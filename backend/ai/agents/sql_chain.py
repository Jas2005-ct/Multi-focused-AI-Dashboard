"""LCEL SQL generation chain (Phase 4).

Uses LangChain Expression Language: prompt | model | safety_gate.
Keeps old chain as fallback for learning purposes.
"""

import logging
import re
from typing import Any

from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from ai.guards import add_safety_limits, validate_sql_ast
from ai.llm_factory import get_llm

logger = logging.getLogger(__name__)


def extract_sql(text: str) -> str:
    """Extract a single SQL statement from LLM output.

    Models sometimes wrap SQL in markdown fences or prepend explanations.
    The validator/parser expects raw SQL, so normalize before safety checks.
    """
    if not text:
        return ""
    cleaned = text.strip()

    # Prefer content from a fenced code block (```sql ... ``` or ``` ... ```).
    fence = re.search(
        r"```(?:sql|postgresql|postgres)?\s*\n?(.*?)```",
        cleaned,
        re.IGNORECASE | re.DOTALL,
    )
    if fence:
        cleaned = fence.group(1).strip()

    # If prose remains before the statement, keep from first SELECT/WITH.
    match = re.search(r"\b(SELECT|WITH)\b", cleaned, re.IGNORECASE)
    if match and match.start() > 0:
        logger.debug("Stripping %d chars of prose before SQL", match.start())
        cleaned = cleaned[match.start() :].strip()

    # Remove a stray trailing fence.
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    return cleaned


SQL_SYSTEM_TEMPLATE = """You are an expert PostgreSQL SQL Query Compiler.

Convert the user request into a single valid, optimized PostgreSQL query.

RULES:
1. Output ONLY the SQL statement. No markdown, no code fences, no explanation, no preamble.
2. Output must be valid PostgreSQL syntax and production-safe.
3. If aggregation is required, always use proper GROUP BY.
4. Use explicit column names whenever possible; avoid SELECT *.
5. Use ONLY table and column names that appear in the schema context. Never invent identifiers.
6. Generate optimized queries whenever possible.

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
    """Final chain step: normalize, reject unsafe SQL, and apply safety limits."""
    cleaned = extract_sql(sql)
    if cleaned != (sql or "").strip():
        logger.info("Normalized LLM SQL output before validation")
    is_safe, error_msg = validate_sql_ast(cleaned)
    if not is_safe:
        logger.warning(
            "Potentially unsafe SQL detected: %s | raw_preview=%r",
            error_msg,
            (sql or "")[:200],
        )
        raise ValueError(error_msg)
    return add_safety_limits(cleaned)


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
