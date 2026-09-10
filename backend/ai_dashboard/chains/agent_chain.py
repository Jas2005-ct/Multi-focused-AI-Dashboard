"""Professional tool-calling agent built with langchain_core only.

This module demonstrates the MODERN LangChain agent pattern (Tool Calling)
without requiring the heavy `langchain` package:

    1. Bind tools to the chat model via .bind_tools()
    2. Loop:
         model -> tool_calls -> execute each tool -> feed results back
    3. When the model stops calling tools, its message is the final answer.

The loop is the same one AgentExecutor runs internally. Building it by hand
is the best way to *understand* agents before reaching for the abstraction.

Tools available to the agent:
    - list_tables        : DB structure
    - count_rows         : per-table row count
    - sample_rows        : sample rows from a table
    - describe_table     : column metadata
    - run_sql_query      : execute a read-only SQL query (safety-checked)

If the underlying model does not support tool calling (e.g. some free
models on OpenRouter), the whole thing falls back to the deterministic
SQL-generation chain so the endpoint never breaks.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool as lc_tool

from ai_dashboard.chains.llm import get_llm
from ai_dashboard.tools.introspection import (
    _resolve_connection,
    count_rows_tool,
    describe_table_tool,
    get_full_schema_tool,
    list_tables_tool,
    sample_rows_tool,
)
from ai_dashboard.db_connections import connection_pool, format_schema_for_llm
from sqlalchemy import text

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(_h)

TOOL_LOG = logging.getLogger(f"{__name__}.tools")
TOOL_LOG.setLevel(logging.INFO)
if not TOOL_LOG.handlers:
    _th = logging.StreamHandler()
    _th.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s TOOL %(name)s: %(message)s"))
    TOOL_LOG.addHandler(_th)

_WRITE_RE = re.compile(
    r"\b(insert|update|delete|create|alter|drop|truncate|replace|upsert|merge)\b",
    re.IGNORECASE,
)


def _is_write_intent(sentence: str) -> bool:
    """Detect write operations — all writes are blocked in read-only mode."""
    if not sentence:
        return False
    return bool(_WRITE_RE.search(sentence))


def _build_schema_context(user_id: int, db_id: int) -> str:
    """Fetch and format full schema for LLM context."""
    try:
        from ai_dashboard.tools.introspection import get_full_schema_tool
        schema = get_full_schema_tool.invoke({"user_id": user_id, "db_id": db_id})
        return format_schema_for_llm(schema)
    except Exception:
        return ""


SYSTEM_PROMPT = """You are a read-only database assistant for the user's PostgreSQL database.
You have tools to list tables, count rows, sample rows, describe tables, and run
read-only SQL. To answer the user's question, call the appropriate tool(s), inspect
the results, and then reply with a concise natural-language answer.
Only use run_sql_query for questions the other tools cannot answer.
Never invent table or column names — discover them with the tools first.
READ-ONLY: All write operations (INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, TRUNCATE, REPLACE, UPSERT, MERGE) are NOT permitted. If user asks to insert/update/delete, politely refuse without calling any tool.

Database Schema:
{schema_context}

Instructions:
- Always use exact table names from the schema above.
- Map user terms to the closest matching table by meaning (e.g., user says "resume" or "cv" → use portfolio_resume, "skills" → portfolio_skills).
- If unsure, prefer get_full_schema or list_tables first, then act.

Examples:
User: "show my resume" → Call describe_table(table_name="portfolio_resume")
User: "list all skills" → Call sample_rows(table_name="portfolio_skills", limit=20)
User: "how many projects" → Call count_rows(table_name="portfolio_projects")
User: "what tables exist" → Call list_tables()
"""


def _build_tools(user_id: int, db_id: int) -> List[Any]:
    """Create per-request tools with user_id/db_id already bound (injected)."""

    @lc_tool
    def list_tables() -> List[str]:
        """List all tables in the database. Use when asked 'what tables exist?'."""
        TOOL_LOG.info("CALL list_tables() user_id=%s db_id=%s", user_id, db_id)
        result = list_tables_tool.invoke({"user_id": user_id, "db_id": db_id})
        TOOL_LOG.info("RESULT list_tables() -> %d tables", len(result))
        return result

    @lc_tool
    def count_rows(table_name: str) -> int:
        """Count rows in a specific table. Use for 'how many X in Y table?'."""
        TOOL_LOG.info("CALL count_rows(table_name=%r) user_id=%s db_id=%s", table_name, user_id, db_id)
        result = count_rows_tool.invoke(
            {"user_id": user_id, "db_id": db_id, "table_name": table_name}
        )
        TOOL_LOG.info("RESULT count_rows(%r) -> %s", table_name, result)
        return result

    @lc_tool
    def sample_rows(table_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Return sample rows from a table. Use for 'what are the X?'."""
        TOOL_LOG.info("CALL sample_rows(table_name=%r, limit=%s) user_id=%s db_id=%s", table_name, limit, user_id, db_id)
        result = sample_rows_tool.invoke(
            {"user_id": user_id, "db_id": db_id, "table_name": table_name, "limit": limit}
        )
        TOOL_LOG.info("RESULT sample_rows(%r) -> %d rows", table_name, len(result))
        return result

    @lc_tool
    def describe_table(table_name: str) -> Dict[str, Any]:
        """Describe the columns of a table."""
        TOOL_LOG.info("CALL describe_table(table_name=%r) user_id=%s db_id=%s", table_name, user_id, db_id)
        result = describe_table_tool.invoke(
            {"user_id": user_id, "db_id": db_id, "table_name": table_name}
        )
        TOOL_LOG.info("RESULT describe_table(%r) -> %d columns", table_name, len(result.get("columns", [])) if isinstance(result, dict) else 0)
        return result

    @lc_tool
    def get_full_schema() -> Dict[str, Any]:
        """Return the full schema (all tables + columns). Use for 'describe the database'."""
        TOOL_LOG.info("CALL get_full_schema() user_id=%s db_id=%s", user_id, db_id)
        result = get_full_schema_tool.invoke({"user_id": user_id, "db_id": db_id})
        TOOL_LOG.info("RESULT get_full_schema() -> %d tables", len(result.get("tables", [])) if isinstance(result, dict) else 0)
        return result

    @lc_tool
    def run_sql_query(query: str) -> List[Dict[str, Any]]:
        """Run a read-only SQL SELECT/WITH query and return rows. For complex questions."""
        TOOL_LOG.info("CALL run_sql_query(query=%r) user_id=%s db_id=%s", query, user_id, db_id)
        from ai_dashboard.chains.sql_chain import _validate_sql_safety

        ok, err = _validate_sql_safety(query)
        if not ok:
            TOOL_LOG.error("REJECTED run_sql_query(): %s", err)
            raise ValueError(err)
        conn = _resolve_connection(user_id, db_id)
        with connection_pool.get_connection(user_id, db_id, conn.connection_string) as c:
            result = c.execute(text(query))
            cols = list(result.keys())
            rows = [dict(zip(cols, row)) for row in result.fetchall()]
            TOOL_LOG.info("RESULT run_sql_query() -> %d rows", len(rows))
            return rows[:50]

    return [list_tables, count_rows, sample_rows, describe_table, get_full_schema, run_sql_query]


