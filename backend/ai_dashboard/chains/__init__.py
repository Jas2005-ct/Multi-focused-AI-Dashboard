"""Compatibility shim: re-export from ai package."""

from ai.agents.sql_chain import get_query_format, sql_chain
from ai.agents.react_agent import run_agent_question

from ai_dashboard.chains.introspection_chain import (
    get_introspection_router,
    get_routed_query_format,
)

__all__ = [
    "get_query_format",
    "sql_chain",
    "get_introspection_router",
    "get_routed_query_format",
    "run_agent_question",
]