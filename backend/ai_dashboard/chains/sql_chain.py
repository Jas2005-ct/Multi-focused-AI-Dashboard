"""Compatibility shim: re-export from ai package."""

from ai.agents.sql_chain import (
    _get_sql_chain,
    _validate_sql_safety,
    get_query_format,
    sql_chain,
)

__all__ = [
    "get_query_format",
    "sql_chain",
    "_validate_sql_safety",
    "_get_sql_chain",
]
