"""The demo connection endpoint.

The demo database is the shared, synthetic dataset a visitor can attach
to their account to try the assistant without bringing a database of
their own. These tests cover the endpoint's contract: it needs a signed-in
user, it answers 503 when the deployment has no demo database, it is
idempotent, and it never stores the demo credentials in the clear.
"""

import pytest

DEMO_URL = "postgresql://demo_reader:s3cret@db.example.com:5432/demo_ai_db"


def _register(client, email="demo@example.com"):
    resp = client.post(
        "/auth/register", json={"email": email, "password": "Password123", "name": "Demo"}
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def test_the_demo_endpoint_needs_a_signed_in_user(app_client):
    """No token, no demo database."""
    _, client = app_client

    resp = client.post("/api/v1/connections/demo")

    assert resp.status_code == 401, resp.get_data(as_text=True)


def test_without_a_configured_demo_database_the_endpoint_answers_503(app_client, auth_headers):
    """A deployment without a demo database says so instead of failing oddly."""
    _, client = app_client

    resp = client.post("/api/v1/connections/demo", headers=auth_headers[0])

    assert resp.status_code == 503, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is False
    text = (body.get("error") or body.get("message") or "").lower()
    assert "demo" in text


def test_the_demo_connection_is_attached(app_client, auth_headers, monkeypatch):
    """The configured URL becomes a saved connection for the user."""
    from config import get_settings

    monkeypatch.setattr(get_settings(), "DEMO_DB_URL", DEMO_URL)

    _, client = app_client

    resp = client.post("/api/v1/connections/demo", headers=auth_headers[0])

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True
    data = body["data"]
    assert data["created"] is True
    assert data["host"] == "db.example.com"
    assert data["port"] == 5432
    assert data["database"] == "demo_ai_db"
    assert data["username"] == "demo_reader"
    assert data["db_type"] == "postgresql"


def test_the_demo_connection_shows_up_in_the_connection_list(app_client, auth_headers, monkeypatch):
    """The attached database is a normal connection from here on."""
    from config import get_settings

    monkeypatch.setattr(get_settings(), "DEMO_DB_URL", DEMO_URL)

    _, client = app_client
    client.post("/api/v1/connections/demo", headers=auth_headers[0])

    resp = client.get("/api/v1/connections", headers=auth_headers[0])

    assert resp.status_code == 200, resp.get_data(as_text=True)
    connections = resp.get_json()["data"]["connections"]
    assert [c["database"] for c in connections] == ["demo_ai_db"]


def test_pressing_the_button_twice_reuses_the_same_connection(
    app_client, auth_headers, monkeypatch
):
    """The button is idempotent: a second press does not create a duplicate."""
    from config import get_settings

    monkeypatch.setattr(get_settings(), "DEMO_DB_URL", DEMO_URL)

    _, client = app_client

    first = client.post("/api/v1/connections/demo", headers=auth_headers[0])
    second = client.post("/api/v1/connections/demo", headers=auth_headers[0])

    assert first.status_code == 200, first.get_data(as_text=True)
    assert second.status_code == 200, second.get_data(as_text=True)
    assert first.get_json()["data"]["created"] is True
    assert second.get_json()["data"]["created"] is False
    assert first.get_json()["data"]["id"] == second.get_json()["data"]["id"]

    listed = client.get("/api/v1/connections", headers=auth_headers[0])
    assert listed.get_json()["data"]["total"] == 1


def test_the_demo_password_is_stored_encrypted(app_client, auth_headers, monkeypatch):
    """The demo credentials must never be readable in the database."""
    from config import get_settings

    monkeypatch.setattr(get_settings(), "DEMO_DB_URL", DEMO_URL)

    app, client = app_client
    client.post("/api/v1/connections/demo", headers=auth_headers[0])

    from auths.models import db
    from connections.model import DBConnection

    row = DBConnection.query.filter_by(database="demo_ai_db").first()

    assert row is not None
    assert "s3cret" not in row.connection_string
    assert "s3cret" not in (row.password or "")
    # The plaintext only exists inside the encrypted blob.
    assert db.session.execute(db.select(DBConnection.id).where(DBConnection.id == row.id)).scalar()


def test_two_users_each_get_their_own_demo_connection(app_client, monkeypatch):
    """The demo database is shared, but the connection row belongs to the user."""
    from config import get_settings

    monkeypatch.setattr(get_settings(), "DEMO_DB_URL", DEMO_URL)

    _, client = app_client
    first = _register(client, "one@example.com")
    second = _register(client, "two@example.com")

    one = client.post("/api/v1/connections/demo", headers=first)
    two = client.post("/api/v1/connections/demo", headers=second)

    assert one.get_json()["data"]["id"] != two.get_json()["data"]["id"]

    listed = client.get("/api/v1/connections", headers=first)
    assert listed.get_json()["data"]["total"] == 1


def test_a_mysql_demo_url_is_recognised(app_client, auth_headers, monkeypatch):
    """The app supports MySQL too, so the demo URL may be a MySQL one."""
    from config import get_settings

    monkeypatch.setattr(
        get_settings(), "DEMO_DB_URL", "mysql://demo:s3cret@db.example.com:3306/demo_shop"
    )

    _, client = app_client

    resp = client.post("/api/v1/connections/demo", headers=auth_headers[0])

    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()["data"]
    assert data["db_type"] == "mysql"
    assert data["port"] == 3306


def test_an_incomplete_demo_url_is_rejected(app_client, auth_headers, monkeypatch):
    """A URL without a database name is a configuration mistake, not a crash."""
    from config import get_settings

    monkeypatch.setattr(get_settings(), "DEMO_DB_URL", "postgresql://user@host")

    _, client = app_client

    resp = client.post("/api/v1/connections/demo", headers=auth_headers[0])

    assert resp.status_code == 400, resp.get_data(as_text=True)


@pytest.mark.parametrize(
    ("url", "expected_user"),
    [
        ("postgresql://user:p%40ss@host:5432/db", "user"),
        ("postgresql://user:p%40ss@host:5432/db", "user"),
    ],
)
def test_percent_encoded_credentials_are_decoded(url, expected_user):
    """A password with special characters survives the round trip.

    Supabase hands out passwords that need percent-encoding in a URL; the
    stored username and password have to be the real ones, not the
    encoded form.
    """
    from connections.service import parse_connection_string

    parsed = parse_connection_string(url)

    assert parsed["username"] == expected_user
    assert parsed["password"] == "p@ss"
