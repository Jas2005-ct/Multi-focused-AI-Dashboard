"""API v1 routes — standardized contracts with OpenAPI docs (Phase 5)."""

from flask import request
from flask_openapi3 import APIBlueprint, Tag

from ai_dashboard.schemas import (
    PromptRequest, SelectConnectionRequest, DeleteConnectionRequest,
    AIQueryRequest, AIQueryResponse, DBConnectionRequest
)
from connections.model import DBConnection
from auths.models import db, User
from ai_dashboard.chains.introspection_chain import get_routed_query_format
from ai_dashboard.chains.sql_chain import get_query_format as lcel_get_query_format
from connections.service import (
    parse_connection_string,
    build_connection_string,
    connection_pool,
    get_tables,
    get_full_schema,
    format_schema_for_llm,
    save_connection,
    test_connection,
    delete_connection,
    list_connections,
    get_connection,
    get_connection_with_tables,
    get_table_schema,
)
from security.dec import require_auth
from flask_openapi3 import APIBlueprint, Tag
from flask import g
import json
import logging

from common.responses import success_response, error_response

logger = logging.getLogger(__name__)

# v1 blueprint with /api/v1 prefix
v1 = APIBlueprint('services_v1', __name__, url_prefix='/api/v1', abp_security=[{"jwt": []}])
sql_tags = Tag(name='SQL Query', description='SQL Query operations')
conn_tags = Tag(name='Database Connections', description='Database Connection management')
ai_tags = Tag(name='AI Assistant', description='AI-powered SQL generation and data answers')
health_tags = Tag(name='Health', description='Service health and readiness')

DEPRECATION_HEADER = "Warning: This endpoint is deprecated. Use /api/v1/ instead."


def _add_deprecation(resp):
    """Add deprecation header to response."""
    resp.headers["Deprecation"] = "true"
    resp.headers["Link"] = '<https://api.example.com/api/v1/>; rel="successor-version"'
    return resp


# ==================== Health ====================

@v1.get('/health',
        tags=[health_tags],
        summary='Liveness probe',
        responses={200: {"description": "Service healthy"}, 503: {"description": "Service unhealthy"}})
def health_v1():
    """Liveness probe — can we reach the database?"""
    from sqlalchemy import text
    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return success_response({"status": "ok", "database": "connected"})
    except Exception:
        return error_response("Service unavailable", "Database connection failed", 503)


@v1.get('/ready',
        tags=[health_tags],
        summary='Readiness probe',
        responses={200: {"description": "Service ready"}, 503: {"description": "Service not ready"}})
def ready_v1():
    """Readiness probe — deeper checks."""
    checks = {"database": "connected" if _db_ok() else "error"}
    ok = all(v == "connected" for v in checks.values())
    return (success_response({"status": "ready", "checks": checks}) 
            if ok else 
            error_response("Not ready", "Service not ready", 503, details=checks))


def _db_ok() -> bool:
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# ==================== AI Query ====================

