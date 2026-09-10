"""Router for database questions — delegates to a tool-calling agent.

Every request goes through the agent, which decides which tool to call
(list_tables, count_rows, sample_rows, describe_table, get_full_schema,
run_sql_query). The regex helpers below (is_metadata_intent /
is_data_intent) are kept for reference but are no longer used by the router.
"""

import re
import logging
from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableBranch, RunnableLambda

from ai_dashboard.schemas import PromptRequest
from ai_dashboard.chains.sql_chain import get_query_format as sql_get_query_format
from ai_dashboard.tools.introspection import format_introspection_answer, format_data_answer

logger = logging.getLogger(__name__)

# Phase 1: regex routers — fast, deterministic

# METADATA = DB structure: "how many tables", "list tables", "what tables in my db", "describe schema"
_METADATA_RE = re.compile(
    r"\b(how many|count)\s+(tables|schemas)\b"
    r"|\b(list|show|display)\s+(tables|schemas)\b"
    r"|\bwhat\s+(are\s+)?(the\s+)?tables\b"
    r"|\b(describe|show)\s+(schema|structure)\b"
    r"|\b(tables?|schemas?)\b.*\b(in|of|for)\b.*\b(db|database)\b",
    re.IGNORECASE,
)

# DATA = per-table row questions: "how many certificates in certificate table", "what are the certificates"
_DATA_RE = re.compile(
    r"\b(how many|count|what are|list|show|display)\b.*\b(\w+)\s+table\b",
    re.IGNORECASE,
)

from ai_dashboard.write_guard import is_write_intent as _is_write_intent


