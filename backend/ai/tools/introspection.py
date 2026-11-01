"""Introspection tools as StructuredTool wrappers (Phase 4).

Each tool enforces user_id ownership before touching the DB.
Uses Pydantic models for arguments and returns JSON-serializable results.
"""

import logging
import re
from typing import Any, Dict, List

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ai.guards import sanitize_table_name
from auths.models import db
from connections.model import DBConnection
from connections.service import (
    connection_pool,
)
from connections.service import (
    get_full_schema as svc_get_full_schema,
)
from connections.service import (
    get_table_schema as svc_get_table_schema,
)
from connections.service import (
    get_tables as svc_get_tables,
)

logger = logging.getLogger(__name__)


_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _resolve_connection(user_id: int, db_id: int) -> DBConnection:
    conn = db.session.get(DBConnection, db_id)
    if not conn:
        raise ValueError(f"Connection {db_id} not found")
    if conn.user_id != user_id:
        raise PermissionError("Unauthorized: connection does not belong to user")
    return conn


# --- Pydantic argument models ---


class ListTablesArgs(BaseModel):
    user_id: int = Field(..., description="User ID")
    db_id: int = Field(..., description="Database connection ID")


class DescribeTableArgs(BaseModel):
    user_id: int = Field(..., description="User ID")
    db_id: int = Field(..., description="Database connection ID")
    table_name: str = Field(..., min_length=1, max_length=100, description="Table name")


class SampleRowsArgs(BaseModel):
    user_id: int = Field(..., description="User ID")
    db_id: int = Field(..., description="Database connection ID")
    table_name: str = Field(..., min_length=1, max_length=100, description="Table name")
    limit: int = Field(20, ge=1, le=50, description="Row limit")


class CountRowsArgs(BaseModel):
    user_id: int = Field(..., description="User ID")
    db_id: int = Field(..., description="Database connection ID")
    table_name: str = Field(..., min_length=1, max_length=100, description="Table name")


class GetFullSchemaArgs(BaseModel):
    user_id: int = Field(..., description="User ID")
    db_id: int = Field(..., description="Database connection ID")


class RunSQLArgs(BaseModel):
    user_id: int = Field(..., description="User ID")
    db_id: int = Field(..., description="Database connection ID")
    query: str = Field(
        ..., min_length=1, max_length=5000, description="Read-only SQL query (SELECT/WITH only)"
    )


# --- Tool implementations ---


def _list_tables_impl(args: ListTablesArgs) -> List[str]:
    conn = _resolve_connection(args.user_id, args.db_id)
    return svc_get_tables(args.user_id, args.db_id, conn.get_decrypted_connection_string())


def _describe_table_impl(args: DescribeTableArgs) -> Dict[str, Any]:
    table = sanitize_table_name(args.table_name)
    conn = _resolve_connection(args.user_id, args.db_id)
    return svc_get_table_schema(
        args.user_id, args.db_id, conn.get_decrypted_connection_string(), table
    )


def _sample_rows_impl(args: SampleRowsArgs) -> List[Dict[str, Any]]:
    table = sanitize_table_name(args.table_name)
    conn = _resolve_connection(args.user_id, args.db_id)
    conn_str = conn.get_decrypted_connection_string()

    # Verify table exists
    tables = svc_get_tables(args.user_id, args.db_id, conn_str)
    if table not in [x.lower() for x in tables]:
        actual = next((x for x in tables if x.lower() == table), None)
        if not actual:
            raise ValueError(f"Table '{args.table_name}' not found. Available: {', '.join(tables)}")
        table = actual

    with connection_pool.get_connection(args.user_id, args.db_id, conn_str) as c:
        from sqlalchemy import text

        result = c.execute(text(f'SELECT * FROM "{table}" LIMIT :lim'), {"lim": args.limit})
        cols = list(result.keys())
        rows = [dict(zip(cols, row, strict=False)) for row in result.fetchall()]
        # Make JSON-serializable
        for r in rows:
            for k, v in list(r.items()):
                if hasattr(v, "isoformat"):
                    try:
                        r[k] = v.isoformat()
                    except Exception:
                        r[k] = str(v)
        return rows