@v1.post('/ai/query',
         tags=[ai_tags],
         summary='AI-powered SQL generation or data answers',
         responses={
             200: {"description": "Success - SQL query or natural language answer"},
             400: {"description": "Bad request - invalid input"},
             401: {"description": "Unauthorized - authentication required"},
             500: {"description": "Internal server error"}
         })
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
            user_record = User.query.get(g.user_id)
            if user_record:
                conn = DBConnection.query.get(body.connection_id)
                if conn and conn.user_id == user_record.id:
                    try:
                        schema = get_full_schema(user_record.id, body.connection_id, conn.get_decrypted_connection_string())
                        schema_context = format_schema_for_llm(schema)
                    except Exception as e:
                        logger.warning(f"Failed to fetch schema: {str(e)}")

        if body.mode == "sql":
            # Direct LCEL chain for SQL generation
            result = lcel_get_query_format(PromptRequest(sentence=body.query, db_id=body.connection_id), schema_context=schema_context)
            if "error" in result:
                error_type = result.get("error_type")
                status_code = 500 if error_type == "api_error" else (401 if error_type == "auth_error" else 400)
                return error_response(result["error"], status_code=status_code)
            return success_response({
                "type": "query",
                "sql": result.get("sql") or result.get("output_query"),
                "metadata": result.get("metadata", {}),
            })

        # Agent mode (auto or answer)
        from ai_dashboard.chains.introspection_chain import get_routed_query_format
        from ai_dashboard.schemas import PromptRequest
        result = get_routed_query_format(
            PromptRequest(sentence=body.query, db_id=body.connection_id),
            user_id=g.user_id,
            db_id=body.connection_id,
            schema_context=schema_context
        )

        if "error" in result:
            error_type = result.get("error_type")
            status_code = 500 if error_type == "api_error" else (401 if error_type == "auth_error" else 400)
            return error_response(result["error"], status_code=status_code)

        if result.get("type") == "answer":
            return success_response({
                "type": "answer",
                "answer": result["answer"],
                "tables": result.get("tables", []),
                "count": result.get("count"),
                "rows": result.get("rows", []),
                "table": result.get("table"),
                "toolCalls": result.get("toolCalls", []),
                "usage": result.get("usage"),
            })

        return success_response({
            "type": "query",
            "sql": result.get("output_query") or result.get("sql"),
            "metadata": result.get("metadata", {}),
            "toolCalls": result.get("toolCalls", []),
            "usage": result.get("usage"),
        })

    except Exception as e:
        logger.exception("AI query failed")
        return error_response("Internal server error", status=500)


# ==================== SQL Query (Legacy Shim) ====================

@v1.post('/sql-query/',
         tags=[sql_tags],
         summary='Generate SQL query or answer (legacy shim)',
         deprecated=True,
         responses={
             200: {"description": "Success - SQL query or metadata answer"},
             400: {"description": "Bad request - invalid input"},
             401: {"description": "Unauthorized"},
             500: {"description": "Internal server error"}
         })
@require_auth
def optimize_v1(body: PromptRequest):
    """Legacy endpoint — use POST /api/v1/ai/query instead.

    Generates optimized SQL query or answers metadata via tools.
    """
    try:
        schema_context = None
        if body.db_id:
            user_record = User.query.get(g.user_id)
            if user_record:
                conn = DBConnection.query.get(body.db_id)
                if conn and conn.user_id == user_record.id:
                    try:
                        schema = get_full_schema(user_record.id, body.db_id, conn.get_decrypted_connection_string())
                        schema_context = format_schema_for_llm(schema)
                    except Exception as e:
                        logger.warning(f"Failed to fetch schema: {str(e)}")

        result = get_routed_query_format(
            body, user_id=g.user_id, db_id=body.db_id, schema_context=schema_context
        )

        if "error" in result:
            error_type = result.get("error_type")
            status_code = 500 if error_type == "api_error" else (401 if error_type == "auth_error" else 400)
            return error_response(result["error"], status_code=status_code)

        if result.get("type") == "answer":
            return success_response({
                "type": "answer",
                "answer": result["answer"],
                "tables": result.get("tables", []),
                "count": result.get("count"),
                "rows": result.get("rows", []),
                "table": result.get("table"),
                "toolCalls": result.get("toolCalls", []),
                "output_query": None,
            })

        return success_response({
            "type": "query",
            "sql": result["output_query"],
            "metadata": result.get("metadata", {}),
        })

    except json.JSONDecodeError as e:
        return error_response(f"Invalid JSON format: {str(e)}", status=400)
    except Exception as e:
        logger.exception("SQL query failed")
        return error_response("Internal server error", status=500)


# ==================== Database Connections ====================

@v1.post('/connections',
         tags=[conn_tags],
         summary='Create a new database connection',
         responses={
             200: {"description": "Connection saved successfully"},
             400: {"description": "Bad request - invalid input"},
             401: {"description": "Unauthorized"},
             500: {"description": "Internal server error"}
         })
