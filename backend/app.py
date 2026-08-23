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
    secret_key = os.getenv("SECRET_KEY")
    
    # Ensure secret key is at least 32 bytes for JWT HS256 security
    if not secret_key or len(secret_key.encode('utf-8')) < 32:
        import secrets
        import warnings
        warnings.warn(
            "SECRET_KEY is too short (< 32 bytes) or not set. "
            "Using a generated key. Set a proper SECRET_KEY in .env for production.",
            RuntimeWarning
        )
        # Generate a 32-byte (256-bit) secure key
        secret_key = secrets.token_urlsafe(32)
    
    app.secret_key = secret_key
    
    # Configure CORS to handle preflight and credentials
    CORS(app, 
         resources={r"/*": {"origins": ["http://localhost:5173", "http://127.0.0.1:5173"]}},
         supports_credentials=True,
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Initialize database
    db.init_app(app)
    
    # Initialize OAuth
    oauth.init_app(app)

    # Initialize Google OAuth (optional)
    google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if google_client_id and google_client_secret:
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
    app.register_api(auth_bp, url_prefix='/auth')
    app.register_api(service_api, url_prefix='/api')
    
    # Initialize migration
    migrate = Migrate(app, db)
    
    return app


if __name__ == '__main__':
    create_app().run(debug=True)
