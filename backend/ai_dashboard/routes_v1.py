"""API v1 routes — standardized contracts with OpenAPI docs (Phase 5)."""

import logging

from flask import g
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ai.agents.sql_chain import get_query_format as lcel_get_query_format
from ai_dashboard.chains.introspection_chain import get_routed_query_format
from ai_dashboard.schemas import (
    AIQueryRequest,
    DBConnectionRequest,
    PromptRequest,
)
from auths.models import User, db
from common.responses import error_response, success_response
from connections.model import DBConnection
from connections.service import (
    delete_connection,
    format_schema_for_llm,
    get_connection,
    get_connection_with_tables,
    get_full_schema,
    get_table_schema,
    get_tables,
    list_connections,
    save_connection,
    test_connection,
)
from security.dec import require_auth

logger = logging.getLogger(__name__)


# ==================== Path parameter models ====================
# flask-openapi3 binds URL rule variables (e.g. <int:db_id>) to the view
# function by name. Declaring them in a Pydantic model keeps the signature
# self-documenting and lets OpenAPI render the parameters as path params.


class ConnectionPath(BaseModel):
    db_id: int = Field(..., description="Database connection ID")


class TablePath(BaseModel):
    db_id: int = Field(..., description="Database connection ID")
    table_name: str = Field(..., description="Table name")


# v1 blueprint with /api/v1 prefix
v1 = APIBlueprint("services_v1", __name__, url_prefix="/api/v1", abp_security=[{"jwt": []}])
conn_tags = Tag(name="Database Connections", description="Database Connection management")
ai_tags = Tag(name="AI Assistant", description="AI-powered SQL generation and data answers")


def _db_error_response(exc: Exception, status: int = 502):
    """Turn a target-database failure into a readable 502 instead of a generic 500.

    The driver message ("could not translate host name ...", "password
    authentication failed", ...) is actionable for the user, so it is surfaced
    instead of being swallowed by the generic 500 handler.
    """
    logger.warning("Target database error: %s", exc)
    return error_response("Database unreachable", str(exc), status)


# ==================== AI Query ====================


@v1.post(
    "/ai/query",
    tags=[ai_tags],
    summary="AI-powered SQL generation or data answers",
    responses={
        200: {"description": "Success - SQL query or natural language answer"},
        400: {"description": "Bad request - invalid input"},
        401: {"description": "Unauthorized - authentication required"},
        500: {"description": "Internal server error"},
    },
)
@require_auth
def ai_query_v1(body: AIQueryRequest):
    """AI-powered SQL generation or data answers via LangGraph agent or LCEL chain.

    Modes:
    - auto: LangGraph ReAct agent (default) — decides which tool to call
    - sql: LCEL chain for direct SQL generation
    - answer: Data-only mode (agent with answer-only output)
    """
    try:
        # Fetch schema context if connection_id provided
        schema_context = None
        if body.connection_id:
            user_record = db.session.get(User, g.user_id)
            if user_record:
                conn = db.session.get(DBConnection, body.connection_id)
                if conn and conn.user_id == user_record.id:
                    try:
                        schema = get_full_schema(
                            user_record.id,
                            body.connection_id,
                            conn.get_decrypted_connection_string(),
                        )
                        schema_context = format_schema_for_llm(schema)
                    except Exception as e:
                        logger.warning(f"Failed to fetch schema: {e!s}")

        if body.mode == "sql":
            # Direct LCEL chain for SQL generation
            result = lcel_get_query_format(
                body.query,
                schema_context=schema_context,
            )
            if "error" in result:
                error_type = result.get("error_type")
                status_code = (
                    500
                    if error_type == "api_error"
                    else (401 if error_type == "auth_error" else 400)
                )
                return error_response(result["error"], status=status_code)
            return success_response(
                {
                    "type": "query",
                    "sql": result.get("sql") or result.get("output_query"),
                    "metadata": result.get("metadata", {}),
                }
            )

        # Agent mode (auto or answer)
        result = get_routed_query_format(
            PromptRequest(sentence=body.query, db_id=body.connection_id),
            user_id=g.user_id,
            db_id=body.connection_id,
            schema_context=schema_context,
        )

        if "error" in result:
            error_type = result.get("error_type")
            status_code = (
                500 if error_type == "api_error" else (401 if error_type == "auth_error" else 400)
            )
            return error_response(result["error"], status=status_code)

        if result.get("type") == "answer":
            return success_response(
                {
                    "type": "answer",
                    "answer": result["answer"],
                    "tables": result.get("tables", []),
                    "count": result.get("count"),
                    "rows": result.get("rows", []),
                    "table": result.get("table"),
                    "toolCalls": result.get("toolCalls", []),
                    "usage": result.get("usage"),
                }
            )

        return success_response(
            {
                "type": "query",
                "sql": result.get("output_query") or result.get("sql"),
                "metadata": result.get("metadata", {}),
                "toolCalls": result.get("toolCalls", []),
                "usage": result.get("usage"),
            }
        )

    except Exception:
        logger.exception("AI query failed")
        return error_response("Internal server error", status=500)


# ==================== Database Connections ====================


