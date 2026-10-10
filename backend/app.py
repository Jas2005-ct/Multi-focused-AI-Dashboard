from flask_openapi3 import Info, OpenAPI
from sqlalchemy import text

from ai_dashboard.routes import api as service_api
from auths.auth import auth_bp
from auths.models import db
from common.errors import register_error_handlers
from common.request_id import register_request_id
from config import get_settings
from extensions import init_cors, init_limiter, init_migrations, init_oauth


def create_app() -> OpenAPI:
    settings = get_settings()
    app = OpenAPI(
        __name__,
        info=Info(
            title="AI Dashboard API",
            version="1.0.0",
            description="SQL Optimizer with OAuth",
        ),
        security_schemes={"jwt": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}},
    )

    # Fail fast in production when secrets are missing/short.
    app.secret_key = settings.ensure_secret_key()

    register_request_id(app)
    init_cors(app, settings)
    # Disabled automatically when FLASK_ENV=testing (see extensions).
    init_limiter(app, settings)

    # Database configuration
    app.config["SQLALCHEMY_DATABASE_URI"] = settings.DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Initialize database
    db.init_app(app)

    # Initialize OAuth (Google only when client id/secret configured)
    init_oauth(app, settings)

    def _db_ok() -> bool:
        try:
            # Reuse the Flask-SQLAlchemy engine instead of minting one per call.
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 -- liveness probe: any failure means "down"
            return False

    # Health check endpoint (liveness: can we reach the database?)
    @app.get("/health")
    def health():
        """Return status of the service and database connectivity."""
        connected = _db_ok()
        return (
            {
                "status": "ok" if connected else "error",
                "database": "connected" if connected else "error",
            },
            200 if connected else 503,
        )

    # Readiness endpoint (used by orchestrators before sending traffic)
    @app.get("/ready")
    def ready():
        """Deeper readiness probe: database plus extension state."""
        checks = {
            "database": "connected" if _db_ok() else "error",
        }
        ok = all(v == "connected" for v in checks.values())
        return (
            {"status": "ready" if ok else "not_ready", "checks": checks},
            200 if ok else 503,
        )

    register_error_handlers(app)

    # Register blueprints / APIs
    app.register_api(auth_bp, url_prefix="/auth")
    app.register_api(service_api, url_prefix="/api")

    # Initialize migration support
    init_migrations(app, db)

    return app


if __name__ == "__main__":
    import os as _os

    _debug = _os.getenv("FLASK_ENV") != "production" and _os.getenv("FLASK_DEBUG") != "0"
    create_app().run(debug=_debug)
