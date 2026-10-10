"""Phase 2: rotating refresh tokens, hardened auth gate, OTP discipline."""

from datetime import datetime, timedelta, timezone

import jwt


def _register(client, email="phase2@example.com", password="Password123"):
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": password, "name": "Phase Two"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


# --- Token pair issuance ---


def test_register_and_login_issue_refresh_pair(app_client):
    _, client = app_client
    reg = _register(client)
    assert set(reg) >= {"token", "refreshToken", "user"}

    login = client.post(
        "/auth/login", json={"email": "phase2@example.com", "password": "Password123"}
    )
    assert login.status_code == 200
    assert set(login.get_json()) >= {"token", "refreshToken", "user"}


def test_refresh_token_rejected_as_access(app_client):
    _, client = app_client
    reg = _register(client)
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {reg['refreshToken']}"})
    assert resp.status_code == 401
    assert resp.get_json()["code"] == "INVALID_TOKEN"


def test_legacy_typ_less_token_accepted_until_expiry(app_client):
    app, client = app_client
    reg = _register(client)
    legacy = jwt.encode(
        {
            "user_id": reg["user"]["id"],
            "email": reg["user"]["email"],
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        app.secret_key,
        algorithm="HS256",
    )
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {legacy}"})
    assert resp.status_code == 200, resp.get_data(as_text=True)


def test_expired_access_returns_token_expired_code(app_client):
    app, client = app_client
    reg = _register(client)
    expired = jwt.encode(
        {
            "typ": "access",
            "user_id": reg["user"]["id"],
            "email": reg["user"]["email"],
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        app.secret_key,
        algorithm="HS256",
    )
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401
    assert resp.get_json()["code"] == "TOKEN_EXPIRED"


# --- Rotation + reuse detection ---


def test_refresh_rotation_and_reuse_burns_family(app_client):
    _, client = app_client
    reg = _register(client)

    first = client.post("/auth/refresh", json={"refreshToken": reg["refreshToken"]})
    assert first.status_code == 200, first.get_data(as_text=True)
    pair_b = first.get_json()

    second = client.post("/auth/refresh", json={"refreshToken": pair_b["refreshToken"]})
    assert second.status_code == 200, second.get_data(as_text=True)

    # Replaying the already-rotated token fails closed and burns the family.
    replay = client.post("/auth/refresh", json={"refreshToken": reg["refreshToken"]})
    assert replay.status_code == 401

    burned = client.post("/auth/refresh", json={"refreshToken": pair_b["refreshToken"]})
    assert burned.status_code == 401


def test_refresh_invalid_token_rejected(app_client):
    _, client = app_client
    resp = client.post("/auth/refresh", json={"refreshToken": "not-a-token"})
    assert resp.status_code == 401


# --- /me ---


def test_me_returns_current_user(app_client, auth_headers):
    _, client = app_client
    headers, _ = auth_headers
    resp = client.get("/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["email"] == "phase0@example.com"


# --- OTP discipline ---


def test_forgot_password_uniform_for_unknown_email(app_client):
    _, client = app_client
    resp = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_forgot_password_uniform_for_google_account(app_client):
    app, client = app_client
    from auths.models import User, db

    with app.app_context():
        db.session.add(User(google_id="google-sub-1", email="gonly@example.com", name="G"))
        db.session.commit()
    resp = client.post("/auth/forgot-password", json={"email": "gonly@example.com"})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_otp_resend_cooldown(app_client, auth_headers):
    _, client = app_client
    _, email = auth_headers
    first = client.post("/auth/forgot-password", json={"email": email})
    assert first.status_code == 200
    second = client.post("/auth/resend-otp", json={"email": email})
    assert second.status_code == 429, second.get_data(as_text=True)


def test_otp_verify_reset_end_to_end(app_client, auth_headers):
    _, client = app_client
    from auths.otp_store import otp_store

    _, email = auth_headers
    assert client.post("/auth/forgot-password", json={"email": email}).status_code == 200
    entry = otp_store.get(email)
    assert entry is not None
    otp, _, _ = entry

    assert (
        client.post("/auth/verify-otp", json={"email": email, "otp": "000000"}).status_code == 400
    )
    assert client.post("/auth/verify-otp", json={"email": email, "otp": otp}).status_code == 200
    reset = client.post(
        "/auth/reset-password",
        json={"email": email, "otp": otp, "new_password": "Newpass123"},
    )
    assert reset.status_code == 200, reset.get_data(as_text=True)
    login = client.post("/auth/login", json={"email": email, "password": "Newpass123"})
    assert login.status_code == 200
