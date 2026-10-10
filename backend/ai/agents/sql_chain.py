"""LCEL SQL generation chain (Phase 4).

Uses LangChain Expression Language: prompt | model | safety_gate.
Keeps old chain as fallback for learning purposes.
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from ai.llm_factory import get_llm
from ai.guards import validate_sql_ast, add_safety_limits

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

sql_prompt = ChatPromptTemplate.from_messages([
    ("system", SQL_SYSTEM_TEMPLATE),
    ("human", SQL_USER_TEMPLATE),
])


def _safety_gate(sql: str) -> str:
    """Final chain step: reject unsafe SQL before it reaches callers."""
    is_safe, error_msg = validate_sql_ast(sql)
    if not is_safe:
        logger.warning(f"Potentially unsafe SQL detected: {error_msg}")
        raise ValueError(error_msg)
    return add_safety_limits(sql)


# LCEL chain: prompt -> model -> parser -> safety_gate
sql_chain = (
    sql_prompt
    | get_llm(temperature=0, max_tokens=3000)
    | StrOutputParser()
    | RunnableLambda(_safety_gate)
)


def get_query_format(
    sentence: str,
    schema_context: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert natural language to SQL using LCEL chain.

    Args:
        sentence: User input
        schema_context: Optional database schema context

    Returns:
        {"sql": str} on success, or {"error": ..., "error_type": ...}
    """
    try:
        sql = sql_chain.invoke({
            "sentence": sentence,
            "schema_context": schema_context or "",
        })
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