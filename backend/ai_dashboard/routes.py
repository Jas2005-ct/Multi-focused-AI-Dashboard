from flask import request
from ai_dashboard.schemas import QueryResponse, PromptRequest
from auths.models import DBConnection, db, User
from ai_dashboard.prompt_optimize import get_query_format
from ai_dashboard.schemas import DBConnectionRequest
from security.dec import require_auth
from flask_openapi3 import APIBlueprint, Tag
from flask import session
import json

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
        body: PromptRequest containing the natural language input
        
    Returns:
        JSON response with generated SQL query and metadata
    """
    try:
        result = get_query_format(body)
        
        # Check if result contains error
        if "error" in result:
            status_code = 500 if result.get("error_type") == "api_error" else 400
            return {"success": False, "error": result["error"], "output_query": None}, status_code
            
        return {
            "success": True,
            "output_query": result["output_query"],
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
        
        # Check for existing connection
        existing_conn = DBConnection.query.filter_by(
            user_id=user_id, 
            host=body.host,
            port=body.port,
            database=body.database,
            username=body.username
        ).first()
        
        if existing_conn:
            return {"success": True, "message": "Connection already exists"}, 200
        
        # Create new connection
        new_conn = DBConnection(
            user_id=user_id,
            host=body.host,
            port=body.port,
            database=body.database,
            username=body.username,
            password=body.password,
            connection_string=body.connection_string
        )
        
        db.session.add(new_conn)
        db.session.commit()

        return {"success": True, "message": "Database connection saved successfully"}, 200
        
    except Exception as e:
        db.session.rollback()
        return {"success": False, "message": f"Failed to save connection: {str(e)}"}, 500
    

@api.get('/test/')
@require_auth
def test():
    return "Test successful!"



    

