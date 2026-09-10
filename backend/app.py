from flask import Flask
from flask_cors import CORS
import os
from settings import ALLOWED_ORIGINS, RATE_LIMIT_PER_MIN
from dotenv import load_dotenv
from ai_dashboard.routes import api as service_api
from flask_openapi3 import OpenAPI, Info
from auths.auth import auth_bp
from auths.models import db
from authlib.integrations.flask_client import OAuth
from flask_migrate import Migrate

load_dotenv()


def create_app() -> OpenAPI:
    app = OpenAPI(__name__, info=Info(title="AI Dashboard API", version="1.0.0",
                                      description="SQL Optimizer with OAuth"),
                  security_schemes={"jwt": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}})

    # Secret key handling
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key or len(secret_key.encode("utf-8")) < 32:
        import secrets
        import warnings
        warnings.warn(
            "SECRET_KEY is too short (< 32 bytes) or not set. "
            "Using a generated key. Set a proper SECRET_KEY in .env for production.",
            RuntimeWarning,
        )
        secret_key = secrets.token_urlsafe(32)
    app.secret_key = secret_key

    # Configure CORS using environment origins
    CORS(app,
         resources={r"/*": {"origins": ALLOWED_ORIGINS}},
         supports_credentials=True,
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

    # Rate limiting (flask-limiter if installed)
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=[f"{RATE_LIMIT_PER_MIN}/minute"]
        )
    except ImportError:
        limiter = None

    # Database configuration
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///app.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Initialize database
    db.init_app(app)

    # Initialize OAuth
    oauth = OAuth()
    app.oauth = oauth

    # Optional Google OAuth
    google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if google_client_id and google_client_secret:
        oauth.register(
            name='google',
            client_id=google_client_id,
            client_secret=google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={'scope': 'openid email profile'}
        )

    # Health check endpoint
    @app.get('/health')
    def health():
        """Return status of the service and database connectivity."""
        from sqlalchemy import create_engine, text
        db_status = "unknown"
        try:
            engine = create_engine(app.config["SQLALCHEMY_DATABASE_URI"])
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception:
            db_status = "error"
        secret_set = bool(os.getenv("SECRET_KEY"))
        ok = db_status == "connected" and secret_set
        return {"status": "ok" if ok else "error", "database": db_status}, \
               200 if ok else 503

    # Register blueprints / APIs
    app.register_api(auth_bp, url_prefix='/auth')
    app.register_api(service_api, url_prefix='/api')

    # Initialize migration support
    migrate = Migrate(app, db)

    return app


if __name__ == '__main__':
    create_app().run(debug=True)