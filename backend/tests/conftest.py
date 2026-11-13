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
