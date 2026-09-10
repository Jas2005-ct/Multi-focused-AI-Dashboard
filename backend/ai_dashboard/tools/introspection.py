"""Introspection tools — thin wrappers around db_connections helpers.

Each tool enforces user_id ownership before touching the DB.
Decorated with @tool for future AgentExecutor use, but also callable directly.
"""

import logging
from typing import List, Dict, Any

from langchain_core.tools import tool

from auths.models import DBConnection

logger = logging.getLogger(__name__)


def _resolve_connection(user_id: int, db_id: int) -> DBConnection:
    conn = DBConnection.query.get(db_id)
    if not conn:
        raise ValueError(f"Connection {db_id} not found")
    if conn.user_id != user_id:
        raise PermissionError("Unauthorized: connection does not belong to user")
    return conn


@tool
def list_tables_tool(user_id: int, db_id: int) -> List[str]:
    """List all tables in the connected database. Use when user asks what tables exist."""
    from ai_dashboard.db_connections import get_tables

    conn = _resolve_connection(user_id, db_id)
    return get_tables(user_id, db_id, conn.get_decrypted_connection_string())


@tool
def count_tables_tool(user_id: int, db_id: int) -> Dict[str, Any]:
    """Count tables and return list. Use for 'how many tables' questions."""
    tables = list_tables_tool.invoke({"user_id": user_id, "db_id": db_id})
    return {"count": len(tables), "tables": tables}


@tool
def describe_table_tool(user_id: int, db_id: int, table_name: str) -> Dict[str, Any]:
    """Describe columns of a single table."""
    from ai_dashboard.db_connections import get_table_schema

    conn = _resolve_connection(user_id, db_id)
    return get_table_schema(user_id, db_id, conn.get_decrypted_connection_string(), table_name)


@tool
def get_full_schema_tool(user_id: int, db_id: int) -> Dict[str, Any]:
    """Return full schema (all tables + columns). Use for 'describe DB' questions."""
    from ai_dashboard.db_connections import get_full_schema

    conn = _resolve_connection(user_id, db_id)
    return get_full_schema(user_id, db_id, conn.get_decrypted_connection_string())


import re

_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_table_name(table: str) -> str:
    t = table.strip().strip('"').strip("'").lower()
    if not _TABLE_NAME_RE.match(t):
        raise ValueError(f"Invalid table name: {table}")
    # prevent injection via schema-qualified or quoted
    if "." in t or ";" in t or " " in t:
        raise ValueError(f"Invalid table name: {table}")
    return t


@tool
def count_rows_tool(user_id: int, db_id: int, table_name: str) -> int:
    """Count rows in a specific table. Use for 'how many X in Y table'."""
    from sqlalchemy import text
    from ai_dashboard.db_connections import connection_pool

    t = _validate_table_name(table_name)
    conn = _resolve_connection(user_id, db_id)
    conn_str = conn.get_decrypted_connection_string()
    # Verify table exists
    from ai_dashboard.db_connections import get_tables

    tables = get_tables(user_id, db_id, conn_str)
    if t not in [x.lower() for x in tables]:
        # allow case-insensitive but keep original for query
        # try to find actual casing
        actual = next((x for x in tables if x.lower() == t), None)
        if not actual:
            raise ValueError(f"Table '{table_name}' not found. Available: {', '.join(tables)}")
        t = actual

    with connection_pool.get_connection(user_id, db_id, conn_str) as c:
        # quote identifier safely (postgres/mysql both accept double quotes)
        result = c.execute(text(f'SELECT COUNT(*) FROM "{t}"'))
        return int(result.scalar() or 0)


@tool
def sample_rows_tool(user_id: int, db_id: int, table_name: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Return sample rows from a table. Use for 'what are the X'."""
    from sqlalchemy import text
    from ai_dashboard.db_connections import connection_pool

    t = _validate_table_name(table_name)
    limit = max(1, min(int(limit), 50))
    conn = _resolve_connection(user_id, db_id)
    conn_str = conn.get_decrypted_connection_string()
    from ai_dashboard.db_connections import get_tables

    tables = get_tables(user_id, db_id, conn_str)
    if t not in [x.lower() for x in tables]:
        actual = next((x for x in tables if x.lower() == t), None)
        if not actual:
            raise ValueError(f"Table '{table_name}' not found. Available: {', '.join(tables)}")
        t = actual

    with connection_pool.get_connection(user_id, db_id, conn_str) as c:
        result = c.execute(text(f'SELECT * FROM "{t}" LIMIT :lim'), {"lim": limit})
        cols = list(result.keys())
        rows = [dict(zip(cols, row)) for row in result.fetchall()]
        # make JSON-serializable (datetime -> iso)
        for r in rows:
            for k, v in list(r.items()):
                if hasattr(v, "isoformat"):
                    try:
                        r[k] = v.isoformat()
                    except Exception:
                        r[k] = str(v)
        return rows


def format_introspection_answer(tables: List[str], count: int = None) -> str:
    if count is None:
        count = len(tables)
    if count == 0:
        return "There are no tables in this database."
    if count == 1:
        return f"There is 1 table: {tables[0]}"
    listed = ", ".join(tables[:20])
    suffix = f" (showing 20 of {count})" if count > 20 else ""
    return f"There are {count} tables: {listed}{suffix}."


def format_data_answer(table: str, count: int, rows: List[Dict[str, Any]]) -> str:
    if count == 0:
        return f"There are no rows in '{table}' table."
    header = f"There are {count} row(s) in '{table}' table."
    if rows:
        header += f" Showing {len(rows)} sample row(s)."
    return header
