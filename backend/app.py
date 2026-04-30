from flask import Flask
from flask_cors import CORS
import os
from dotenv import load_dotenv
from ai_dashboard.routes import api as service_api
from flask_openapi3 import OpenAPI,Info
from auths.auth import auth_bp
from auths.models import db
from authlib.integrations.flask_client import OAuth
from flask_migrate import Migrate
load_dotenv()

oauth = OAuth()

info = Info(
    title="AI Dashboard API",
    version="1.0.0",
    description="SQL Optimizer with OAuth"
)

def create_app() -> OpenAPI:
    app = OpenAPI(__name__, info=info)
    app.secret_key = os.getenv("SECRET_KEY")
    CORS(app)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Initialize database
    db.init_app(app)
    
    # Initialize OAuth
    oauth.init_app(app)

    # Initialize Google OAuth
    google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not google_client_id or not google_client_secret:
        raise RuntimeError("Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET environment variables")

    oauth.register(
        name='google',
        client_id=google_client_id,
        client_secret=google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            'scope': 'openid email profile'
        }
    )
    
    app.oauth = oauth
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_api(service_api,url_prefix='/api')
    
    # Initialize migration
    migrate = Migrate(app, db)
    
    return app


if __name__ == '__main__':
    create_app().run(debug=True)
