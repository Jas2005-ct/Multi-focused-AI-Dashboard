"""JWT issuance and verification with rotating refresh tokens (Phase 2).

Token model:
- access: 15 min, ``{"typ": "access", user_id, email, exp}``. Legacy tokens
  issued before Phase 2 carry no ``typ`` and are accepted until they expire.
- refresh: 7 days, ``{"typ": "refresh", jti, user_id, exp}``. Each use
  rotates: the presented ``jti`` row is revoked and a fresh pair issued.
  Presenting an unknown/revoked ``jti`` revokes the whole family (reuse
  detection) and fails closed.
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt

ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=7)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue_pair(user, secret: str) -> dict:
    """Return ``{"token", "refreshToken", "jti"}`` for a user row."""
    jti = uuid.uuid4().hex
    access = jwt.encode(
        {
            "typ": "access",
            "user_id": user.id,
            "email": user.email,
            "exp": _now() + ACCESS_TTL,
        },
        secret,
        algorithm="HS256",
    )
    refresh = jwt.encode(
        {"typ": "refresh", "jti": jti, "user_id": user.id, "exp": _now() + REFRESH_TTL},
        secret,
        algorithm="HS256",
    )
    return {"token": access, "refreshToken": refresh, "jti": jti}


def decode_access(token: str, secret: str) -> dict:
    """Decode an access token; legacy typ-less tokens still accepted."""
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    if payload.get("typ") not in (None, "access"):
        raise jwt.InvalidTokenError("not an access token")
    if not payload.get("user_id"):
        raise jwt.InvalidTokenError("missing subject")
    return payload


def decode_refresh(token: str, secret: str) -> dict:
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    if payload.get("typ") != "refresh" or not payload.get("jti"):
        raise jwt.InvalidTokenError("not a refresh token")
    return payload
