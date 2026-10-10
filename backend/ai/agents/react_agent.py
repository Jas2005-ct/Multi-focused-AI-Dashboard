"""LangGraph ReAct agent for database introspection (Phase 4).

Main agent entry point. Uses create_react_agent with our StructuredTools.
Falls back to LCEL SQL chain if model lacks tool support.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from ai.llm_factory import get_llm
from ai.guards import is_write_intent
from ai.tools.introspection import ALL_TOOLS

logger = logging.getLogger(__name__)

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

MAX_ITERATIONS = 6


def _build_schema_context(user_id: int, db_id: int) -> str:
    """Fetch and format full schema for LLM context."""
    try:
        from ai.tools.introspection import get_full_schema
        schema = get_full_schema.invoke({"user_id": user_id, "db_id": db_id})
        from ai_dashboard.db_connections import format_schema_for_llm
        return format_schema_for_llm(schema)
    except Exception:
        return ""


def run_agent_question(
    sentence: str,
    user_id: int,
    db_id: int,
    schema_context: str = "",
) -> Dict[str, Any]:
    """Run the ReAct agent for a free-form DB question.

    Returns:
        {"type": "answer", "answer": str, "toolCalls": [...], "tables": [], "rows": [], "count": None, "table": None}
    """
    # Block write operations — read-only mode
    if is_write_intent(sentence):
        logger.warning(f"BLOCKED write intent sentence={sentence!r} user_id={user_id} db_id={db_id}")
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

    # Build tool map
    tool_map = {t.name: t for t in ALL_TOOLS}
    trace: List[Dict[str, Any]] = []

    logger.info("AGENT START sentence=%r user_id=%s db_id=%s", sentence, user_id, db_id)
    logger.info("AGENT TOOLS available: %s", ", ".join(t.name for t in ALL_TOOLS))

    try:
        llm = get_llm(temperature=0, max_tokens=2000)
        llm_with_tools = llm.bind_tools(ALL_TOOLS)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=sentence),
        ]

        for step in range(1, MAX_ITERATIONS + 1):
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
                except Exception as e:
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

        # Exceeded max iterations
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
            f"LangGraph agent failed for user={user_id} db={db_id}: {e}; "
            f"falling back to LCEL SQL chain"
        )
        from ai.agents.sql_chain import get_query_format as lcel_get_query_format
        from ai_dashboard.schemas import PromptRequest

        res = lcel_get_query_format(PromptRequest(sentence=sentence, db_id=db_id))
        if "sql" in res:
            res["type"] = "query"
        res["toolCalls"] = trace
        return res