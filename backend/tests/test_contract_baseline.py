"""Phase 0 contract snapshots — frozen pre-revamp behavior.

No network, no LLM calls. Every test must stay green through Phase 1-7
unless its contract is intentionally changed (then update the test + note
it in the PR body). Covers: health, auth, auth-gating, request validation,
write-guard, SQL safety gate, Fernet crypto, OTP format.
"""

import re

import pytest
from pydantic import ValidationError

# --- Health ---


def test_health_shape(app_client):
    _, client = app_client
    resp = client.get("/health")
    body = resp.get_json()
    assert set(body) >= {"status", "database"}
    assert body["status"] in ("ok", "error")
    assert body["database"] in ("connected", "error", "unknown")


# --- Auth contracts ---


def test_register_login_roundtrip(app_client):
    _, client = app_client
    reg = client.post(
        "/auth/register",
        json={"email": "roundtrip@example.com", "password": "Password123", "name": "RT"},
    )
    assert reg.status_code == 201, reg.get_data(as_text=True)
    reg_body = reg.get_json()
    assert set(reg_body) >= {"token", "user"}
    assert reg_body["user"]["email"] == "roundtrip@example.com"

    login = client.post(
        "/auth/login",
        json={"email": "roundtrip@example.com", "password": "Password123"},
    )
    assert login.status_code == 200
    assert set(login.get_json()) >= {"token", "user"}


def test_register_weak_password_rejected(app_client):
    _, client = app_client
    resp = client.post(
        "/auth/register",
        json={"email": "weak@example.com", "password": "short", "name": "W"},
    )
    # flask-openapi3 surfaces Pydantic body errors as 422.
    assert resp.status_code == 422, resp.get_data(as_text=True)


def test_register_duplicate_conflict(app_client, auth_headers):
    _, client = app_client
    _, email = auth_headers
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": "Password123", "name": "Dupe"},
    )
    assert resp.status_code == 409, resp.get_data(as_text=True)


def test_login_invalid_credentials(app_client, auth_headers):
    _, client = app_client
    _, email = auth_headers
    resp = client.post("/auth/login", json={"email": email, "password": "Wrongpass1"})
    assert resp.status_code == 401


# --- Auth gating on /api ---


def test_sql_query_requires_auth(app_client):
    _, client = app_client
    # NOTE (baseline quirk): body validation runs before require_auth, so an
    # explicitly-null db_id yields 422 even without a token. Omit db_id to
    # isolate the auth gate.
    resp = client.post("/api/sql-query/", json={"sentence": "list tables"})
    assert resp.status_code == 401, resp.get_data(as_text=True)


def test_sql_query_invalid_body_without_auth_is_422(app_client):
    """Locks current ordering: schema validation precedes the auth check."""
    _, client = app_client
    resp = client.post("/api/sql-query/", json={"sentence": "list tables", "db_id": None})
    assert resp.status_code == 422, resp.get_data(as_text=True)


def test_get_connections_requires_auth(app_client):
    _, client = app_client
    # Phase 2: session fallback removed — every API route answers 401 JSON,
    # never a browser redirect (supersedes the Phase 0 302 lock-in).
    plain = client.get("/api/get-connections/")
    assert plain.status_code == 401, plain.get_data(as_text=True)
    assert plain.get_json()["code"] == "MISSING_TOKEN"

    as_json = client.get("/api/get-connections/", headers={"Accept": "application/json"})
    assert as_json.status_code == 401, as_json.get_data(as_text=True)


def test_sql_query_rejects_empty_sentence(app_client, auth_headers):
    _, client = app_client
    headers, _ = auth_headers
    resp = client.post("/api/sql-query/", json={"sentence": "   "}, headers=headers)
    # flask-openapi3 surfaces Pydantic body errors as 422.
    assert resp.status_code == 422, resp.get_data(as_text=True)


# --- write_guard snapshot ---


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("show me all users", False),
        ("how many tables are there", False),
        ("list all skills", False),
        ("insert a new user", True),
        ("please delete old rows", True),
        ("update my profile", True),
        ("drop the temp table", True),
        ("create an index", True),
        ("", False),
    ],
)
def test_write_guard_snapshot(sentence, expected):
    from ai_dashboard.write_guard import is_write_intent

    assert is_write_intent(sentence) is expected


# --- SQL safety gate snapshot ---


@pytest.mark.parametrize(
    "query",
    [
        "SELECT id, email FROM users WHERE active = true",
        "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent",
    ],
)
def test_sql_safety_allows_reads(query):
    from ai_dashboard.chains.sql_chain import _validate_sql_safety

    ok, _ = _validate_sql_safety(query)
    assert ok is True


@pytest.mark.parametrize(
    "query",
    [
        "DROP TABLE users",
        "DELETE FROM users",
        "INSERT INTO users VALUES (1)",
        "SELECT * FROM users UNION SELECT * FROM admins",
        "SELECT * FROM users; DROP TABLE users",
        "SELECT SLEEP(5)",
    ],
)
def test_sql_safety_blocks_dangerous(query):
    from ai_dashboard.chains.sql_chain import _validate_sql_safety

    ok, _ = _validate_sql_safety(query)
    assert ok is False


# --- Pydantic schema snapshots ---


def test_prompt_request_rejects_empty():
    from ai_dashboard.schemas import PromptRequest

    with pytest.raises(ValidationError):
        PromptRequest(sentence="   ")


def test_db_connection_request_validation():
    from ai_dashboard.schemas import DBConnectionRequest

    with pytest.raises(ValidationError):
        DBConnectionRequest(port=99999)
    with pytest.raises(ValidationError):
        DBConnectionRequest(db_type="oracle")


# --- Crypto snapshot ---


def test_crypto_roundtrip():
    from security.crypto import decrypt_value, encrypt_value

    token = encrypt_value("s3cr3t-password")
    assert token != "s3cr3t-password"
    assert decrypt_value(token) == "s3cr3t-password"


def test_crypto_legacy_plaintext_fallback():
    """Current lenient behavior: undecryptable values pass through.

    Locked here so Phase 3 (strict crypto) changes it deliberately.
    """
    from security.crypto import decrypt_value

    assert decrypt_value("plaintext-legacy-value") == "plaintext-legacy-value"


# --- OTP format ---


def test_otp_is_six_digits():
    from auths.otp_store import generate_otp

    for _ in range(25):
        assert re.fullmatch(r"\d{6}", generate_otp())
