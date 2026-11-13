"""Compatibility shim: re-implement router functions using ai package."""

import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableLambda

from ai.agents.react_agent import run_agent_question
from ai.guards import is_write_intent as _is_write_intent
from ai.payloads import RouterResult, Row
from ai_dashboard.schemas import PromptRequest

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


def _extract_table_name(sentence: str) -> str | None:
    # Prefer "in <word> table" / "from <word> table" / last "<word> table"
    m = re.search(r"\b(?:in|from|of)\s+(\w+)\s+table\b", sentence, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\b(\w+)\s+table\b", sentence, re.IGNORECASE)
    if m:
        w = m.group(1).lower()
        if w in ("my", "the", "a", "an", "certificate", "certificates"):
            return w.rstrip("s") if w not in ("my", "the", "a", "an") else None
        return m.group(1)
    return None


def format_introspection_answer(tables: list[str]) -> str:
    if not tables:
        return "No tables found in this database."
    return f"Found {len(tables)} table(s): {', '.join(tables)}."


def format_data_answer(table: str, count: int, rows: list[dict[str, Any]]) -> str:
    msg = f"Table '{table}' has {count} row(s)."
    if rows:
        msg += f" Showing sample of {len(rows)} row(s)."
    return msg


def _metadata_handler(inputs: Dict[str, Any]) -> RouterResult:
    """
    Execute sqlalchemy and return a natural language answer.

    Expected inputs: {sentence, user_id, db_id, schema_context}
    Returns: {"type":"answer", "answer": "...", "tables": [...]}
    """
    user_id: Optional[int] = inputs.get("user_id")
    db_id: Optional[int] = inputs.get("db_id")

    if not db_id:
        no_connection: RouterResult = {
            "type": "answer",
            "answer": "Please select a database connection first, then ask about its tables.",
            "tables": [],
        }
        return no_connection

    if not user_id:
        return {"error": "User not authenticated", "error_type": "auth_error"}

    try:
        from ai.tools.introspection import list_tables

        tables = list_tables.invoke({"user_id": user_id, "db_id": db_id})
        answer = format_introspection_answer(tables)
        listed: RouterResult = {"type": "answer", "answer": answer, "tables": tables}
        return listed
    except PermissionError as e:
        logger.warning(f"Introspection unauthorized user={user_id} db={db_id}: {e}")
        return {"error": str(e), "error_type": "auth_error"}
    except ValueError as e:
        logger.warning(f"Introspection value error: {e}")
        return {"error": str(e), "error_type": "validation_error"}
    except Exception as e:
        logger.exception(f"Introspection failed: {e}")
        return {"error": f"Failed to list tables: {str(e)}", "error_type": "api_error"}


def _data_handler(inputs: Dict[str, Any]) -> RouterResult:
    """
    Handle per-table row questions: 'how many certificates in certificate table'
    Executes COUNT(*) + sample rows via sqlalchemy.
    Returns: {"type":"answer", "answer": "...", "count": n, "rows": [...], "tables": [...]}
    """
    user_id: Optional[int] = inputs.get("user_id")
    db_id: Optional[int] = inputs.get("db_id")
    sentence: str = inputs.get("sentence", "") or ""

    if not db_id:
        no_connection: RouterResult = {
            "type": "answer",
            "answer": "Please select a database connection first, then ask about that table.",
            "tables": [],
        }
        return no_connection
    if not user_id:
        return {"error": "User not authenticated", "error_type": "auth_error"}

    table = _extract_table_name(sentence)
    if not table:
        return _query_handler(inputs)

    try:
        from ai.tools.introspection import count_rows, sample_rows

        count = count_rows.invoke({"user_id": user_id, "db_id": db_id, "table_name": table})
        wants_rows = bool(
            re.search(r"\b(what are|list|show|display|give me)\b", sentence, re.IGNORECASE)
        )
        wants_count = bool(re.search(r"\b(how many|count|number)\b", sentence, re.IGNORECASE))
        rows: List[Row] = []
        if wants_rows or not wants_count:
            try:
                rows = sample_rows.invoke(
                    {"user_id": user_id, "db_id": db_id, "table_name": table, "limit": 20}
                )
            except Exception:
                rows = []

        answer = format_data_answer(table, count, rows)
        data: RouterResult = {
            "type": "answer",
            "answer": answer,
            "count": count,
            "table": table,
            "rows": rows,
        }
        try:
            from ai.tools.introspection import list_tables

            data["tables"] = list_tables.invoke({"user_id": user_id, "db_id": db_id})
        except Exception:
            pass
        return data
    except PermissionError as e:
        logger.warning(f"Data unauthorized user={user_id} db={db_id}: {e}")
        return {"error": str(e), "error_type": "auth_error"}
    except ValueError as e:
        logger.warning(f"Data value error: {e}")
        return {"error": str(e), "error_type": "validation_error"}
    except Exception as e:
        logger.exception(f"Data handler failed: {e}")
        return {"error": f"Failed to query table '{table}': {str(e)}", "error_type": "api_error"}


def _query_handler(inputs: Dict[str, Any]) -> RouterResult:
    """Delegate free-form questions to the tool-calling agent."""
    sentence: str = inputs.get("sentence", "")
    user_id: Optional[int] = inputs.get("user_id")
    db_id: Optional[int] = inputs.get("db_id")
    schema_context: Optional[str] = inputs.get("schema_context")

    if _is_write_intent(sentence):
        logger.warning("BLOCKED write intent in _query_handler sentence=%r", sentence)
        blocked: RouterResult = {
            "type": "answer",
            "answer": "Write operation not permitted — this dashboard is read-only. INSERT/UPDATE/DELETE/CREATE/ALTER/DROP operations are blocked. Please use the Projects UI to create or modify data.",
            "toolCalls": [],
            "tables": [],
            "rows": [],
            "count": None,
            "table": None,
        }
        return blocked

    if not db_id or not user_id:
        from ai.agents.sql_chain import get_query_format as sql_get_query_format
        from ai_dashboard.schemas import PromptRequest

        req = PromptRequest(sentence=sentence, db_id=db_id)
        result: RouterResult = sql_get_query_format(req, schema_context=schema_context)
        if "output_query" in result:
            result["type"] = "query"
        return result

    return run_agent_question(sentence, user_id, db_id, schema_context)


def _agent_dispatch(inputs: Dict[str, Any]) -> RouterResult:
    """Route every request to the tool-calling agent (LLM decides the tool)."""
    if _is_write_intent(inputs.get("sentence", "")):
        logger.warning(
            "BLOCKED write intent in _agent_dispatch sentence=%r", inputs.get("sentence", "")
        )
        return {
            "type": "answer",
            "answer": "Write operation not permitted — this dashboard is read-only. INSERT/UPDATE/DELETE/CREATE/ALTER/DROP operations are blocked. Please use the Projects UI to create or modify data.",
            "toolCalls": [],
            "tables": [],
            "rows": [],
            "count": None,
            "table": None,
        }

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


def get_introspection_router():
    """Factory for routes.py — returns the branch chain."""
    return router_chain


# Convenience wrapper matching old get_query_format signature + extra context
def get_routed_query_format(
    sentence: PromptRequest,
    user_id: Optional[int] = None,
    db_id: Optional[int] = None,
    schema_context: Optional[str] = None,
) -> RouterResult:
    return router_chain.invoke(
        {
            "sentence": sentence.sentence,
            "user_id": user_id,
            "db_id": db_id if db_id is not None else sentence.db_id,
            "schema_context": schema_context,
        }
    )
