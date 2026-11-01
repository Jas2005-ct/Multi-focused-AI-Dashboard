"""Phase 5 API contract tests.

These lock the behaviour of the versioned `/api/v1` surface, with special
attention to the connection routes that take **path parameters**.

Background: the five connection views were originally declared with
`path_db_id` / `path_table_name` while the URL rules declared `<int:db_id>` /
`<table_name>`. Flask binds rule variables to view arguments *by name*, so
every one of those routes raised

    TypeError: delete_connection_v1() missing 1 required positional argument

and answered with Flask's HTML 500 page. The views now take a Pydantic path
model (`ConnectionPath` / `TablePath`), which flask-openapi3 populates from
the URL. These tests are the regression net for exactly that class of bug.
"""

import pytest

# --- helpers ---------------------------------------------------------------


def _register(client, email="phase5@example.com", password="Password123"):
    resp = client.post(
        "/auth/register", json={"email": email, "password": password, "name": "Phase Five"}
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def _make_connection(app, user_id, host="db.invalid", port=5432, database="app"):
    """Insert a saved connection row directly (no network access needed)."""
    from connections.model import DBConnection

    conn = DBConnection(
        user_id=user_id,
        name="Test DB",
        db_type="postgresql",
        host=host,
        port=port,
        database=database,
        username="app_user",
        password="s3cret",
        connection_string=f"postgresql://app_user:s3cret@{host}:{port}/{database}",
    )
    db = app.extensions["sqlalchemy"].session
    db.add(conn)
    db.commit()
    return conn.id


# --- path parameters bind correctly ---------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/connections/1"),
        ("post", "/api/v1/connections/1/test"),
        ("get", "/api/v1/connections/1/tables"),
        ("get", "/api/v1/connections/1/tables/users"),
        ("delete", "/api/v1/connections/1"),
    ],
)
def test_connection_routes_bind_path_params(app_client, method, path):
    """A path-parameter route must never 500 with a TypeError.

    Before the fix these raised
    `TypeError: ... missing 1 required positional argument: 'path_db_id'`
    and Flask rendered an HTML 500 page.
    """
    app, client = app_client
    headers = _register(client)

    resp = getattr(client, method)(path, headers=headers)

    # The route matched and the handler ran: the outcome is a JSON 4xx
    # (unknown id) — never an HTML 500.
    assert resp.content_type.startswith("application/json"), (
        f"{method.upper()} {path} returned {resp.status_code} "
        f"({resp.content_type}) instead of JSON"
    )
    assert resp.status_code == 404, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is False
    assert body["error"] == "Connection not found"


def test_table_route_binds_table_name(app_client):
    """The table name must reach the handler (not be swallowed)."""
    app, client = app_client
    headers = _register(client)
    user_id = client.get("/auth/me", headers=headers).get_json()["id"]
    conn_id = _make_connection(app, user_id)

    resp = client.get(f"/api/v1/connections/{conn_id}/tables/users", headers=headers)

    # The connection exists, so the handler proceeds past the ownership check
    # and fails on the (unreachable) target database instead of on routing.
    assert resp.content_type.startswith("application/json")
    assert resp.status_code in (200, 502), resp.get_data(as_text=True)
    body = resp.get_json()
    if resp.status_code == 502:
        # The driver error is surfaced instead of a generic 500.
        assert body["error"] == "Database unreachable"


# --- authentication is enforced --------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/connections"),
        ("get", "/api/v1/connections/1"),
        ("post", "/api/v1/connections/1/test"),
        ("get", "/api/v1/connections/1/tables"),
        ("get", "/api/v1/connections/1/tables/users"),
        ("delete", "/api/v1/connections/1"),
    ],
)
def test_connection_routes_require_auth(app_client, method, path):
    _, client = app_client

    resp = getattr(client, method)(path)

    assert resp.status_code == 401, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["code"] == "MISSING_TOKEN"


# --- envelopes -------------------------------------------------------------


def test_list_connections_uses_standard_envelope(app_client):
    app, client = app_client
    headers = _register(client)
    user_id = client.get("/auth/me", headers=headers).get_json()["id"]
    _make_connection(app, user_id)

    resp = client.get("/api/v1/connections", headers=headers)

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True
    assert "data" in body
    assert body["data"]["total"] == 1
    assert body["data"]["connections"][0]["id"] >= 1
    # Secrets are never returned.
    assert "password" not in body["data"]["connections"][0]
    assert "connection_string" not in body["data"]["connections"][0]


def test_test_connection_reports_failure_with_200(app_client):
    """A failed connection is a successful *test* with a negative result.

    It must answer 200 with success:false so the client can show the real
    driver message instead of falling into its generic error path.
    """
    app, client = app_client
    headers = _register(client)
    user_id = client.get("/auth/me", headers=headers).get_json()["id"]
    conn_id = _make_connection(app, user_id, host="db.invalid")

    resp = client.post(f"/api/v1/connections/{conn_id}/test", headers=headers)

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True  # envelope ok
    assert body["data"]["success"] is False  # the test itself failed
    assert "db.invalid" in body["data"]["message"]


def test_unknown_connection_is_404(app_client):
    _, client = app_client
    headers = _register(client)

    resp = client.post("/api/v1/connections/9999/test", headers=headers)

    assert resp.status_code == 404, resp.get_data(as_text=True)
    assert resp.get_json()["error"] == "Connection not found"


# --- ownership -------------------------------------------------------------


def test_other_users_connection_is_not_visible(app_client):
    """A row owned by someone else is reported as 404, not 403."""
    app, client = app_client
    owner_headers = _register(client, email="owner@example.com")
    owner_id = client.get("/auth/me", headers=owner_headers).get_json()["id"]
    conn_id = _make_connection(app, owner_id)

    other_headers = _register(client, email="other@example.com")

    resp = client.get(f"/api/v1/connections/{conn_id}", headers=other_headers)

    assert resp.status_code == 404, resp.get_data(as_text=True)
    assert resp.get_json()["error"] == "Connection not found"


def test_delete_connection_uses_standard_envelope(app_client):
    app, client = app_client
    headers = _register(client)
    user_id = client.get("/auth/me", headers=headers).get_json()["id"]
    conn_id = _make_connection(app, user_id)

    resp = client.delete(f"/api/v1/connections/{conn_id}", headers=headers)

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True
    assert body["message"] == "Connection deleted successfully"

    # And it is really gone.
    again = client.delete(f"/api/v1/connections/{conn_id}", headers=headers)
    assert again.status_code == 404
