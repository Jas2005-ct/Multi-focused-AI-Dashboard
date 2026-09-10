"""Chat model factory.

Dynamically configures and instantiates ChatOpenAI based on the active provider
defined in .env (API_KEY_PROVIDER: OPEN_ZEN or OPENROUTER).
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from langchain_openai import ChatOpenAI

from settings import (
    API_KEY_PROVIDER,
    OPEN_ROUTER_API_KEY,
    OPEN_ROUTER_MODEL,
    OPEN_ROUTER_BASE_URL,
    OPEN_ZEN_API_KEY,
    OPEN_ZEN_MODEL,
    OPEN_ZEN_BASE_URL,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    env_prefix: str
    fallback_prefix: Optional[str]
    aliases: set[str]
    defaults: tuple[str, str, str]  # (api_key, model, base_url)


_REGISTRY: dict[str, ProviderConfig] = {
    "zen": ProviderConfig(
        name="OpenCode Zen",
        env_prefix="OPEN_ZEN",
        fallback_prefix="OPENCODE_ZEN",
        aliases={"OPEN_ZEN", "OPENCODE_ZEN", "OPENCODE", "ZEN"},
        defaults=(OPEN_ZEN_API_KEY, OPEN_ZEN_MODEL, OPEN_ZEN_BASE_URL),
    ),
    "openrouter": ProviderConfig(
        name="OpenRouter",
        env_prefix="OPEN_ROUTER",
        fallback_prefix=None,
        aliases={"OPENROUTER", "OPEN_ROUTER", "ROUTER"},
        defaults=(OPEN_ROUTER_API_KEY, OPEN_ROUTER_MODEL, OPEN_ROUTER_BASE_URL),
    ),
}

_ALIAS_TO_KEY: dict[str, str] = {
    alias: key for key, cfg in _REGISTRY.items() for alias in cfg.aliases
}


def _resolve_env(prefix: str, fallback_prefix: Optional[str], suffix: str, default: str) -> str:
    """Resolve single env var with optional fallback prefix then settings default."""
    val = os.getenv(f"{prefix}_{suffix}")
    if val:
        return val
    if fallback_prefix:
        val = os.getenv(f"{fallback_prefix}_{suffix}")
        if val:
            return val
    return default


def get_provider_config(provider: Optional[str] = None) -> Tuple[str, str, str, str]:
    """Resolve the active LLM provider configuration.

    Args:
        provider: Explicit provider override (e.g. 'OPEN_ZEN', 'OPENROUTER').
                  If None, reads from API_KEY_PROVIDER in settings / env.

    Returns:
        Tuple of (provider_name, api_key, model, base_url)
    """
    active_provider = (
        provider or os.getenv("API_KEY_PROVIDER") or API_KEY_PROVIDER or "OPEN_ZEN"
    ).strip().upper()

    key = _ALIAS_TO_KEY.get(active_provider)
    if key is None:
        logger.warning(f"Unknown API_KEY_PROVIDER '{active_provider}'. Defaulting to OPEN_ZEN.")
        key = "zen"

    cfg = _REGISTRY[key]
    api_key = _resolve_env(cfg.env_prefix, cfg.fallback_prefix, "API_KEY", cfg.defaults[0])
    model = _resolve_env(cfg.env_prefix, cfg.fallback_prefix, "MODEL", cfg.defaults[1])
    base_url = _resolve_env(cfg.env_prefix, cfg.fallback_prefix, "BASE_URL", cfg.defaults[2])

    return cfg.name, api_key, model, base_url


def get_llm(
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 3000,
    timeout: int = 30,
    max_retries: int = 3,
    provider: Optional[str] = None,
) -> ChatOpenAI:
    """Create a chat model client for the active provider (OpenRouter or OpenCode Zen).

    Args:
        model: Optional model override. If not provided, uses provider default from env.
        temperature: Sampling temperature (low = more deterministic SQL/JSON).
        max_tokens: Maximum tokens the model may generate.
        timeout: Request timeout in seconds.
        max_retries: Automatic retries on 429/5xx with backoff.
        provider: Optional provider override ('OPEN_ZEN' or 'OPENROUTER').

    Returns:
        A configured ChatOpenAI instance.
    """
    provider_name, api_key, default_model, base_url = get_provider_config(provider)
    resolved_model = model or default_model

    if not api_key:
        raise ValueError(
            f"API key for provider '{provider_name}' is not set. "
            f"Please configure OPEN_ZEN_API_KEY or OPEN_ROUTER_API_KEY in your .env file."
        )

    logger.info(
        f"Initializing LLM with provider='{provider_name}', model='{resolved_model}', base_url='{base_url}'"
    )
    return ChatOpenAI(
        model=resolved_model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )

