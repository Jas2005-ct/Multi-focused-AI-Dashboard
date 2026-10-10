"""Third-party extension wiring (Phase 1).

Keeps create_app() declarative: CORS, rate limiting, OAuth and migrations
are initialized here, driven by :mod:`config`. Importing this module has
no side effects.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def init_cors(app: Any, settings: Any) -> Any:
    """Credentialed CORS restricted to explicit origins (validated)."""
    from flask_cors import CORS

    origins = settings.ensure_allowed_origins()
    return CORS(
        app,
        resources={r"/*": {"origins": origins}},
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    )


def init_limiter(app: Any, settings: Any) -> Any | None:
    """Per-IP rate limiting. Disabled when FLASK_ENV=testing (suite speed)."""
    if settings.FLASK_ENV.strip().lower() == "testing":
        return None
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address

        return Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=[f"{settings.RATE_LIMIT_PER_MIN}/minute"],
        )
    except ImportError:
        logger.warning("flask-limiter not installed; rate limiting disabled")
        return None


def init_oauth(app: Any, settings: Any) -> Any:
    """Attach Authlib OAuth; registers Google only when configured."""
    from authlib.integrations.flask_client import OAuth

    oauth = OAuth()
    app.oauth = oauth
    if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
        oauth.register(
            name="google",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    else:
        logger.info("GOOGLE_CLIENT_ID/SECRET not set; Google OAuth disabled")
    return oauth


def init_migrations(app: Any, db: Any) -> Any:
    from flask_migrate import Migrate

    return Migrate(app, db)
