"""Typed payloads for the auth layer."""

from typing import TypedDict


class TokenPair(TypedDict):
    """An issued access/refresh pair."""

    token: str
    refreshToken: str
    jti: str


class AccessTokenPayload(TypedDict, total=False):
    """The decoded access-token claims.

    Legacy tokens issued before Phase 2 carry no ``typ``, so it is optional.
    """

    typ: str
    user_id: int
    email: str
    exp: int


class RefreshTokenPayload(TypedDict, total=False):
    """The decoded refresh-token claims."""

    typ: str
    jti: str
    user_id: int
    exp: int


__all__ = [
    "AccessTokenPayload",
    "RefreshTokenPayload",
    "TokenPair",
]
