"""Demo mode: authentication is skipped so visitors can use the demo database.

TEMPORARY: these tests pin the behaviour that lets visitors in without
signing in. When ``AUTH_REQUIRED`` is restored to True, delete this module
and the demo-mode branch in ``security/dec.py``.
"""

from auths.models import DEMO_USER_EMAIL, User

DEMO_URL = "postgresql://demo_reader:s3cret@db.example.com:5432/demo_ai_db"


def _enable_demo_mode(monkeypatch):
    """Switch the request-time setting off and rebuild the cached settings."""
    from config import get_settings

    monkeypatch.setenv("AUTH_REQUIRED", "false")
    get_settings.cache_clear()


def test_anonymous_requests_are_attributed_to_the_demo_user(app_client, monkeypatch):
    """No token is required while AUTH_REQUIRED is False."""
    _enable_demo_mode(monkeypatch)
    _, client = app_client

    resp = client.get("/api/v1/connections")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is True


def test_auth_me_reports_the_shared_demo_user(app_client, monkeypatch):
    """The protected /auth/me route resolves to the reserved demo identity."""
    _enable_demo_mode(monkeypatch)
    _, client = app_client

    resp = client.get("/auth/me")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["email"] == DEMO_USER_EMAIL


def test_demo_mode_creates_a_single_shared_user(app_client, monkeypatch):
    """Every anonymous request shares one demo row, not one per request."""
    _enable_demo_mode(monkeypatch)
    _, client = app_client

    client.get("/api/v1/connections")
    client.get("/auth/me")

    assert User.query.filter_by(email=DEMO_USER_EMAIL).count() == 1


def test_the_demo_database_can_be_attached_without_a_login(app_client, monkeypatch):
    """The auto-connect flow works for a visitor with no credentials."""
    from config import get_settings

    _enable_demo_mode(monkeypatch)
    monkeypatch.setattr(get_settings(), "DEMO_DB_URL", DEMO_URL)
    _, client = app_client

    resp = client.post("/api/v1/connections/demo")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["data"]["database"] == "demo_ai_db"
