"""Create-connection contract: `name` and `sslmode` are accepted and persisted.

Regression for the original Phase 1.1 bug: the route passed `body.name`
and `body.sslmode` while DBConnectionRequest did not declare them, so
Pydantic popped an AttributeError and every creation attempt returned
HTTP 500.
"""

# --- create-connection contract --------------------------------------------


def _register(client, email="phase5-save@example.com", password="Password123"):
    resp = client.post(
        "/auth/register", json={"email": email, "password": password, "name": "Phase Save"}
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def test_create_connection_persists_name_and_sslmode(app_client):
    """POST /api/v1/connections must not 500 and must persist name/sslmode."""
    _, client = app_client
    headers = _register(client)

    payload = {
        "name": "Analytics Warehouse",
        "host": "db.invalid",
        "port": 5432,
        "database": "analytics",
        "username": "analyst",
        "password": "hunter2!",
        "db_type": "postgresql",
        "sslmode": "disable",
    }
    resp = client.post("/api/v1/connections", json=payload, headers=headers)
    assert resp.status_code == 200, resp.get_data(as_text=True)

    body = resp.get_json()
    data = body["data"]
    assert data["name"] == "Analytics Warehouse"
    assert data["sslmode"] == "disable"
    assert data["db_type"] == "postgresql"

    # Secrets must never be echoed, even on success.
    assert "password" not in data
    assert "connection_string" not in data

    # The surface contract is backed by real persistence.
    from auths.models import db
    from connections.model import DBConnection

    user_id = client.get("/auth/me", headers=headers).get_json()["id"]
    row = (
        db.session.query(DBConnection).filter_by(user_id=user_id, name="Analytics Warehouse").one()
    )
    assert row.host == "db.invalid"
    assert row.sslmode == "disable"
    assert row.user_id == user_id


def test_create_connection_duplicate_returns_existing_row(app_client):
    """Saving identical details twice returns the SAME row (idempotent)."""
    _, client = app_client
    headers = _register(client, email="dupe-save@example.com")

    payload = {
        "host": "db.invalid",
        "port": 5432,
        "database": "analytics",
        "username": "analyst",
        "password": "hunter2!",
    }
    first = client.post("/api/v1/connections", json=payload, headers=headers)
    assert first.status_code == 200, first.get_data(as_text=True)

    again = client.post("/api/v1/connections", json=payload, headers=headers)
    assert again.status_code == 200, again.get_data(as_text=True)
    assert again.get_json()["data"]["id"] == first.get_json()["data"]["id"]


def test_create_connection_missing_fields_is_400(app_client):
    """Missing credentials answer a clean 400, never an HTML 500."""
    _, client = app_client
    headers = _register(client, email="blank-fields@example.com")

    resp = client.post(
        "/api/v1/connections",
        json={"host": "db.invalid", "db_type": "postgresql"},
        headers=headers,
    )
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is False