def _extract_table_name(sentence: str) -> str | None:
    # Prefer "in <word> table" / "from <word> table" / last "<word> table"
    m = re.search(r"\b(?:in|from|of)\s+(\w+)\s+table\b", sentence, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\b(\w+)\s+table\b", sentence, re.IGNORECASE)
    if m:
        w = m.group(1).lower()
        if w in ("my", "the", "a", "an", "certificate", "certificates"):
            # for "certificate table" return certificate, but handle plural
            return w.rstrip("s") if w not in ("my", "the", "a", "an") else None
        return m.group(1)
    return None


def is_metadata_intent(sentence: str) -> bool:
    """Return True if sentence asks about DB structure (list of tables)."""
    if not sentence:
        return False
    s = sentence.strip().lower()
    # Data intent like "how many certificates in certificate table" must NOT be metadata
    # If it mentions a specific <X> table where X != tables/schemas, treat as data
    data_match = _DATA_RE.search(sentence)
    if data_match:
        tbl = _extract_table_name(sentence)
        if tbl and tbl.lower() not in ("tables", "table", "schemas", "schema"):
            # e.g., certificate table -> data, not metadata
            # but "how many tables" leaves tbl = tables -> keep as metadata
            return False
    return bool(_METADATA_RE.search(sentence.strip()))


def is_data_intent(sentence: str) -> bool:
    """Return True if sentence asks about rows in a specific table."""
    if not sentence:
        return False
    if _DATA_RE.search(sentence):
        tbl = _extract_table_name(sentence)
        return bool(tbl)
    return False


def _metadata_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute sqlalchemy and return a natural language answer.

    Expected inputs: {sentence, user_id, db_id, schema_context}
    Returns: {"type":"answer", "answer": "...", "tables": [...]}
    """
    user_id: Optional[int] = inputs.get("user_id")
    db_id: Optional[int] = inputs.get("db_id")

    if not db_id:
        return {
            "type": "answer",
            "answer": "Please select a database connection first, then ask about its tables.",
            "tables": [],
        }

    if not user_id:
        return {"error": "User not authenticated", "error_type": "auth_error"}

    try:
        # Import here to avoid circular deps at module load
        from ai_dashboard.tools.introspection import list_tables_tool

        tables = list_tables_tool.invoke({"user_id": user_id, "db_id": db_id})
        answer = format_introspection_answer(tables)
        return {"type": "answer", "answer": answer, "tables": tables}
    except PermissionError as e:
        logger.warning(f"Introspection unauthorized user={user_id} db={db_id}: {e}")
        return {"error": str(e), "error_type": "auth_error"}
    except ValueError as e:
        logger.warning(f"Introspection value error: {e}")
        return {"error": str(e), "error_type": "validation_error"}
    except Exception as e:
        logger.exception(f"Introspection failed: {e}")
        return {"error": f"Failed to list tables: {str(e)}", "error_type": "api_error"}


def _data_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle per-table row questions: 'how many certificates in certificate table'
    Executes COUNT(*) + sample rows via sqlalchemy.
    Returns: {"type":"answer", "answer": "...", "count": n, "rows": [...], "tables": [...]}
    """
    user_id: Optional[int] = inputs.get("user_id")
    db_id: Optional[int] = inputs.get("db_id")
    sentence: str = inputs.get("sentence", "") or ""

    if not db_id:
        return {
            "type": "answer",
            "answer": "Please select a database connection first, then ask about that table.",
            "tables": [],
        }
    if not user_id:
        return {"error": "User not authenticated", "error_type": "auth_error"}

    table = _extract_table_name(sentence)
    if not table:
        # fallback to generic query branch
        return _query_handler(inputs)

    try:
        from ai_dashboard.tools.introspection import count_rows_tool, sample_rows_tool, format_data_answer

        count = count_rows_tool.invoke({"user_id": user_id, "db_id": db_id, "table_name": table})
        # detect if user also wants rows ("what are they" / "list" / "show")
        wants_rows = bool(re.search(r"\b(what are|list|show|display|give me)\b", sentence, re.IGNORECASE))
        wants_count = bool(re.search(r"\b(how many|count|number)\b", sentence, re.IGNORECASE))
        rows = []
        if wants_rows or not wants_count:
            # hybrid: if they asked both, or just "what are"
            try:
                rows = sample_rows_tool.invoke({"user_id": user_id, "db_id": db_id, "table_name": table, "limit": 20})
            except Exception:
                rows = []

        answer = format_data_answer(table, count, rows)
        result: Dict[str, Any] = {"type": "answer", "answer": answer, "count": count, "table": table, "rows": rows}
        # also include tables for UI consistency
        try:
            from ai_dashboard.tools.introspection import list_tables_tool

            result["tables"] = list_tables_tool.invoke({"user_id": user_id, "db_id": db_id})
        except Exception:
            pass
        return result
    except PermissionError as e:
        logger.warning(f"Data unauthorized user={user_id} db={db_id}: {e}")
        return {"error": str(e), "error_type": "auth_error"}
    except ValueError as e:
        # table not found -> fallback to LLM query generation with helpful hint
        logger.warning(f"Data value error: {e}")
        return {"error": str(e), "error_type": "validation_error"}
    except Exception as e:
        logger.exception(f"Data handler failed: {e}")
        return {"error": f"Failed to query table '{table}': {str(e)}", "error_type": "api_error"}


def _query_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Delegate free-form questions to the tool-calling agent.

    The agent decides which tool(s) to call (list tables, count rows, sample
    rows, describe table, run SQL) and returns a natural-language answer.
    Falls back to raw SQL generation if the model lacks tool support.
    """
    sentence: str = inputs.get("sentence", "")
    user_id: Optional[int] = inputs.get("user_id")
    db_id: Optional[int] = inputs.get("db_id")
    schema_context: Optional[str] = inputs.get("schema_context")

    if _is_write_intent(sentence):
        logger.warning("BLOCKED write intent in _query_handler sentence=%r", sentence)
        return {
            "type": "answer",
            "answer": "Write operation not permitted — this dashboard is read-only. INSERT/UPDATE/DELETE/CREATE/ALTER/DROP operations are blocked. Please use the Projects UI to create or modify data.",
            "toolCalls": [],
            "tables": [],
            "rows": [],
            "count": None,
            "table": None,
        }

    if not db_id or not user_id:
        # Nothing to connect to -> let the old chain attempt a generic answer
        req = PromptRequest(sentence=sentence, db_id=db_id)
        result = sql_get_query_format(req, schema_context=schema_context)
        if "output_query" in result:
            result["type"] = "query"
        return result

    from ai_dashboard.chains.agent_chain import run_agent_question

    return run_agent_question(sentence, user_id, db_id, schema_context)


def _agent_dispatch(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Route every request to the tool-calling agent (LLM decides the tool)."""
    if _is_write_intent(inputs.get("sentence", "")):
        logger.warning("BLOCKED write intent in _agent_dispatch sentence=%r", inputs.get("sentence", ""))
        return {
            "type": "answer",
            "answer": "Write operation not permitted — this dashboard is read-only. INSERT/UPDATE/DELETE/CREATE/ALTER/DROP operations are blocked. Please use the Projects UI to create or modify data.",
            "toolCalls": [],
            "tables": [],
            "rows": [],
            "count": None,
            "table": None,
        }
    from ai_dashboard.chains.agent_chain import run_agent_question

    sentence: str = inputs.get("sentence", "") or ""
    user_id: Optional[int] = inputs.get("user_id")
    db_id: Optional[int] = inputs.get("db_id")
    schema_context: Optional[str] = inputs.get("schema_context")
    return run_agent_question(sentence, user_id, db_id, schema_context)


# The router is now a single tool-calling agent: the LLM decides which tool
# to call for every question. The old regex branches (metadata / data) are
# kept as direct tool wrappers below, but the router no longer selects them
# by hand — the agent picks from the same tool set.
router_chain = RunnableLambda(_agent_dispatch)

# Optional LLM classifier for Phase 2 — kept import-lazy to avoid extra call in Phase 1
# def get_classifier_chain():
#     from langchain_core.prompts import ChatPromptTemplate
#     from ai_dashboard.chains.llm import get_llm
#     from langchain_core.output_parsers import StrOutputParser
#     prompt = ChatPromptTemplate.from_template(
#         "Classify the user request as METADATA (asking about tables/schema/columns/structure) "
#         "or QUERY (asking for data/select/join/aggregate). Sentence: '{sentence}' Reply one word."
#     )
#     return prompt | get_llm(temperature=0) | StrOutputParser()


def get_introspection_router():
    """Factory for routes.py — returns the branch chain."""
    return router_chain


# Convenience wrapper matching old get_query_format signature + extra context
def get_routed_query_format(
    sentence: PromptRequest,
    user_id: Optional[int] = None,
    db_id: Optional[int] = None,
    schema_context: Optional[str] = None,
) -> Dict[str, Any]:
    return router_chain.invoke(
        {
            "sentence": sentence.sentence,
            "user_id": user_id,
            "db_id": db_id if db_id is not None else sentence.db_id,
            "schema_context": schema_context,
        }
    )
