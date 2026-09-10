from flask import request
from ai_dashboard.schemas import QueryResponse, PromptRequest, SelectConnectionRequest, DeleteConnectionRequest
from auths.models import DBConnection, db, User
from ai_dashboard.chains.introspection_chain import get_routed_query_format
from ai_dashboard.schemas import DBConnectionRequest
from ai_dashboard.db_connections import (
    parse_connection_string, 
    build_connection_string, 
    connection_pool,
    get_tables,
    get_full_schema,
    format_schema_for_llm,
    invalidate_schema_cache,
    get_schema_cache_stats
)
from security.dec import require_auth
from flask_openapi3 import APIBlueprint, Tag
from flask import g
import json
import logging

logger = logging.getLogger(__name__)

api = APIBlueprint('services', __name__, abp_security=[{"jwt": []}])
sql_tags = Tag(name='SQL Query', description='SQL Query operations')
db_tags = Tag(name='Database Connection', description='Database Connection operations')



@api.get('/')
@require_auth
def hello():
    return f"Hello, {g.email}!"


@api.post('/sql-query/',
         tags=[sql_tags],
         description='Generate a SQL query or answer metadata questions via tools',
         responses={200: {"description": "Success - either SQL query or metadata answer", "content": {"application/json": {"schema": {"type": "object", "properties": {"success": {"type": "boolean"}, "type": {"type": "string", "enum": ["query", "answer"]}, "output_query": {"type": "string"}, "answer": {"type": "string"}, "tables": {"type": "array", "items": {"type": "string"}}, "metadata": {"type": "object"}}}}}},
                    400: {"description": "Bad request - invalid input"},
                    401: {"description": "Unauthorized - authentication required"},
                    500: {"description": "Internal server error"}})
@require_auth
def optimize(body: PromptRequest):
    """Generate optimized SQL query or answer metadata via sqlalchemy tools.
    
    Introspection sentences like 'what tables are in my db' are executed via
    tools and return a natural language answer instead of a SQL string.
    """
    try:
        # If db_id is provided, fetch schema for context (query branch only)
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
        
        # Check if result contains error
        if "error" in result:
            error_type = result.get("error_type")
            if error_type == "api_error":
                status_code = 500
            elif error_type in ("security_error", "auth_error"):
                status_code = 401 if error_type == "auth_error" else 400
            else:
                status_code = 400
            return {"success": False, "error": result["error"], "error_type": error_type, "output_query": None, "type": "error"}, status_code

        # Metadata / data answer path (via tools)
        if result.get("type") == "answer":
            return {
                "success": True,
                "type": "answer",
                "answer": result["answer"],
                "tables": result.get("tables", []),
                "count": result.get("count"),
                "rows": result.get("rows", []),
                "table": result.get("table"),
                "toolCalls": result.get("toolCalls", []),
                "output_query": None,
            }, 200

        # Query path (via LLM) — keep backward compat
        return {
            "success": True,
            "type": "query",
            "output_query": result["output_query"],
            "metadata": result.get("metadata", {}),
        }, 200
        
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON format: {str(e)}", "output_query": None, "type": "error"}, 400
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}", "output_query": None, "type": "error"}, 500

@api.post('/db-connection',
          tags=[db_tags],
          description='Store database connection details securely',
          responses={200: {"description": "Connection saved successfully", "content": {"application/json": {"schema": {"type": "object", "properties": {"success": {"type": "boolean"}, "message": {"type": "string"}}}}}},
                     400: {"description": "Bad request - invalid input or missing fields"},
                     401: {"description": "Unauthorized - authentication required"},
                     409: {"description": "Conflict - connection already exists"},
                     500: {"description": "Internal server error"}})
@require_auth
def db_connection(body: DBConnectionRequest):
    """Store database connection details for the authenticated user.
    
    Args:
        body: DBConnectionRequest containing host, port, database, username, password
        
    Returns:
        JSON response with success status and message
    """
    try:
        user_record = User.query.get(g.user_id)
        if not user_record:
            return {"success": False, "message": "User not found"}, 404

        user_id = user_record.id
        
        # Handle connection string input
        if body.connection_string:
            try:
                parsed = parse_connection_string(body.connection_string)
                # Use parsed values if separate fields not provided
                host = parsed["host"] or body.host
                port = body.port or parsed["port"]
                database = body.database or parsed["database"]
                username = body.username or parsed["username"]
                password = body.password or parsed["password"]
                connection_string = body.connection_string
                # Detect DB type from connection string prefix
                if body.connection_string.startswith(('postgresql://', 'postgres://')):
                    db_type = 'postgresql'
                elif body.connection_string.startswith('mysql://'):
                    db_type = 'mysql'
                else:
                    db_type = 'postgresql'  # Default
            except ValueError as e:
                return {"success": False, "message": f"Invalid connection string: {str(e)}"}, 400
        else:
            # Use separate values - require all fields
            if not all([body.host, body.port, body.database, body.username, body.password]):
                return {"success": False, "message": "All database fields (host, port, database, username, password) are required when connection_string is not provided"}, 400
            host = body.host
            port = body.port
            database = body.database
            username = body.username
            password = body.password
            db_type = body.db_type or 'postgresql'
            connection_string = build_connection_string(host, port, database, username, password, db_type)
        # Check for existing connection
        existing_conn = DBConnection.query.filter_by(
            user_id=user_id, 
            host=host,
            port=port,
            database=database,
            username=username,
            db_type=db_type
        ).first()
        
        if existing_conn:
            return {"success": True, "message": "Connection already exists"}, 200
        
        # Create new connection (encrypt secrets)
        new_conn = DBConnection(
            user_id=user_id,
            host=host,
            port=port,
            database=database,
            username=username,
            db_type=db_type
        )
        new_conn.set_encrypted_fields(password, connection_string)
        
        db.session.add(new_conn)
        db.session.commit()

        return {"success": True, "message": "Database connection saved successfully"}, 200
        
    except Exception as e:
        db.session.rollback()
        return {"success": False, "message": f"Failed to save connection: {str(e)}"}, 500