@v1.post(
    "/connections",
    tags=[conn_tags],
    summary="Create a new database connection",
    responses={
        200: {"description": "Connection saved successfully"},
        400: {"description": "Bad request - invalid input"},
        401: {"description": "Unauthorized"},
        500: {"description": "Internal server error"},
    },
)
@require_auth
def create_connection_v1(body: DBConnectionRequest):
    """Save a new database connection for the authenticated user."""
    try:
        conn = save_connection(
            user_id=g.user_id,
            host=body.host,
            port=body.port,
            database=body.database,
            username=body.username,
            password=body.password,
            db_type=body.db_type,
            connection_string=body.connection_string,
            name=body.name,
            sslmode=body.sslmode,
        )
        return success_response(
            {
                "id": conn.id,
                "name": conn.name,
                "host": conn.host,
                "port": conn.port,
                "database": conn.database,
                "username": conn.username,
                "db_type": conn.db_type,
                "sslmode": conn.sslmode,
                "created_at": conn.created_at.isoformat() if conn.created_at else None,
                "last_used": conn.last_used.isoformat() if conn.last_used else None,
            },
            "Connection saved successfully",
        )
    except ValueError as e:
        return error_response(str(e), status=400)
    except Exception:
        logger.exception("Failed to save connection")
        return error_response("Failed to save connection", status=500)


@v1.get(
    "/connections",
    tags=[conn_tags],
    summary="List database connections with pagination",
    responses={
        200: {"description": "Paginated list of connections"},
        401: {"description": "Unauthorized"},
    },
)
@require_auth
def get_connections_v1(page: int = 1, per_page: int = 20):
    """List all saved connections for the authenticated user with pagination."""
    result = list_connections(g.user_id, page=page, per_page=per_page)
    return success_response(
        {
            "page": result["page"],
            "per_page": result["per_page"],
            "total": result["total"],
            "pages": result["pages"],
            "connections": [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "host": c["host"],
                    "port": c["port"],
                    "database": c["database"],
                    "username": c["username"],
                    "db_type": c["db_type"],
                    "sslmode": c["sslmode"],
                    "created_at": c["created_at"],
                    "last_used": c["last_used"],
                }
                for c in result["connections"]
            ],
        }
    )


@v1.get(
    "/connections/<int:db_id>",
    tags=[conn_tags],
    summary="Get a specific connection with table list",
    responses={
        200: {"description": "Connection details with tables"},
        404: {"description": "Connection not found"},
        401: {"description": "Unauthorized"},
    },
)
@require_auth
def get_connection_detail_v1(path: ConnectionPath):
    """Get a specific connection by ID with table list."""
    try:
        result = get_connection_with_tables(g.user_id, path.db_id)
    except ConnectionError as e:
        # Target database unreachable / bad credentials — surface the reason.
        return _db_error_response(e)
    if not result:
        return error_response("Connection not found", status=404)
    return success_response(
        {
            "id": result["id"],
            "name": result["name"],
            "host": result["host"],
            "port": result["port"],
            "database": result["database"],
            "username": result["username"],
            "db_type": result["db_type"],
            "sslmode": result["sslmode"],
            "created_at": result["created_at"],
            "last_used": result["last_used"],
            "tables": result["tables"],
        }
    )


@v1.delete(
    "/connections/<int:db_id>",
    tags=[conn_tags],
    summary="Delete a database connection",
    responses={
        200: {"description": "Connection deleted"},
        404: {"description": "Connection not found"},
        401: {"description": "Unauthorized"},
    },
)
@require_auth
def delete_connection_v1(path: ConnectionPath):
    """Delete a saved database connection."""
    ok = delete_connection(g.user_id, path.db_id)
    if not ok:
        return error_response("Connection not found", status=404)
    return success_response(None, "Connection deleted successfully")


@v1.post(
    "/connections/<int:db_id>/test",
    tags=[conn_tags],
    summary="Test a database connection",
    responses={
        200: {"description": "Test result"},
        404: {"description": "Connection not found"},
        401: {"description": "Unauthorized"},
    },
)
@require_auth
def test_connection_v1(path: ConnectionPath):
    """Test if a saved connection is valid.

    A failed connection is a *successful* test run with a negative result, so it
    answers 200 with ``success: false`` and the driver's message. That keeps the
    client on its normal response path instead of the generic error path, and
    lets the UI show the actual reason (bad host, refused login, timeout).
    """
    result = test_connection(g.user_id, path.db_id)
    if "Connection not found" in result.get("message", ""):
        return error_response(result["message"], status=404)
    if result["success"]:
        return success_response(
            {"success": True, "message": result["message"]},
            "Connection successful",
        )
    return success_response(
        {"success": False, "message": result["message"]},
        "Connection failed",
    )


@v1.get(
    "/connections/<int:db_id>/tables",
    tags=[conn_tags],
    summary="Get tables for a connection",
    responses={
        200: {"description": "List of tables"},
        404: {"description": "Connection not found"},
        401: {"description": "Unauthorized"},
    },
)
@require_auth
def get_tables_v1(path: ConnectionPath):
    """Get list of tables for a connection."""
    conn = get_connection(g.user_id, path.db_id)
    if not conn:
        return error_response("Connection not found", status=404)
    conn_str = conn.get_decrypted_connection_string()
    try:
        tables = get_tables(g.user_id, path.db_id, conn_str)
    except Exception as e:  # noqa: BLE001 -- driver errors are user-facing
        return _db_error_response(e)
    return success_response({"tables": tables})


@v1.get(
    "/connections/<int:db_id>/tables/<table_name>",
    tags=[conn_tags],
    summary="Get schema for a specific table",
    responses={
        200: {"description": "Table schema"},
        404: {"description": "Not found"},
        401: {"description": "Unauthorized"},
    },
)
@require_auth
def get_table_schema_v1(path: TablePath):
    """Get schema for a specific table."""
    conn = get_connection(g.user_id, path.db_id)
    if not conn:
        return error_response("Connection not found", status=404)
    conn_str = conn.get_decrypted_connection_string()
    try:
        schema = get_table_schema(g.user_id, path.db_id, conn_str, path.table_name)
    except Exception as e:  # noqa: BLE001 -- driver errors are user-facing
        return _db_error_response(e)
    return success_response(schema)
