"""Phase 0 baseline fixtures.

Sets deterministic env vars BEFORE any app/chain import (sql_chain builds
the LLM client at import time), wires backend/ onto sys.path, and provides
a fresh SQLite database per test.
"""

import os
import sys

# Explicit assignment (not setdefault): load_dotenv() inside create_app()
# must not resurrect developer-local secrets for baseline runs.
os.environ["SECRET_KEY"] = "phase0-test-secret-key-32-chars-min!"
os.environ["ENCRYPTION_KEY"] = "phase0-test-encryption-key-32-chr!"
os.environ["API_KEY_PROVIDER"] = "OPEN_ZEN"
os.environ["OPEN_ZEN_API_KEY"] = "phase0-dummy-key"
os.environ["FLASK_ENV"] = "testing"
# Deterministic OTP path: force the in-memory store (no Redis/Celery), so
# suite runs never depend on developer-local brokers.
os.environ["OTP_BACKEND"] = "memory"
os.environ.pop("REDIS_URL", None)
os.environ.pop("CELERY_BROKER_URL", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import sqlglot
from sqlglot import exp

# The URL schemes that address a real database server. SQLite is the only
# one the test suite is allowed to write to.
_REAL_DB_SCHEMES = {
    "postgresql",
    "postgres",
    "mysql",
    "mariadb",
    "mssql",
    "oracle",
    "cockroachdb",
}

# Statement types that change data or schema. Anything else is a read.
_WRITE_EXPRESSIONS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
)


@pytest.fixture(autouse=True, scope="session")
def _no_real_database_writes():
    """Fail any test that writes to a real database server.

    The suite is supposed to run entirely on throwaway SQLite files. This
    is the last line of defence: even if a test builds its own engine from
    a URL it read out of the developer's ``.env``, a write against it is
    refused instead of silently landing in their data.

    The check sits on SQLAlchemy's ``before_cursor_execute`` event, which
    is the only level that covers every driver. A socket-level guard does
    *not* work here: psycopg2 talks to libpq, a C library that opens its
    own sockets and never goes through Python's ``socket`` module. A
    socket guard was tried and silently let a ``DROP TABLE`` through.

    Reads are allowed - a test may inspect a real database's schema - but
    nothing may create, alter or delete anything in it.

    On 2026-11-13 a full test run dropped the tables of the local
    development database, because the settings cache made the app bind to
    that database and the fixture's ``db.drop_all()`` dropped its tables.
    The URL is now forced to SQLite, and this guard makes the remaining
    paths impossible as well.
    """
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    def _refuse_write(conn, cursor, statement, parameters, context, executemany):
        url = conn.engine.url
        if url.get_backend_name() not in _REAL_DB_SCHEMES:
            return

        # Only writes are forbidden. Reads are allowed so a test can still
        # inspect a real database's schema. sqlglot already classifies
        # every statement, so the check does not have to guess from
        # keywords: a CTE that ends in an INSERT is an INSERT, and a
        # SELECT is a SELECT.
        try:
            parsed = sqlglot.parse_one(statement, read="postgres")
        except Exception:  # noqa: BLE001 - unparsable SQL is not trusted
            parsed = None

        if isinstance(parsed, _WRITE_EXPRESSIONS):
            raise RuntimeError(
                f"tests must never write to a real database server "
                f"({url.drivername}://{url.host}/{url.database}): "
                f"{statement!r}. Use a throwaway SQLite file instead."
            )

    event.listen(Engine, "before_cursor_execute", _refuse_write)
    try:
        yield
    finally:
        event.remove(Engine, "before_cursor_execute", _refuse_write)


@pytest.fixture(autouse=True)
def _hermetic_database_url(tmp_path, monkeypatch):
    """Point every test at a throwaway SQLite file for the whole session.

    The app factory binds to ``settings.DATABASE_URL``, which comes from the
    environment and the developer's ``.env`` - i.e. their real database. A
    test that builds the app outside the ``app_client`` fixture would
    therefore be *configured* against the real database, and anything that
    then ran a query or dropped tables would hit it.

    Forcing the URL for every test makes that impossible regardless of what
    the test does, and the settings cache is cleared so the new value is
    picked up.
    """
    from config import get_settings

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'suite.db'}")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def app_client(tmp_path):
    """Fresh Flask app + file SQLite DB + test client per test."""
    old_database_url = os.environ.get("DATABASE_URL")
    db_file = tmp_path.joinpath("phase0.db").as_posix()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"

    # The settings object is cached for the whole process and app.py binds
    # the app to `settings.DATABASE_URL`. If anything read the settings
    # before this fixture (any test that touches get_settings() outside the
    # app_client window will), the cache still holds the DATABASE_URL from
    # .env - the developer's real database - and the app would be bound to
    # it. The teardown below then runs db.drop_all() against that database
    # and deletes its tables. Clearing the cache here makes the app bind to
    # the throwaway SQLite file no matter what ran before.
    from config import get_settings

    get_settings.cache_clear()

    from app import create_app
    from auths.models import db

    app = create_app()
    app.config.update(TESTING=True)
    ctx = app.app_context()
    ctx.push()
    db.create_all()
    try:
        yield app, app.test_client()
    finally:
        db.session.remove()
        # Safety net: never drop tables in a database that is not a
        # throwaway SQLite file, whatever the app ended up bound to.
        if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite://"):
            db.drop_all()
        ctx.pop()
        get_settings.cache_clear()
        if old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_database_url


@pytest.fixture(autouse=True)
def _isolate_otp_store():
    """Reset the (forced in-memory) OTP store around every test."""
    yield
    from auths.otp_store import otp_store

    clear = getattr(otp_store, "clear", None)
    if callable(clear):
        clear()


@pytest.fixture()
def auth_headers(app_client):
    """Register a baseline user; return (auth headers, email) with live JWT."""
    _, client = app_client
    email = "phase0@example.com"
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": "Password123", "name": "Phase Zero"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    token = resp.get_json()["token"]
    return {"Authorization": f"Bearer {token}"}, email
