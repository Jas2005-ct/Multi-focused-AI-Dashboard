"""Introspection tools as StructuredTool wrappers (Phase 4).

Each tool enforces user_id ownership before touching the DB.
Uses Pydantic models for arguments and returns JSON-serializable results.
"""

import logging
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from langchain_core.tools import StructuredTool

from connections.model import DBConnection
from connections.service import (
    get_tables as svc_get_tables,
    get_table_schema as svc_get_table_schema,
    get_full_schema as svc_get_full_schema,
    connection_pool,
)
from ai.guards import sanitize_table_name

logger = logging.getLogger(__name__)


_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _resolve_connection(user_id: int, db_id: int) -> DBConnection:
    conn = DBConnection.query.get(db_id)
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
    query: str = Field(..., min_length=1, max_length=5000, description="Read-only SQL query (SELECT/WITH only)")


# --- Tool implementations ---

def _list_tables_impl(args: ListTablesArgs) -> List[str]:
    conn = _resolve_connection(args.user_id, args.db_id)
    return svc_get_tables(args.user_id, args.db_id, conn.get_decrypted_connection_string())


def _describe_table_impl(args: DescribeTableArgs) -> Dict[str, Any]:
    table = sanitize_table_name(args.table_name)
    conn = _resolve_connection(args.user_id, args.db_id)
    return svc_get_table_schema(args.user_id, args.db_id, conn.get_decrypted_connection_string(), table)


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
        rows = [dict(zip(cols, row)) for row in result.fetchall()]
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
        rows = [dict(zip(cols, row)) for row in result.fetchall()[:50]]  # Cap at 50
        for r in rows:
            for k, v in list(r.items()):
                if hasattr(v, "isoformat"):
                    try:
                        r[k] = v.isoformat()
                    except Exception:
                        r[k] = str(v)
        return rows


# --- StructuredTool exports ---

list_tables = StructuredTool.from_function(
    func=_list_tables_impl,
    name="list_tables",
    description="List all tables in the database. Use when asked 'what tables exist?'.",
    args_schema=ListTablesArgs,
    return_direct=False,
)

describe_table = StructuredTool.from_function(
    func=_describe_table_impl,
    name="describe_table",
    description="Describe columns of a specific table. Use for 'what columns does X table have?'.",
    args_schema=DescribeTableArgs,
    return_direct=False,
)

sample_rows = StructuredTool.from_function(
    func=_sample_rows_impl,
    name="sample_rows",
    description="Return sample rows from a table. Use for 'show me the data in X table'.",
    args_schema=SampleRowsArgs,
    return_direct=False,
)

count_rows = StructuredTool.from_function(
    func=_count_rows_impl,
    name="count_rows",
    description="Count rows in a specific table. Use for 'how many rows in X table?'.",
    args_schema=CountRowsArgs,
    return_direct=False,
)

get_full_schema = StructuredTool.from_function(
    func=_get_full_schema_impl,
    name="get_full_schema",
    description="Return full schema (all tables + columns). Use for 'describe the database'.",
    args_schema=GetFullSchemaArgs,
    return_direct=False,
)

run_sql_query = StructuredTool.from_function(
    func=_run_sql_impl,
    name="run_sql_query",
    description="Run a read-only SQL SELECT/WITH query and return rows. Use for complex questions other tools can't answer.",
    args_schema=RunSQLArgs,
    return_direct=False,
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