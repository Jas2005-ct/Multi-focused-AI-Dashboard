from flask import request
from ai_dashboard.schemas import QueryResponse, PromptRequest
from auths.models import DBConnection, db, User
from ai_dashboard.prompt_optimize import get_query_format
from ai_dashboard.schemas import DBConnectionRequest
from security.dec import require_auth
from flask_openapi3 import APIBlueprint, Tag
from flask import session

api = APIBlueprint('services', __name__)
sql_tags = Tag(name='SQL Query', description='SQL Query operations')
db_tags = Tag(name='Database Connection', description='Database Connection operations')



@api.get('/')
@require_auth
def hello():
    return "Hello, World!"


@api.post('/sql-query/', 
             tags=[sql_tags],
             description='Generate a SQL query from a natural language sentence',             
             )
@require_auth
def optimize():
    sentence = request.json["sentence"]
    sentence_obj = PromptRequest(input=sentence)
    result = get_query_format(sentence_obj)
    return result

@api.post('/db-connection/',
             tags=[db_tags],
             description='Store database connection details',
             )
@require_auth
def db_connection():
    db_config = DBConnectionRequest(**request.json)
    db_string = f"postgresql://{db_config.username}:{db_config.password}@{db_config.host}:{db_config.port}/{db_config.database}"
    user = session.get('email')
    user_id = User.query.filter_by(email=user).first().id
    
    #check existing connection string
    existing_conn = DBConnection.query.filter_by(
        user_id=user_id, 
        host=db_config.host,
        port=db_config.port,
        database=db_config.database,
        username=db_config.username
    ).first()
    if existing_conn:
        return {"message": "Connection string already exists"}
    
    # Save to database
    new_conn = DBConnection(
        user_id=user_id,
        host=db_config.host,
        port=db_config.port,
        database=db_config.database,
        username=db_config.username,
        password=db_config.password
    )
    try:
        if db_config.connection_string:
            new_conn.connection_string = db_config.connection_string
    except Exception as e:
        print(e)
    db.session.add(new_conn)
    db.session.commit()

    return {"message": "Database connection details stored successfully"}
    

@api.get('/test/')
@require_auth
def test():
    return "Test successful!"



    

