#!/usr/bin/env python
"""
Database initialization script.

Applies Alembic migrations instead of a bare ``db.create_all()`` so every
database — fresh or legacy — ends up with the *current* schema *and* a
recorded migration history.

Why not create_all(): way back, databases created with create_all() never
wrote an ``alembic_version`` row, so later ``flask db upgrade`` attempts
either failed (tables already exist) or re-ran from base. This script
self-heals those databases by stamping the current head before upgrading.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import inspect, text

from app import create_app
from auths.models import db

# Load environment variables
load_dotenv()

# Tables created by the legacy create_all() bootstrap, before migrations existed.
_LEGACY_SCHEMA_TABLES = {"users", "db_connections", "refresh_tokens"}


def _needs_legacy_stamp(conn) -> bool:
    """True when workspace tables exist but no Alembic revision is recorded."""
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    if "alembic_version" in tables and conn.execute(text("SELECT 1 FROM alembic_version")).fetchall():
        return False  # Revision recorded — normal migration-tracked database.
    # No version row (or no version table at all): legacy create_all() database?
    return bool(tables & _LEGACY_SCHEMA_TABLES)


def init_database() -> None:
    """Migrate the database to the latest schema revision."""
    app = create_app()

    with app.app_context():
        from flask_migrate import stamp, upgrade

        with db.engine.connect() as conn:
            legacy_unstamped = _needs_legacy_stamp(conn)

        if legacy_unstamped:
            print("Legacy (pre-migration) schema detected — stamping head, then upgrading...")
            stamp(revision="head")

        upgrade()
        current = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        print(f"[ok] Database migrated successfully! (alembic_version: {current})")
        print(f"[ok] Database URL: {os.getenv('DATABASE_URL')}")


if __name__ == "__main__":
    init_database()