@require_auth
def create_connection_v1(body: DBConnectionRequest):
    """Save a new database connection for the authenticated user."""
    try:
        from connections.service import save_connection
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
        return success_response({
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
        }, "Connection saved successfully")
    except ValueError as e:
        return error_response(str(e), status=400)
    except Exception as e:
        logger.exception("Failed to save connection")
        return error_response("Failed to save connection", status=500)


@v1.get('/connections',
        tags=[conn_tags],
        summary='List database connections with pagination',
        responses={
            200: {"description": "Paginated list of connections"},
            401: {"description": "Unauthorized"}
        })
@require_auth
def get_connections_v1(page: int = 1, per_page: int = 20):
    """List all saved connections for the authenticated user with pagination."""
    from connections.service import list_connections
    result = list_connections(g.user_id, page=page, per_page=per_page)
    return success_response({
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
        ]
    })


@v1.get('/connections/<int:db_id>',
        tags=[conn_tags],
        summary='Get a specific connection with table list',
        responses={
            200: {"description": "Connection details with tables"},
            404: {"description": "Connection not found"},
            401: {"description": "Unauthorized"}
        })
@require_auth
def get_connection_detail_v1(path_db_id: int):
    """Get a specific connection by ID with table list."""
    from connections.service import get_connection_with_tables
    result = get_connection_with_tables(g.user_id, path_db_id)
    if not result:
        return error_response("Connection not found", status=404)
    return success_response({
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
    })


@v1.delete('/connections/<int:db_id>',
           tags=[conn_tags],
           summary='Delete a database connection',
           responses={
               200: {"description": "Connection deleted"},
               404: {"description": "Connection not found"},
               401: {"description": "Unauthorized"}
           })
@require_auth
def delete_connection_v1(path_db_id: int):
    """Delete a saved database connection."""
    from connections.service import delete_connection
    ok = delete_connection(g.user_id, path_db_id)
    if not ok:
        return error_response("Connection not found", status=404)
    return success_response(None, "Connection deleted successfully")


@v1.post('/connections/<int:db_id>/test',
         tags=[conn_tags],
         summary='Test a database connection',
         responses={
             200: {"description": "Test result"},
             404: {"description": "Connection not found"},
             401: {"description": "Unauthorized"}
         })
@require_auth
def test_connection_v1(path_db_id: int):
    """Test if a saved connection is valid."""
    from connections.service import test_connection
    result = test_connection(g.user_id, path_db_id)
    if "Connection not found" in result.get("message", ""):
        return error_response(result["message"], status=404)
    return (success_response(result) if result["success"] else error_response(result["message"], status=500))


@v1.get('/connections/<int:db_id>/tables',
        tags=[conn_tags],
        summary='Get tables for a connection',
        responses={
            200: {"description": "List of tables"},
            404: {"description": "Connection not found"},
            401: {"description": "Unauthorized"}
        })
@require_auth
def get_tables_v1(path_db_id: int):
    """Get list of tables for a connection."""
    from connections.service import get_connection, get_tables
    conn = get_connection(g.user_id, path_db_id)
    if not conn:
        return error_response("Connection not found", status=404)
    conn_str = conn.get_decrypted_connection_string()
    tables = get_tables(g.user_id, path_db_id, conn_str)
    return success_response({"tables": tables})


@v1.get('/connections/<int:db_id>/tables/<table_name>',
        tags=[conn_tags],
        summary='Get schema for a specific table',
        responses={
            200: {"description": "Table schema"},
            404: {"description": "Not found"},
            401: {"description": "Unauthorized"}
        })
@require_auth
def get_table_schema_v1(path_db_id: int, path_table_name: str):
    """Get schema for a specific table."""
    from connections.service import get_connection, get_table_schema
    conn = get_connection(g.user_id, path_db_id)
    if not conn:
        return error_response("Connection not found", status=404)
    conn_str = conn.get_decrypted_connection_string()
    schema = get_table_schema(g.user_id, path_db_id, conn_str, path_table_name)
    return success_response(schema)