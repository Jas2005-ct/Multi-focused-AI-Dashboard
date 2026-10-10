"""Phase 1: config fail-fast, readiness, request-ID, JSON error envelope."""

import pytest

from config import get_settings


@pytest.fixture()
def isolated_settings(monkeypatch):
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_prod_rejects_short_secret(isolated_settings):
    isolated_settings.setenv("FLASK_ENV", "production")
    isolated_settings.setenv("SECRET_KEY", "too-short")
    from app import create_app

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


def test_prod_rejects_wildcard_origins(isolated_settings):
    isolated_settings.setenv("FLASK_ENV", "production")
    isolated_settings.setenv("SECRET_KEY", "prod-secret-key-32-chars-minimum!")
    isolated_settings.setenv("ALLOWED_ORIGINS", "*")
    from app import create_app

    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        create_app()


def test_dev_boots_with_ephemeral_secret_warning(isolated_settings, recwarn):
    isolated_settings.setenv("FLASK_ENV", "development")
    isolated_settings.setenv("SECRET_KEY", "")
    from app import create_app

    create_app()
    assert any("SECRET_KEY" in str(w.message) for w in recwarn.list)


def test_ready_endpoint(app_client):
    _, client = app_client
    resp = client.get("/ready")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "connected"


def test_request_id_present_and_echoed(app_client):
    _, client = app_client
    plain = client.get("/health")
    assert plain.headers.get("X-Request-ID"), "response must carry X-Request-ID"

    echoed = client.get("/health", headers={"X-Request-ID": "phase1-probe"})
    assert echoed.headers.get("X-Request-ID") == "phase1-probe"
    assert echoed.get_json() is not None


def test_unknown_route_returns_json_envelope(app_client):
    _, client = app_client
    resp = client.get("/definitely-missing-route")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["success"] is False
    assert "request_id" in body
