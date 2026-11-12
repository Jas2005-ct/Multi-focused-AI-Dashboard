#!/usr/bin/env python
"""
Database initialization script.

Brings a database to the current schema revision, whether it is brand new,
a legacy ``create_all()`` database, or an already-migrated one.

Why not create_all(): way back, databases created with create_all() never
wrote an ``alembic_version`` row, so later ``flask db upgrade`` attempts
either failed (tables already exist) or re-ran from base. This script
self-heals those databases by stamping the current head.

Fresh databases are *stamped*, not upgraded: ``db.create_all()`` materialises
the current model schema, which is exactly the head revision, so replaying
the migration history on top of it would re-apply DDL that already exists
(duplicate columns, re-created tables).
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


def _inspect_database(conn):
    """Return (tables, has_version_row) for the connected database."""
    tables = set(inspect(conn).get_table_names())
    has_version_row = bool(
        "alembic_version" in tables
        and conn.execute(text("SELECT 1 FROM alembic_version")).fetchall()
    )
    return tables, has_version_row


def init_database() -> None:
    """Migrate the database to the latest schema revision."""
    app = create_app()

    with app.app_context():
        from flask_migrate import stamp, upgrade

        with db.engine.connect() as conn:
            tables, has_version_row = _inspect_database(conn)

        if has_version_row:
            # Already migration-tracked - just move it forward.
            print("Migration-tracked database detected — upgrading to head...")
            upgrade()
        elif tables & _LEGACY_SCHEMA_TABLES:
            # Legacy create_all() database: the schema is already at head.
            print("Legacy (pre-migration) schema detected — stamping head...")
            stamp(revision="head")
        elif tables:
            # Some other schema we do not recognise - refuse rather than
            # half-apply migrations to an unknown starting point.
            raise RuntimeError(
                "Unrecognised database schema (tables: "
                f"{', '.join(sorted(tables))}) and no alembic revision recorded. "
                "Refusing to migrate an unknown starting point."
            )
        else:
            # Fresh database: create_all() already produces the head schema,
            # so stamp instead of replaying the migration history.
            print("Fresh database — creating base schema via db.create_all(), stamping head...")
            db.create_all()
            stamp(revision="head")

        current = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

        # Safety net: a legacy database is stamped straight to head, which
        # assumes its schema already matches. Verify that assumption instead
        # of failing later at runtime.
        missing = _LEGACY_SCHEMA_TABLES - set(inspect(db.engine).get_table_names())
        if missing:
            raise RuntimeError(
                f"Database is missing expected table(s): {', '.join(sorted(missing))}. "
                "Its schema does not match the recorded revision - review the "
                "migration history for this database before using it."
            )

        print(f"[ok] Database migrated successfully! (alembic_version: {current})")
        print(f"[ok] Database URL: {os.getenv('DATABASE_URL')}")


if __name__ == "__main__":
    init_database()
