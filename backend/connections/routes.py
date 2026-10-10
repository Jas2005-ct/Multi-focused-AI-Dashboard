"""Connection routes (Phase 3) - RESTful /api/v1/connections."""

from flask import g
from flask_openapi3 import APIBlueprint, Tag

from security.dec import require_auth
from connections.service import (
    save_connection,
    list_connections,
    get_connection,
    get_connection_with_tables,
    test_connection,
    delete_connection,
    get_tables,
    get_table_schema,
)
from connections.schemas import (
    ConnectionCreate,
    ConnectionResponse,
    ConnectionDetailResponse,
    PaginatedConnections,
    ConnectionTestResponse,
    TablesResponse,
    TableSchemaResponse,
)

api = APIBlueprint("connections", __name__, url_prefix="/api/v1", abp_security=[{"jwt": []}])
connections_tag = Tag(name="Database Connections", description="Database Connection management")


@api.post(
    "/connections",
    tags=[connections_tag],
    summary="Create a new database connection",
    responses={
        200: ConnectionResponse,
        400: {"description": "Validation error"},
        401: {"description": "Unauthorized"},
        500: {"description": "Server error"},
    },
)
@require_auth
def create_connection(body: ConnectionCreate):
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
        return ConnectionResponse(
            id=conn.id,
            name=conn.name,
            host=conn.host,
            port=conn.port,
            database=conn.database,
            username=conn.username,
            db_type=conn.db_type,
            sslmode=conn.sslmode,
            created_at=conn.created_at.isoformat() if conn.created_at else None,
            last_used=conn.last_used.isoformat() if conn.last_used else None,
        ), 200
    except ValueError as e:
        return {"success": False, "message": str(e)}, 400
    except Exception as e:
        return {"success": False, "message": f"Failed to save connection: {e}"}, 500


@api.get(
    "/connections",
    tags=[connections_tag],
    summary="List database connections with pagination",
    responses={200: PaginatedConnections, 401: {"description": "Unauthorized"}},
)
@require_auth
def get_connections(query_page: int = 1, query_per_page: int = 20):
    """List all saved connections for the authenticated user with pagination."""
    result = list_connections(g.user_id, page=query_page, per_page=query_per_page)
    return PaginatedConnections(
        page=result["page"],
        per_page=result["per_page"],
        total=result["total"],
        pages=result["pages"],
        connections=[
            ConnectionResponse(
                id=c["id"],
                name=c["name"],
                host=c["host"],
                port=c["port"],
                database=c["database"],
                username=c["username"],
                db_type=c["db_type"],
                sslmode=c["sslmode"],
                created_at=c["created_at"],
                last_used=c["last_used"],
            )
            for c in result["connections"]
        ],
    ), 200


@api.get(
    "/connections/<int:db_id>",
    tags=[connections_tag],
    summary="Get a specific connection with table list",
    responses={200: ConnectionDetailResponse, 404: {"description": "Not found"}, 401: {"description": "Unauthorized"}},
)
@require_auth
def get_connection_detail(path_db_id: int):
    """Get a specific connection by ID with table list."""
    from connections.service import get_connection_with_tables

    result = get_connection_with_tables(g.user_id, path_db_id)
    if not result:
        return {"success": False, "message": "Connection not found"}, 404

    return ConnectionDetailResponse(
        id=result["id"],
        name=result["name"],
        host=result["host"],
        port=result["port"],
        database=result["database"],
        username=result["username"],
        db_type=result["db_type"],
        sslmode=result["sslmode"],
        created_at=result["created_at"],
        last_used=result["last_used"],
        tables=result["tables"],
    ), 200


@api.delete(
    "/connections/<int:db_id>",
    tags=[connections_tag],
    summary="Delete a database connection",
    responses={200: {"description": "Deleted"}, 404: {"description": "Not found"}, 401: {"description": "Unauthorized"}},
)
@require_auth
def delete_connection_route(path_db_id: int):
    """Delete a saved connection."""
    from connections.service import delete_connection

    ok = delete_connection(g.user_id, path_db_id)
    if not ok:
        return {"success": False, "message": "Connection not found"}, 404
    return {"success": True, "message": "Connection deleted successfully"}, 200


@api.post(
    "/connections/<int:db_id>/test",
    tags=[connections_tag],
    summary="Test a database connection",
    responses={200: ConnectionTestResponse, 404: {"description": "Not found"}, 401: {"description": "Unauthorized"}},
)
@require_auth
def test_connection_route(path_db_id: int):
    """Test if a saved connection is valid."""
    from connections.service import test_connection

    result = test_connection(g.user_id, path_db_id)
    if "Connection not found" in result.get("message", ""):
        return result, 404
    return result, 200 if result["success"] else 500


@api.get(
    "/connections/<int:db_id>/tables",
    tags=[connections_tag],
    summary="Get tables for a connection",
    responses={200: TablesResponse, 404: {"description": "Not found"}, 401: {"description": "Unauthorized"}},
)
@require_auth
def get_tables_route(path_db_id: int):
    """Get list of tables for a connection."""
    from connections.service import get_connection, get_tables

    conn = get_connection(g.user_id, path_db_id)
    if not conn:
        return {"success": False, "message": "Connection not found"}, 404

    conn_str = conn.get_decrypted_connection_string()
    tables = get_tables(g.user_id, path_db_id, conn_str)
    return TablesResponse(tables=tables), 200


@api.get(
    "/connections/<int:db_id>/tables/<table_name>",
    tags=[connections_tag],
    summary="Get schema for a specific table",
    responses={200: TableSchemaResponse, 404: {"description": "Not found"}, 401: {"description": "Unauthorized"}},
)
@require_auth
def get_table_schema_route(path_db_id: int, path_table_name: str):
    """Get schema for a specific table."""
    from connections.service import get_connection, get_table_schema

    conn = get_connection(g.user_id, path_db_id)
    if not conn:
        return {"success": False, "message": "Connection not found"}, 404

    conn_str = conn.get_decrypted_connection_string()
    schema = get_table_schema(g.user_id, path_db_id, conn_str, path_table_name)
    return TableSchemaResponse(**schema), 200