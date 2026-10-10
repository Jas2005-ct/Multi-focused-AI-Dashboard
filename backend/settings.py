"""Deprecated compatibility shim (Phase 1).

Canonical settings live in :mod:`config`. This module re-exports the names
historically imported from here so unrelated code keeps working during the
revamp. Removal: Phase 5 (all importers switch to ``config.get_settings()``).
"""

import warnings

warnings.warn(
    "settings.py is deprecated; use config.get_settings() instead.",
    DeprecationWarning,
    stacklevel=2,
)

from config import get_settings as _get_settings

_settings = _get_settings()

API_KEY_PROVIDER: str = _settings.API_KEY_PROVIDER

OPEN_ROUTER_API_KEY: str = _settings.OPEN_ROUTER_API_KEY
OPEN_ROUTER_MODEL: str = _settings.OPEN_ROUTER_MODEL
OPEN_ROUTER_BASE_URL: str = _settings.OPEN_ROUTER_BASE_URL

OPEN_ZEN_API_KEY: str = _settings.OPEN_ZEN_API_KEY
OPEN_ZEN_MODEL: str = _settings.OPEN_ZEN_MODEL
OPEN_ZEN_BASE_URL: str = _settings.OPEN_ZEN_BASE_URL

DATABASE_URL: str = _settings.DATABASE_URL
ALLOWED_ORIGINS: list[str] = _settings.allowed_origin_list
RATE_LIMIT_PER_MIN: int = _settings.RATE_LIMIT_PER_MIN
