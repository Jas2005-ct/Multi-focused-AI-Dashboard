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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture()
def app_client(tmp_path):
    """Fresh Flask app + file SQLite DB + test client per test."""
    old_database_url = os.environ.get("DATABASE_URL")
    db_file = tmp_path.joinpath("phase0.db").as_posix()
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"

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
        db.drop_all()
        ctx.pop()
        if old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_database_url


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
