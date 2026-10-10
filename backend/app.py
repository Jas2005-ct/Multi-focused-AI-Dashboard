from flask import jsonify
from flask_openapi3 import Info, OpenAPI
from sqlalchemy import text

from ai_dashboard.routes import api as service_api
from ai_dashboard.routes_v1 import v1 as service_api_v1
from auths.auth import auth_bp
from auths.models import db
from common.errors import register_error_handlers
from common.request_id import register_request_id
from config import get_settings
from connections.routes import api as connections_api
from extensions import init_cors, init_limiter, init_migrations, init_oauth
from security.dec import require_auth


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
    app.register_api(service_api_v1)  # already has /api/v1 prefix
    app.register_api(connections_api)  # already has /api/v1 prefix

    # Deprecation shims for old endpoints (Phase 5)
    # These keep old endpoints working but add deprecation headers
    @app.route("/api/sql-query/", methods=["POST"])
    @require_auth
    def _deprecated_sql_query():
        from ai_dashboard.routes import optimize as optimize_impl
        resp = optimize_impl()
        resp = resp if isinstance(resp, tuple) else (resp, 200)
        resp_obj = resp[0] if isinstance(resp, tuple) else resp
        if hasattr(resp_obj, 'headers'):
            resp_obj.headers["Deprecation"] = "true"
            resp_obj.headers["Link"] = '<https://api.example.com/api/v1/ai/query>; rel="successor-version"'
        return resp

    @app.route("/api/db-connection", methods=["POST"])
    @require_auth
    def _deprecated_db_connection():
        from ai_dashboard.routes import db_connection as db_connection_impl
        resp = db_connection_impl()
        if isinstance(resp, tuple):
            resp_obj = resp[0]
        else:
            resp_obj = resp
        if hasattr(resp_obj, 'headers'):
            resp_obj.headers["Deprecation"] = "true"
            resp_obj.headers["Link"] = '<https://api.example.com/api/v1/connections>; rel="successor-version"'
        return resp

    @app.route("/api/get-connections/", methods=["GET"])
    @require_auth
    def _deprecated_get_connections():
        from ai_dashboard.routes import get_connections as get_connections_impl
        resp = get_connections_impl()
        if isinstance(resp, tuple):
            resp_obj = resp[0]
        else:
            resp_obj = resp
        if hasattr(resp_obj, 'headers'):
            resp_obj.headers["Deprecation"] = "true"
            resp_obj.headers["Link"] = '<https://api.example.com/api/v1/connections>; rel="successor-version"'
        return resp

    @app.route("/api/test-connection/", methods=["POST"])
    @require_auth
    def _deprecated_test_connection():
        from ai_dashboard.routes import test_connection as test_connection_impl
        resp = test_connection_impl()
        if isinstance(resp, tuple):
            resp_obj = resp[0]
        else:
            resp_obj = resp
        if hasattr(resp_obj, 'headers'):
            resp_obj.headers["Deprecation"] = "true"
            resp_obj.headers["Link"] = '<https://api.example.com/api/v1/connections/:id/test>; rel="successor-version"'
        return resp

    @app.route("/api/delete-connection", methods=["DELETE"])
    @require_auth
    def _deprecated_delete_connection():
        from ai_dashboard.routes import delete_connection as delete_connection_impl
        resp = delete_connection_impl()
        if isinstance(resp, tuple):
            resp_obj = resp[0]
        else:
            resp_obj = resp
        if hasattr(resp_obj, 'headers'):
            resp_obj.headers["Deprecation"] = "true"
            resp_obj.headers["Link"] = '<https://api.example.com/api/v1/connections/:id>; rel="successor-version"'
        return resp

    # OpenAPI spec endpoint
    @app.get("/openapi.json")
    def openapi_spec():
        """Serve OpenAPI 3.0 specification."""
        return jsonify(app._get_openapi_spec())

    # Initialize migration support
    init_migrations(app, db)

    return app


if __name__ == "__main__":
    import os as _os

    _debug = _os.getenv("FLASK_ENV") != "production" and _os.getenv("FLASK_DEBUG") != "0"
    create_app().run(debug=_debug)
