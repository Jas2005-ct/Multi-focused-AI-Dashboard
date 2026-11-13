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

    # The table names must reach the client: list_tables is the only source
    # of them, and the UI renders them as tags.
    assert result["tables"] == ["orders", "users"]


def test_agent_blocks_write_intent_without_llm(_fresh_settings):
    """Write-intent sentences are refused deterministically, before any LLM call."""
    from ai.agents import react_agent

    result = react_agent.run_agent_question(
        sentence="delete all rows from users", user_id=1, db_id=1
    )
    assert result["type"] == "answer"
    assert "read-only" in result["answer"].lower()
    assert result["toolCalls"] == []


class _FakeTool:
    """Stand-in for a StructuredTool with a canned result.

    The agent builds its tool map from `react_agent.ALL_TOOLS`, which is bound
    at import time, so the module-level tools cannot be swapped by patching
    `ai.tools.introspection` — this replaces the map's contents instead.
    """

    def __init__(self, name: str, result):
        self.name = name
        self._result = result

    def invoke(self, args):
        return self._result


def test_agent_returns_structured_rows_from_query_tool(app_client, seeded_connection, monkeypatch):
    """The agent must surface the rows it fetched, not only prose.

    Historical behaviour: `rows` / `count` / `tables` were hard-coded empty on
    the agent path, so the UI had nothing to render and the model had to
    re-type the rows into a markdown table inside its answer.
    """
    from ai.agents import react_agent

    user_id, db_id = seeded_connection

    scripted = _ScriptedLLM(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "run_sql_query",
                        "args": {"query": "SELECT id, name FROM users"},
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="There is one user row."),
        ]
    )
    monkeypatch.setattr(react_agent, "get_llm", lambda **_kw: scripted)
    monkeypatch.setattr(react_agent, "_build_schema_context", lambda _uid, _did: "")
    monkeypatch.setattr(
        react_agent,
        "ALL_TOOLS",
        [_FakeTool("run_sql_query", [{"id": 1, "name": "jaswant"}])],
    )

    result = react_agent.run_agent_question(sentence="show the users", user_id=user_id, db_id=db_id)

    assert result["type"] == "answer"
    assert result["rows"] == [{"id": 1, "name": "jaswant"}]
    assert result["count"] == 1
    # run_sql_query takes a raw query, so the source table is unknown and
    # must not be guessed.
    assert result["table"] is None


def test_agent_reports_table_total_separately_from_returned_rows(
    app_client, seeded_connection, monkeypatch
):
    """`count_rows` is a table total; `sample_rows` is a page of rows.

    The API exposes a single `count` field, so it carries the larger total and
    the client renders "showing N of M". Returning just len(rows) would claim
    a table with 10,000 rows has 20.
    """
    from ai.agents import react_agent

    user_id, db_id = seeded_connection

    scripted = _ScriptedLLM(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "count_rows", "args": {"table_name": "users"}, "id": "c1"},
                    {
                        "name": "sample_rows",
                        "args": {"table_name": "users", "limit": 20},
                        "id": "c2",
                    },
                ],
            ),
            AIMessage(content="There are users."),
        ]
    )
    monkeypatch.setattr(react_agent, "get_llm", lambda **_kw: scripted)
    monkeypatch.setattr(react_agent, "_build_schema_context", lambda _uid, _did: "")
    monkeypatch.setattr(
        react_agent,
        "ALL_TOOLS",
        [
            _FakeTool("count_rows", 10_000),
            _FakeTool("sample_rows", [{"id": i} for i in range(20)]),
        ],
    )

    result = react_agent.run_agent_question(
        sentence="how many users are there", user_id=user_id, db_id=db_id
    )

    assert len(result["rows"]) == 20
    assert result["count"] == 10_000
    assert "users" in result["tables"]
    # sample_rows names its table, so the client can caption the table.
    assert result["table"] == "users"
