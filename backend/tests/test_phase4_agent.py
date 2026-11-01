"""ReAct agent regression: session-param injection into tool calls.

Historical failure: tools require `user_id`/`db_id` but the LLM's tool
calls omit them; without injection, every invoke died in Pydantic
validation and the agent loop degraded into `Error: ...` tool messages
until the LCEL fallback answered with SQL instead.

These tests lock the injection contract with a stubbed LLM — no
network, no real model, no flaky keys.

Imports are deferred into test bodies (see conftest): importing the
agent chain at module import time would materialize the LRU settings
cache before the app fixture installs its hermetic DATABASE_URL.
"""

import pytest
from langchain_core.messages import AIMessage


class _ScriptedLLM:
    """Deterministic stand-in for the real LLM provider.

    `invoke` hands the agent a predetermined sequence of AIMessages, so
    the agent loop is driven exactly once per scripted turn.
    """

    def __init__(self, script: list[AIMessage]):
        self._script = iter(script)

    def bind_tools(self, tools):  # pragma: no cover - signature parity
        return self

    def invoke(self, messages):
        return next(self._script)


@pytest.fixture()
def _fresh_settings():
    """Defuse the LRU settings cache around every test in this module."""
    from config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def seeded_connection(app_client, _fresh_settings):
    """A saved connection owned by a real registered user."""
    _, client = app_client
    from connections.model import DBConnection

    reg = client.post(
        "/auth/register",
        json={"email": "agent@example.com", "password": "Password123", "name": "Agent"},
    )
    assert reg.status_code == 201, reg.get_data(as_text=True)
    user_id = reg.get_json()["user"]["id"]

    conn = DBConnection(
        user_id=user_id,
        name="Agent DB",
        db_type="postgresql",
        host="db.invalid",
        port=5432,
        database="app",
        username="u",
        password="p",
        connection_string="postgresql://u:p@db.invalid:5432/app",
        sslmode="require",
    )
    db_session = app_client[0].extensions["sqlalchemy"].session
    db_session.add(conn)
    db_session.commit()
    return user_id, conn.id


def test_agent_injects_session_params_into_tool_call(app_client, seeded_connection, monkeypatch):
    """The agent must add user_id/db_id when the LLM's tool args omit them."""
    from ai.agents import react_agent
    from ai.tools import introspection as introspection_tools

    user_id, db_id = seeded_connection

    scripted = _ScriptedLLM(
        [
            # The LLM *omits* user_id/db_id on purpose — pre-fix, this exact
            # call died with Pydantic "Field required".
            AIMessage(content="", tool_calls=[{"name": "list_tables", "args": {}, "id": "c1"}]),
            AIMessage(content="Found 2 tables: users, orders."),
        ]
    )
    monkeypatch.setattr(react_agent, "get_llm", lambda **_kw: scripted)
    monkeypatch.setattr(react_agent, "_build_schema_context", lambda _uid, _did: "")

    monkeypatch.setattr(
        introspection_tools, "svc_get_tables", lambda _uid, _did, _conn_str: ["users", "orders"]
    )

    result = react_agent.run_agent_question(
        sentence="what tables exist", user_id=user_id, db_id=db_id
    )

    assert result["type"] == "answer"
    assert "2 tables" in result["answer"]

    tool_calls = [tc for tc in result["toolCalls"] if tc["name"] == "list_tables"]
    assert tool_calls, "list_tables was never invoked"
    call = tool_calls[0]

    # THE CONTRACT: session params present even though the LLM omitted them.
    assert call["args"]["user_id"] == user_id
    assert call["args"]["db_id"] == db_id

    # The tool really ran (a table list came back), so validation passed
    # — NOT the swallowed `Error: ...` path.
    assert "Error:" not in str(call["result"])
    assert "users" in str(call["result"])


def test_agent_blocks_write_intent_without_llm(_fresh_settings):
    """Write-intent sentences are refused deterministically, before any LLM call."""
    from ai.agents import react_agent

    result = react_agent.run_agent_question(
        sentence="delete all rows from users", user_id=1, db_id=1
    )
    assert result["type"] == "answer"
    assert "read-only" in result["answer"].lower()
    assert result["toolCalls"] == []