def run_agent_question(
    sentence: str, user_id: int, db_id: int, schema_context: str = ""
) -> Dict[str, Any]:
    """Run the tool-calling agent for a free-form DB question.

    Returns the same dict shape as the router handlers so routes.py stays
    unchanged:
        {"type": "answer", "answer": str, ...}
    On any failure (including models without tool support) it falls back to
    the deterministic SQL-generation chain.
    """
    # Block all write operations — read-only mode, no tool calls
    if _is_write_intent(sentence):
        logger.warning("BLOCKED write intent sentence=%r user_id=%s db_id=%s", sentence, user_id, db_id)
        return {
            "type": "answer",
            "answer": "Write operation not permitted — this dashboard is read-only. INSERT/UPDATE/DELETE/CREATE/ALTER/DROP operations are blocked. Please use the Projects UI to create or modify data.",
            "toolCalls": [],
            "tables": [],
            "rows": [],
            "count": None,
            "table": None,
        }

    # Use pre-fetched schema context from routes.py, fallback to fetching if empty
    if not schema_context:
        schema_context = _build_schema_context(user_id, db_id)
    
    system_prompt = SYSTEM_PROMPT.format(schema_context=schema_context or "Unable to fetch schema")

    tools = _build_tools(user_id, db_id)
    tool_map = {t.name: t for t in tools}
    trace: List[Dict[str, Any]] = []

    logger.info("AGENT START sentence=%r user_id=%s db_id=%s", sentence, user_id, db_id)
    logger.info("AGENT TOOLS available: %s", ", ".join(t.name for t in tools))

    try:
        llm = get_llm(temperature=0, max_tokens=2000)
        llm_with_tools = llm.bind_tools(tools)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=sentence),
        ]

        for step in range(1, 7):  # max 6 iterations
            logger.info("AGENT ROUND %d — invoking LLM", step)
            ai_msg: AIMessage = llm_with_tools.invoke(messages)
            messages.append(ai_msg)

            tool_calls = getattr(ai_msg, "tool_calls", None)
            if not tool_calls:
                # Model is done calling tools -> final natural-language answer
                logger.info("AGENT ROUND %d — LLM returned final answer (%d chars), no tool calls",
                            step, len(ai_msg.content or ""))
                return {
                    "type": "answer",
                    "answer": ai_msg.content or "",
                    "toolCalls": trace,
                    "tables": [],
                    "rows": [],
                    "count": None,
                    "table": None,
                }

            logger.info("AGENT ROUND %d — LLM requested %d tool call(s): %s",
                        step, len(tool_calls),
                        ", ".join(f"{tc['name']}({json.dumps(tc.get('args', {}))})" for tc in tool_calls))

            for tc in tool_calls:
                fn = tool_map.get(tc["name"])
                args = tc.get("args", {})
                try:
                    output = fn.invoke(args) if fn else f"Unknown tool: {tc['name']}"
                except Exception as e:  # surface tool errors back to the model
                    output = f"Error: {e}"
                    logger.error("AGENT tool %s raised: %s", tc["name"], e)
                trace.append({
                    "name": tc["name"],
                    "args": args,
                    "result": output if not isinstance(output, str) else output[:500],
                })
                messages.append(
                    ToolMessage(content=str(output), tool_call_id=tc["id"])
                )

        # Exceeded max iterations: return whatever the model produced last
        logger.warning("AGENT exceeded max iterations")
        return {
            "type": "answer",
            "answer": ai_msg.content or "Could not determine a final answer.",
            "toolCalls": trace,
            "tables": [],
            "rows": [],
            "count": None,
            "table": None,
        }

    except Exception as e:
        logger.warning(
            f"Tool-calling agent failed for user={user_id} db={db_id}: {e}; "
            f"falling back to sql_chain"
        )
        from ai_dashboard.chains.sql_chain import get_query_format
        from ai_dashboard.schemas import PromptRequest

        res = get_query_format(PromptRequest(sentence=sentence, db_id=db_id))
        if "output_query" in res:
            res["type"] = "query"
        res["toolCalls"] = trace
        return res
