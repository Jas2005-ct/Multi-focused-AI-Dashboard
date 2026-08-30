"""SQL generation chain built with LangChain.

Phases 2-4 of the refactor:
  - ChatPromptTemplate replaces manual string concatenation.
  - .with_structured_output(QueryResponse) replaces markdown cleanup, JSON
    parsing and all regex fallbacks: the model is forced into the Pydantic
    schema, so invalid output raises instead of needing to be fished out.
  - LCEL (the | pipe operator) composes prompt -> model -> safety gate.

The public function get_query_format keeps its old signature and return
shape so routes.py (and therefore the frontend) stay compatible.
"""

import logging
import re
from typing import Any, Dict, Optional

from langchain_core.exceptions import OutputParserException
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from ai_dashboard.chains.llm import get_llm
from ai_dashboard.schemas import PromptRequest, QueryResponse

logger = logging.getLogger(__name__)


class UnsafeQueryError(ValueError):
    """Raised when generated SQL fails the security validation step."""


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


def _validate_sql_safety(query: str) -> tuple[bool, str]:
    """Validate SQL for dangerous patterns (kept as defense-in-depth).

    Returns:
        Tuple of (is_safe, error_message).
    """
    query_upper = query.upper().strip()

    dangerous_patterns = [
        (r';\s*(DROP|DELETE|INSERT|UPDATE|CREATE|ALTER|GRANT|REVOKE|TRUNCATE|EXEC|EXECUTE|UNION|SELECT)',
         "Multiple SQL statements detected - potential injection"),
        (r'UNION\s+SELECT', "UNION SELECT detected - potential injection"),
        (r'/\*.*\*/', "Block comment detected - potential injection"),
        (r'--.*$', "Line comment detected - potential injection", re.MULTILINE),
        (r';\s*[^\s]', "Stacked query detected - potential injection"),
        (r'(SLEEP|BENCHMARK|WAITFOR|DELAY)\s*\(', "Time delay function detected - potential injection"),
        (r'(LOAD_FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE)', "File operation detected - potential injection"),
        (r'XP_CMDSHELL|SP_OACREATE|SP_OAMETHOD', "System command execution detected"),
    ]

    for pattern in dangerous_patterns:
        flags = pattern[2] if len(pattern) > 2 else 0
        if re.search(pattern[0], query_upper, flags):
            return False, pattern[1]

    allowed_starts = ['SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE']
    first_word = query_upper.split()[0] if query_upper.split() else ''

    if first_word not in allowed_starts:
        return False, f"Query must start with SELECT, WITH, INSERT, UPDATE, or DELETE. Found: {first_word}"

    return True, ""


def _safety_gate(result: QueryResponse) -> Dict[str, Any]:
    """Final chain step: reject unsafe SQL before it reaches callers."""
    is_safe, error_msg = _validate_sql_safety(result.output_query)
    if not is_safe:
        logger.warning(f"Potentially unsafe SQL detected: {error_msg}")
        raise UnsafeQueryError(error_msg)
    return {"output_query": result.output_query}


structured_llm = get_llm().with_structured_output(QueryResponse)

sql_chain = sql_prompt | structured_llm | RunnableLambda(_safety_gate)


def get_query_format(
    sentence: PromptRequest,
    config: Optional[Any] = None,
    schema_context: Optional[str] = None
) -> Dict[str, Any]:
    """Convert natural language to SQL using the LangChain chain.

    Args:
        sentence: User input wrapped in PromptRequest.
        config: Unused; kept for signature compatibility.
        schema_context: Optional database schema context.

    Returns:
        {"output_query": str} on success, or {"error": ..., "error_type": ...}.
    """
    try:
        return sql_chain.invoke(
            {
                "sentence": sentence.sentence,
                "schema_context": schema_context or "",
            }
        )

    except OutputParserException as e:
        error_msg = f"Response parsing failed: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg, "error_type": "parsing_error"}

    except UnsafeQueryError as e:
        error_msg = f"Generated query failed security validation: {str(e)}"
        logger.warning(error_msg)
        return {"error": error_msg, "error_type": "security_error"}

    except Exception as e:
        msg_lower = str(e).lower()
        if "length limit" in msg_lower or "completion_tokens" in str(e):
            error_msg = (
                "Model response was truncated — token limit reached (completion 500 tokens, "
                "995 prompt + 536 reasoning). Increased to 1500; please retry. "
                "If it persists, simplify the prompt/schema."
            )
            logger.warning(error_msg + f" Raw: {e}")
            return {"error": error_msg, "error_type": "api_error"}
        error_msg = f"API request failed: {str(e)}"
        logger.exception(error_msg)
        return {"error": error_msg, "error_type": "api_error"}