@api.post('/test-connection/',
          tags=[db_tags],
          description='Test a database connection')
@require_auth
def test_connection(body: SelectConnectionRequest):
    """Test if a database connection is valid."""
    db_id = body.db_id
    if not db_id:
        return {"success": False, "message": "db_id is required"}, 400
    
    # Get the connection
    conn = DBConnection.query.get(db_id)
    if not conn:
        return {"success": False, "message": "Connection not found"}, 404
    
    # Verify ownership via JWT identity
    user_record = User.query.get(g.user_id)
    if not user_record or conn.user_id != user_record.id:
        return {"success": False, "message": "Unauthorized"}, 401
    
    # Test the connection (decrypt)
    result = connection_pool.test_connection(user_record.id, db_id, conn.get_decrypted_connection_string())
    return result, 200 if result["success"] else 500


@api.delete('/delete-connection',
           tags=[db_tags],
           description='Delete a database connection')
@require_auth
def delete_connection(body: DeleteConnectionRequest):
    """Delete a saved database connection."""
    # Get the connection
    conn = DBConnection.query.get(body.db_id)
    if not conn:
        return {"success": False, "message": "Connection not found"}, 404
    
    # Verify ownership via JWT identity
    user_record = User.query.get(g.user_id)
    if not user_record or conn.user_id != user_record.id:
        return {"success": False, "message": "Unauthorized"}, 401
    
    # Clean up connection pool
    connection_pool._cleanup_pool(user_record.id, body.db_id)
    
    # Delete the connection
    try:
        db.session.delete(conn)
        db.session.commit()
        return {"success": True, "message": "Connection deleted successfully"}, 200
    except Exception as e:
        db.session.rollback()
        return {"success": False, "message": f"Failed to delete connection: {str(e)}"}, 500

@api.get('/get-connections/',
        tags=[db_tags],
        description='Get all database connections for current user')
@require_auth
def get_connections(query: SelectConnectionRequest):
    """Get all saved database connections for the authenticated user.
    
    Args:
        query: Optional query parameters including db_id to get specific connection

    Return:
        List of connections or single connection if db_id is provided
        Creates a connection pool for the user if it doesn't exist
    """

    user_record = User.query.get(g.user_id)
    if not user_record:
        return {"success": False, "message": "User not found"}, 404

    if  query and query.db_id:
        con =  DBConnection.query.get(query.db_id)
        if not con or con.user_id != user_record.id:
            return {"success": False, "message": "Connection not found"}, 404
        conn_str = con.get_decrypted_connection_string()
        test_result = connection_pool.test_connection(user_record.id, query.db_id, conn_str)
        if not test_result["success"]:
            return test_result, 500
        tables = get_tables(user_record.id, query.db_id, conn_str)
        return {
            "success": True,
            "message": "Connection successful",
            "connection": {
                "id": con.id,
                "host": con.host,
                "port": con.port,
                "database": con.database,
                "username": con.username,
                "created_at": con.created_at.isoformat() if con.created_at else None
            },
            "tables": tables
        }

    else:
        page = query.page if query and query.page else 1
        per_page = query.per_page if query and query.per_page else 20
        pagination = DBConnection.query.filter_by(user_id=user_record.id).paginate(page=page, per_page=per_page, error_out=False)
        return {
            "success": True,
            "message": "Connections retrieved successfully",
            "page": page,
            "per_page": per_page,
            "total": pagination.total,
            "pages": pagination.pages,
            "connections": [
                {
                    "id": conn.id,
                    "host": conn.host,
                    "port": conn.port,
                    "database": conn.database,
                    "username": conn.username,
                    "created_at": conn.created_at.isoformat() if conn.created_at else None
                }
                for conn in pagination.items
            ]
        }

    



