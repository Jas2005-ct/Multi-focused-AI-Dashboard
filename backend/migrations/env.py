"""Alembic environment (Phase 4).

Runs in two modes and must work in both:

* ``flask db ...`` - Flask-Migrate pushes an app context, so the app's own
  engine is used. Migrations therefore target exactly the database the app
  uses (same ``DATABASE_URL``, same driver, same pool).
* ``alembic ...`` (raw CLI) - there is no app context, so the URL is resolved
  from ``DATABASE_URL`` (process env, falling back to ``backend/.env``) and
  then from ``sqlalchemy.url`` in ``backend/alembic.ini``.

Previously this module built its own ``Config`` from ``backend/alembic.ini``
and ignored the one Alembic handed in, which pinned every migration to the
hard-coded URL in that file and broke ``DATABASE_URL`` entirely.
"""

import logging
import os
import sys
from pathlib import Path

from alembic import context

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # The raw CLI does not put the project root on sys.path, but the model
    # modules (``auths.models``) live there.
    sys.path.insert(0, str(BACKEND_DIR))

logger = logging.getLogger("alembic.env")

# The Config Alembic hands to this script: Flask-Migrate's under `flask db`,
# otherwise one built from backend/alembic.ini.
config = context.config


def _app_engine():
    """The app's engine, or None when there is no app context."""
    try:
        from flask import current_app, has_app_context
    except ImportError:  # pragma: no cover - Flask is a hard dependency
        return None
    if not has_app_context():
        return None
    return current_app.extensions["migrate"].db.engine


def _cli_database_url() -> str:
    """Database URL for the raw CLI (no Flask app context)."""
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")
    url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError(
            "No database URL configured. Set DATABASE_URL in the environment or "
            "backend/.env, or set sqlalchemy.url in backend/alembic.ini."
        )
    return url


def get_engine():
    """Engine the migrations run against."""
    engine = _app_engine()
    if engine is not None:
        return engine

    from sqlalchemy import create_engine

    url = _cli_database_url()
    # Map the bare schemes onto the drivers that are actually installed.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+pymysql://", 1)
    return create_engine(url)


def get_engine_url():
    """Database URL as a string (used for offline mode and the ini option)."""
    engine = _app_engine()
    if engine is not None:
        url = engine.url.render_as_string(hide_password=False)
    else:
        url = _cli_database_url()
    # ConfigParser treats '%' as interpolation; escape it for set_main_option.
    return url.replace("%", "%%")


def get_metadata():
    """Model metadata, required by ``--autogenerate``.

    The models are Flask-SQLAlchemy models; importing the modules registers
    their tables on ``db.metadata``. ``db.metadata`` is populated when the
    ``SQLAlchemy`` instance is constructed, so this works with and without an
    app context.
    """
    from auths.models import db
    from connections import model  # noqa: F401  (registers DBConnection)

    return db.metadata


def process_revision_directives(context, revision, directives):
    """Skip generating an empty migration when nothing changed."""
    if getattr(config.cmd_opts, "autogenerate", False):
        script = directives[0]
        if script.upgrade_ops.is_empty():
            directives[:] = []
            logger.info("No changes in schema detected.")


config.set_main_option("sqlalchemy.url", get_engine_url())


def run_migrations_offline():
    """Emit SQL to stdout instead of running it against a live database."""
    context.configure(
        url=get_engine_url(),
        target_metadata=get_metadata(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        process_revision_directives=process_revision_directives,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run the migrations against a live database."""
    connectable = get_engine()
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            process_revision_directives=process_revision_directives,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