def _count_rows_impl(args: CountRowsArgs) -> int:
    table = sanitize_table_name(args.table_name)
    conn = _resolve_connection(args.user_id, args.db_id)
    conn_str = conn.get_decrypted_connection_string()

    tables = svc_get_tables(args.user_id, args.db_id, conn_str)
    if table not in [x.lower() for x in tables]:
        actual = next((x for x in tables if x.lower() == table), None)
        if not actual:
            raise ValueError(f"Table '{args.table_name}' not found. Available: {', '.join(tables)}")
        table = actual

    with connection_pool.get_connection(args.user_id, args.db_id, conn_str) as c:
        from sqlalchemy import text

        result = c.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
        return int(result.scalar() or 0)


def _get_full_schema_impl(args: GetFullSchemaArgs) -> Dict[str, Any]:
    conn = _resolve_connection(args.user_id, args.db_id)
    return svc_get_full_schema(args.user_id, args.db_id, conn.get_decrypted_connection_string())


def _run_sql_impl(args: RunSQLArgs) -> List[Dict[str, Any]]:
    # Validate SQL safety
    from ai.guards import validate_sql_ast

    is_safe, error = validate_sql_ast(args.query)
    if not is_safe:
        raise ValueError(error)

    conn = _resolve_connection(args.user_id, args.db_id)
    conn_str = conn.get_decrypted_connection_string()

    with connection_pool.get_connection(args.user_id, args.db_id, conn_str) as c:
        from sqlalchemy import text

        result = c.execute(text(args.query))
        cols = list(result.keys())
        rows = [dict(zip(cols, row, strict=False)) for row in result.fetchall()[:50]]  # Cap at 50
        for r in rows:
            for k, v in list(r.items()):
                if hasattr(v, "isoformat"):
                    try:
                        r[k] = v.isoformat()
                    except Exception:
                        r[k] = str(v)
        return rows


# --- StructuredTool exports ---


def _tool(model, impl, name: str, description: str) -> StructuredTool:
    """Bridge StructuredTool's kwargs-style invocation into model-style impls.

    ``StructuredTool.from_function`` calls the wrapped function with the
    schema fields as kwargs; the ``_*_impl`` functions instead take one
    typed pydantic model. Calling ``model(**kwargs)`` here keeps a single
    validation point (so missing `user_id`/`db_id` surfaces as a clean
    pydantic error) and avoids duplicating parameter lists between the
    schema class and every function signature.
    """

    def _call(**kwargs):
        return impl(model(**kwargs))

    _call.__name__ = name
    return StructuredTool.from_function(
        func=_call,
        name=name,
        description=description,
        args_schema=model,
        return_direct=False,
    )


list_tables = _tool(
    ListTablesArgs,
    _list_tables_impl,
    "list_tables",
    "List all tables in the database. Use when asked 'what tables exist?'.",
)

describe_table = _tool(
    DescribeTableArgs,
    _describe_table_impl,
    "describe_table",
    "Describe columns of a specific table. Use for 'what columns does X table have?'.",
)

sample_rows = _tool(
    SampleRowsArgs,
    _sample_rows_impl,
    "sample_rows",
    "Return sample rows from a table. Use for 'show me the data in X table'.",
)

count_rows = _tool(
    CountRowsArgs,
    _count_rows_impl,
    "count_rows",
    "Count rows in a specific table. Use for 'how many rows in X table?'.",
)

get_full_schema = _tool(
    GetFullSchemaArgs,
    _get_full_schema_impl,
    "get_full_schema",
    "Return full schema (all tables + columns). Use for 'describe the database'.",
)

run_sql_query = _tool(
    RunSQLArgs,
    _run_sql_impl,
    "run_sql_query",
    "Run a read-only SQL SELECT/WITH query and return rows. Use for complex questions other tools can't answer.",
)

# All tools for the agent
ALL_TOOLS = [
    list_tables,
    describe_table,
    sample_rows,
    count_rows,
    get_full_schema,
    run_sql_query,
]
