"""Canonical application configuration (Phase 1).

Single source of truth for env-driven settings. Read exactly once per
process via :func:`get_settings` (cached); tests reset it with
``get_settings.cache_clear()``.

Fail-fast policy:
- ``SECRET_KEY`` shorter than 32 bytes -> RuntimeError in production,
  loud warning + ephemeral key otherwise (dev/test convenience).
- ``ALLOWED_ORIGINS`` containing ``*`` together with credentialed CORS
  -> RuntimeError in production.
- ``settings.py`` is a deprecated shim over this module (removal: Phase 5).
"""

import secrets
import warnings
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_BYTES = 32


class Settings(BaseSettings):
    """Environment-driven settings. Field names match process env vars."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Runtime
    FLASK_ENV: str = "development"
    SECRET_KEY: str = ""
    ENCRYPTION_KEY: str = ""
    DATABASE_URL: str = "sqlite:///app.db"
    FRONTEND_URL: str = "http://localhost:5173"
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    RATE_LIMIT_PER_MIN: int = 60

    # Google OAuth (optional; absent -> OAuth login disabled)
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # LLM providers (resolution + fallbacks live in ai_dashboard.chains.llm)
    API_KEY_PROVIDER: str = "OPEN_ZEN"
    OPEN_ROUTER_API_KEY: str = ""
    OPEN_ROUTER_MODEL: str = "nvidia/nemotron-3.5-lightning:free"
    OPEN_ROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPEN_ZEN_API_KEY: str = ""
    OPEN_ZEN_MODEL: str = "minimax-m3"
    OPEN_ZEN_BASE_URL: str = "https://opencode.ai/zen/v1"

    # OTP / email / workers
    OTP_BACKEND: str = ""
    REDIS_URL: str = ""
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""
    OTP_TTL_SECONDS: int = 300
    OTP_MAX_ATTEMPTS: int = 5
    OTP_EMAIL_BACKEND: str = "auto"
    EMAIL_FROM: str = "noreply@example.com"

    @field_validator("RATE_LIMIT_PER_MIN", "OTP_TTL_SECONDS", "OTP_MAX_ATTEMPTS")
    @classmethod
    def _must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be a positive integer")
        return v

    @property
    def is_production(self) -> bool:
        return self.FLASK_ENV.strip().lower() == "production"

    @property
    def allowed_origin_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    def ensure_secret_key(self) -> str:
        """Return an effective Flask secret, failing fast in production."""
        raw = (self.SECRET_KEY or "").strip()
        if raw and len(raw.encode("utf-8")) >= MIN_SECRET_BYTES:
            return raw
        if self.is_production:
            raise RuntimeError(
                "SECRET_KEY must be set to at least 32 bytes in production. "
                "Refusing to boot with an ephemeral key (stored DB credentials "
                "would become undecryptable after restart)."
            )
        warnings.warn(
            "SECRET_KEY is too short (< 32 bytes) or not set. "
            "Using an ephemeral key — set a proper SECRET_KEY in .env. "
            "Encrypted DB credentials will NOT survive restarts.",
            RuntimeWarning,
            stacklevel=2,
        )
        return secrets.token_urlsafe(32)

    def ensure_allowed_origins(self) -> list[str]:
        """Fail fast when credentialed CORS would be wide open in prod."""
        origins = self.allowed_origin_list
        if "*" in origins and self.is_production:
            raise RuntimeError(
                "ALLOWED_ORIGINS must not contain '*' in production when "
                "CORS supports credentials. List explicit origins instead."
            )
        if "*" in origins:
            warnings.warn(
                "ALLOWED_ORIGINS contains '*'; credentialed browsers will "
                "reject it. Prefer explicit origins.",
                RuntimeWarning,
                stacklevel=2,
            )
        return origins


def get_settings() -> Settings:
    """Return cached settings. Callers must not mutate the result."""
    return _get_settings_cached()


@lru_cache(maxsize=1)
def _get_settings_cached() -> Settings:
    # os.environ wins over .env inside BaseSettings; no explicit load_dotenv
    # here so import order stays side-effect free (fail-fast happens in the
    # factory via ensure_*).
    return Settings()


# Re-export cache control for tests/factory reloads.
get_settings.cache_clear = _get_settings_cached.cache_clear  # type: ignore[attr-defined]
