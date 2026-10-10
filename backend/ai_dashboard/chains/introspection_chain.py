"""Router for database questions — delegates to LangGraph ReAct agent.

All requests go through the agent, which decides which tool to call
(list_tables, count_rows, sample_rows, describe_table, get_full_schema,
run_sql_query). The old regex router and handlers are removed.
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableLambda

from ai_dashboard.schemas import PromptRequest
from ai.agents.react_agent import run_agent_question
from ai.guards import is_write_intent

logger = logging.getLogger(__name__)


def _agent_dispatch(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Route every request to the LangGraph ReAct agent."""
    if is_write_intent(inputs.get("sentence", "")):
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
    from ai.agents.react_agent import run_agent_question

    sentence: str = inputs.get("sentence", "") or ""
    user_id: Optional[int] = inputs.get("user_id")
    db_id: Optional[int] = inputs.get("db_id")
    schema_context: Optional[str] = inputs.get("schema_context")
    return run_agent_question(sentence, user_id, db_id, schema_context)


# Single tool-calling agent: the LLM decides which tool to call for every question.
router_chain = RunnableLambda(_agent_dispatch)


def get_introspection_router():
    """Factory for routes.py — returns the agent chain."""
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