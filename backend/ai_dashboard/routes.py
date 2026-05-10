from flask import request
from ai_dashboard.schemas import QueryResponse, PromptRequest, SelectConnectionRequest, DeleteConnectionRequest
from auths.models import DBConnection, db, User
from ai_dashboard.prompts import get_query_format
from ai_dashboard.schemas import DBConnectionRequest
from ai_dashboard.db_connections import (
    parse_connection_string, 
    build_connection_string, 
    connection_pool,
    get_tables,
    get_full_schema,
    format_schema_for_llm
)
from security.dec import require_auth
from flask_openapi3 import APIBlueprint, Tag
from flask import session
import json
import logging

logger = logging.getLogger(__name__)

api = APIBlueprint('services', __name__)
sql_tags = Tag(name='SQL Query', description='SQL Query operations')
db_tags = Tag(name='Database Connection', description='Database Connection operations')



@api.get('/')
@require_auth
def hello():
    user = session.get('email')
    return f"Hello, {user}!"


@api.post('/sql-query/',
         tags=[sql_tags],
         description='Generate a SQL query from a natural language sentence',
         responses={200: {"description": "SQL query generated successfully", "content": {"application/json": {"schema": {"type": "object", "properties": {"output_query": {"type": "string"}, "metadata": {"type": "object"}}}}}},
                    400: {"description": "Bad request - invalid input"},
                    401: {"description": "Unauthorized - authentication required"},
                    500: {"description": "Internal server error"}})
@require_auth
def optimize(body: PromptRequest):
    """Generate optimized SQL query from natural language input.
    
    Args:
        body: PromptRequest containing the natural language input and optional db_id
        
    Returns:
        JSON response with generated SQL query and metadata
    """
    try:
        # If db_id is provided, fetch schema for context
        schema_context = None
        if body.db_id:
            user = session.get('email')
            user_record = User.query.filter_by(email=user).first()
            if user_record:
                conn = DBConnection.query.get(body.db_id)
                if conn and conn.user_id == user_record.id:
                    try:
                        schema = get_full_schema(user_record.id, body.db_id, conn.connection_string)
                        schema_context = format_schema_for_llm(schema)
                    except Exception as e:
                        logger.warning(f"Failed to fetch schema: {str(e)}")
        
        result = get_query_format(body, schema_context)
        
        # Check if result contains error
        if "error" in result:
            status_code = 500 if result.get("error_type") == "api_error" else 400
            return {"success": False, "error": result["error"], "output_query": None}, status_code
            
        return {
            "success": True,
            "output_query": result["output_query"],
            "metadata": result.get("metadata", {})
        }, 200
        
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON format: {str(e)}", "output_query": None}, 400
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}", "output_query": None}, 500

@api.post('/db-connection/',
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
        user = session.get('email')
        if not user:
            return {"success": False, "message": "User not authenticated"}, 401
            
        user_record = User.query.filter_by(email=user).first()
        if not user_record:
            return {"success": False, "message": "User not found"}, 404
            
        user_id = user_record.id
        
        # Handle connection string input
        if body.connection_string:
            try:
                parsed = parse_connection_string(body.connection_string)
                # Use parsed values if separate fields not provided
                host = body.host or parsed["host"]
                port = body.port or parsed["port"]
                database = body.database or parsed["database"]
                username = body.username or parsed["username"]
                password = body.password or parsed["password"]
                connection_string = body.connection_string
            except ValueError as e:
                return {"success": False, "message": f"Invalid connection string: {str(e)}"}, 400
        else:
            # Use separate values
            host = body.host
            port = body.port
            database = body.database
            username = body.username
            password = body.password
            connection_string = build_connection_string(host, port, database, username, password)

        # Check for existing connection
        existing_conn = DBConnection.query.filter_by(
            user_id=user_id, 
            host=host,
            port=port,
            database=database,
            username=username
        ).first()
        
        if existing_conn:
            return {"success": True, "message": "Connection already exists"}, 200
        
        # Create new connection
        new_conn = DBConnection(
            user_id=user_id,
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            connection_string=connection_string
        )
        
        db.session.add(new_conn)
        db.session.commit()

        return {"success": True, "message": "Database connection saved successfully"}, 200
        
    except Exception as e:
        db.session.rollback()
        return {"success": False, "message": f"Failed to save connection: {str(e)}"}, 500


@api.post('/select-connection/',
          tags=[db_tags],
          description='Select a database connection and list tables')
@require_auth
def select_connection(body: SelectConnectionRequest):
    """Select a database connection, test it, and return tables."""
    # Get the connection
    conn = DBConnection.query.get(body.db_id)
    if not conn:
        return {"success": False, "message": "Connection not found"}, 404
    
    # Verify ownership
    user = session.get('email')
    user_record = User.query.filter_by(email=user).first()
    if not user_record or conn.user_id != user_record.id:
        return {"success": False, "message": "Unauthorized"}, 401
    
    # Test the connection using connection pool
    test_result = connection_pool.test_connection(user_record.id, body.db_id, conn.connection_string)
    if not test_result["success"]:
        return test_result, 500
    
    # Get tables
    try:
        tables = get_tables(user_record.id, body.db_id, conn.connection_string)
        return {
            "success": True,
            "message": "Connection successful",
            "connection": {
                "id": conn.id,
                "host": conn.host,
                "database": conn.database,
                "username": conn.username
            },
            "tables": tables
        }, 200
    except Exception as e:
        logger.error(f"Failed to get tables: {str(e)}")
        return {"success": False, "message": f"Failed to list tables: {str(e)}"}, 500


@api.post('/test-connection/',
          tags=[db_tags],
          description='Test a database connection')
@require_auth
def test_connection(body: SelectConnectionRequest):
    """Test if a database connection is valid."""
    db_id = body.get('db_id')
    if not db_id:
        return {"success": False, "message": "db_id is required"}, 400
    
    # Get the connection
    conn = DBConnection.query.get(db_id)
    if not conn:
        return {"success": False, "message": "Connection not found"}, 404
    
    # Verify ownership
    user = session.get('email')
    user_record = User.query.filter_by(email=user).first()
    if not user_record or conn.user_id != user_record.id:
        return {"success": False, "message": "Unauthorized"}, 401
    
    # Test the connection
    result = connection_pool.test_connection(user_record.id, db_id, conn.connection_string)
    return result, 200 if result["success"] else 500


@api.delete('/delete-connection/',
           tags=[db_tags],
           description='Delete a database connection')
@require_auth
def delete_connection(body: DeleteConnectionRequest):
    """Delete a saved database connection."""
    # Get the connection
    conn = DBConnection.query.get(body.db_id)
    if not conn:
        return {"success": False, "message": "Connection not found"}, 404
    
    # Verify ownership
    user = session.get('email')
    user_record = User.query.filter_by(email=user).first()
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
def get_connections():
    """Get all saved database connections for the authenticated user."""
    user = session.get('email')
    user_record = User.query.filter_by(email=user).first()
    if not user_record:
        return {"success": False, "message": "User not found"}, 404
    
    connections = DBConnection.query.filter_by(user_id=user_record.id).all()
    return {
        "success": True,
        "connections": [
            {
                "id": conn.id,
                "host": conn.host,
                "port": conn.port,
                "database": conn.database,
                "username": conn.username,
                "created_at": conn.created_at.isoformat() if conn.created_at else None
            }
            for conn in connections
        ]
    }, 200


@api.get('/test/')
@require_auth
def test():
    return "Test successful!"



    

