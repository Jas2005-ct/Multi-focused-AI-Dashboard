"""Auth contract tests: password policy, validation errors, OAuth toggle.

Covers three behaviours that were broken and are easy to regress:

1. **Password policy** — the UI used to accept a 6-character password while
   the API demanded 8+ characters with upper/lower/digit, so registration
   failed with an opaque error.
2. **Validation error shape** — flask-openapi3 answers 422 with a pydantic
   error *list*, not the standard error envelope, so the client showed
   "Something went wrong". The list also echoed the rejected value, which
   meant the plaintext password came back in the response body.
3. **Google OAuth toggle** — OAuth is off by default; the routes must answer
   503 with a clear message instead of raising, and must come back to life
   when the flag is switched on.
"""

import pytest

# --- password policy -------------------------------------------------------


@pytest.mark.parametrize(
    ("password", "expected_fragment"),
    [
        ("abc123", "at least 8 characters"),
        ("abcdefgh", "uppercase"),
        ("ABCDEFGH", "lowercase"),
        ("Abcdefgh", "digit"),
    ],
)
def test_weak_password_rejected_with_readable_message(app_client, password, expected_fragment):
    _, client = app_client

    resp = client.post(
        "/auth/register",
        json={"email": "weak@example.com", "password": password, "name": "Weak"},
    )

    assert resp.status_code == 422, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is False
    assert body["error"] == "Validation failed"
    assert expected_fragment.lower() in body["message"].lower()


def test_validation_error_never_echoes_the_password(app_client):
    """The rejected value must not come back in the response body."""
    _, client = app_client
    password = "secret123"

    resp = client.post(
        "/auth/register",
        json={"email": "echo@example.com", "password": password, "name": "Echo"},
    )

    assert resp.status_code == 422
    assert password not in resp.get_data(as_text=True)


def test_strong_password_registers(app_client):
    _, client = app_client

    resp = client.post(
        "/auth/register",
        json={"email": "strong@example.com", "password": "Password123", "name": "Strong"},
    )

    assert resp.status_code == 201, resp.get_data(as_text=True)
    body = resp.get_json()
    assert {"token", "refreshToken", "user"} <= set(body)


# --- Google OAuth toggle ---------------------------------------------------


def test_google_login_disabled_answers_503(app_client):
    """With OAuth off the route must answer 503, not raise an AttributeError."""
    _, client = app_client

    resp = client.get("/auth/login")

    assert resp.status_code == 503, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is False
    assert "disabled" in body["error"].lower()


def test_google_callback_disabled_answers_503(app_client):
    _, client = app_client

    resp = client.get("/auth/callback")

    assert resp.status_code == 503, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is False


def test_oauth_re_enables_with_the_flag(app_client, monkeypatch):
    """Flipping ENABLE_GOOGLE_OAUTH (plus credentials) brings OAuth back.

    This is the re-enable path: set the flag + client id/secret and the
    routes stop answering 503. The redirect target is not asserted (it
    would need a live Google endpoint), only that the guard is lifted.
    """
    import importlib

    import config

    monkeypatch.setenv("ENABLE_GOOGLE_OAUTH", "true")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    config.get_settings.cache_clear()

    try:
        import app as app_module

        importlib.reload(app_module)
        application = app_module.create_app()
        assert application.config["GOOGLE_OAUTH_ENABLED"] is True
    finally:
        config.get_settings.cache_clear()
