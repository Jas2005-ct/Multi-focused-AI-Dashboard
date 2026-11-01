"""LCEL SQL generation chain (Phase 4).

Uses LangChain Expression Language: prompt | model | safety_gate.
Keeps old chain as fallback for learning purposes.
"""

import logging
from typing import Any

from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from ai.guards import add_safety_limits, validate_sql_ast
from ai.llm_factory import get_llm

logger = logging.getLogger(__name__)


SQL_SYSTEM_TEMPLATE = """You are an expert PostgreSQL SQL Query Compiler.

Convert the user request into a single valid, optimized PostgreSQL query.

RULES:
1. Output must be valid PostgreSQL syntax and production-safe.
2. If aggregation is required, always use proper GROUP BY.
3. Use explicit column names whenever possible; avoid SELECT *.
4. Preserve exact table and column names provided by the user.
5. Generate optimized queries whenever possible.

DATABASE SCHEMA CONTEXT (may be empty):
{schema_context}"""

SQL_USER_TEMPLATE = "Convert this request to a PostgreSQL query: {sentence}"

sql_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SQL_SYSTEM_TEMPLATE),
        ("human", SQL_USER_TEMPLATE),
    ]
)


def _safety_gate(sql: str) -> str:
    """Final chain step: reject unsafe SQL before it reaches callers."""
    is_safe, error_msg = validate_sql_ast(sql)
    if not is_safe:
        logger.warning(f"Potentially unsafe SQL detected: {error_msg}")
        raise ValueError(error_msg)
    return add_safety_limits(sql)


def _get_sql_chain():
    """Lazy initialization of the SQL chain to avoid module-level LLM initialization."""
    return (
        sql_prompt
        | get_llm(temperature=0, max_tokens=3000)
        | StrOutputParser()
        | RunnableLambda(_safety_gate)
    )


def get_query_format(
    sentence: Any,
    schema_context: str | None = None,
) -> dict[str, Any]:
    """Convert natural language to SQL using LCEL chain.

    Args:
        sentence: User input (string or PromptRequest)
        schema_context: Optional database schema context

    Returns:
        {"sql": str} on success, or {"error": ..., "error_type": ...}
    """
    try:
        raw_sentence = sentence.sentence if hasattr(sentence, "sentence") else str(sentence)
        sql_chain = _get_sql_chain()
        sql = sql_chain.invoke(
            {
                "sentence": raw_sentence,
                "schema_context": schema_context or "",
            }
        )
        return {"sql": sql}

    except OutputParserException as e:
        error_msg = f"Response parsing failed: {e}"
        logger.error(error_msg)
        return {"error": error_msg, "error_type": "parsing_error"}

    except ValueError as e:
        error_msg = f"Generated query failed security validation: {e}"
        logger.warning(error_msg)
        return {"error": error_msg, "error_type": "security_error"}

    except Exception as e:
        msg_lower = str(e).lower()
        if "length limit" in msg_lower or "completion_tokens" in str(e):
            error_msg = (
                "Model response was truncated — token limit reached. "
                "Please retry. If it persists, simplify the prompt/schema."
            )
            logger.warning(f"{error_msg} Raw: {e}")
            return {"error": error_msg, "error_type": "api_error"}
        error_msg = f"API request failed: {e}"
        logger.exception(error_msg)
        return {"error": error_msg, "error_type": "api_error"}


class _LazySqlChain:
    """Lazily-built LCEL chain.

    The chain is composed on first use instead of at import time, because
    building it requires a live LLM client (and its API key). Importing this
    module must never fail just because no provider is configured yet.
    """

    def __init__(self):
        self._chain = None

    def _resolve(self):
        if self._chain is None:
            self._chain = _get_sql_chain()
        return self._chain

    def invoke(self, *args, **kwargs):
        return self._resolve().invoke(*args, **kwargs)

    async def ainvoke(self, *args, **kwargs):
        return await self._resolve().ainvoke(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        return self._resolve().invoke(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._resolve(), item)

    def __repr__(self) -> str:
        state = "built" if self._chain is not None else "lazy"
        return f"<LazySqlChain ({state})>"


# Module-level exports for backward compatibility
_validate_sql_safety = validate_sql_ast
sql_chain = _LazySqlChain()
