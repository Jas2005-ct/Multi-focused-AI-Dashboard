"""LLM factory with provider fallbacks, retries, and usage tracking (Phase 4)."""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig

from config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    env_prefix: str
    fallback_prefix: Optional[str]
    aliases: set[str]
    defaults: Tuple[str, str, str]  # (api_key, model, base_url)


_REGISTRY: dict[str, ProviderConfig] = {
    "zen": ProviderConfig(
        name="OpenCode Zen",
        env_prefix="OPEN_ZEN",
        fallback_prefix="OPENCODE_ZEN",
        aliases={"OPEN_ZEN", "OPENCODE_ZEN", "OPENCODE", "ZEN"},
        defaults=(get_settings().OPEN_ZEN_API_KEY, get_settings().OPEN_ZEN_MODEL, get_settings().OPEN_ZEN_BASE_URL),
    ),
    "openrouter": ProviderConfig(
        name="OpenRouter",
        env_prefix="OPEN_ROUTER",
        fallback_prefix=None,
        aliases={"OPENROUTER", "OPEN_ROUTER", "ROUTER"},
        defaults=(get_settings().OPEN_ROUTER_API_KEY, get_settings().OPEN_ROUTER_MODEL, get_settings().OPEN_ROUTER_BASE_URL),
    ),
}

_ALIAS_TO_KEY: dict[str, str] = {
    alias: key for key, cfg in _REGISTRY.items() for alias in cfg.aliases
}


def _resolve_env(prefix: str, fallback_prefix: Optional[str], suffix: str, default: str) -> str:
    val = get_settings().__dict__.get(f"{prefix}_{suffix}", "")
    if val:
        return val
    if fallback_prefix:
        val = get_settings().__dict__.get(f"{fallback_prefix}_{suffix}", "")
        if val:
            return val
    return default


def get_provider_config(provider: Optional[str] = None) -> Tuple[str, str, str, str]:
    active_provider = (
        provider or get_settings().API_KEY_PROVIDER or "OPEN_ZEN"
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


class LLMUsageTracker:
    """Track LLM usage for cost monitoring and debugging."""

    def __init__(self):
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_requests = 0

    def add_usage(self, prompt_tokens: int, completion_tokens: int):
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_requests += 1

    def get_summary(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
        }

    def reset(self):
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_requests = 0


# Global usage tracker
usage_tracker = LLMUsageTracker()


def get_llm(
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 3000,
    timeout: int = 30,
    max_retries: int = 3,
    provider: Optional[str] = None,
) -> ChatOpenAI:
    """Create a chat model client with retries, timeout, and usage tracking."""
    provider_name, api_key, default_model, base_url = get_provider_config(provider)
    resolved_model = model or default_model

    if not api_key:
        raise ValueError(
            f"API key for provider '{provider_name}' is not set. "
            f"Please configure OPEN_ZEN_API_KEY or OPEN_ROUTER_API_KEY in your .env file."
        )

    logger.info(
        f"Initializing LLM: provider='{provider_name}', model='{resolved_model}', base_url='{base_url}'"
    )

    # Custom callback to track usage
    def track_usage(response):
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage_tracker.add_usage(
                response.usage_metadata.get('input_tokens', 0),
                response.usage_metadata.get('output_tokens', 0),
            )

    return ChatOpenAI(
        model=resolved_model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
        callbacks=[track_usage],
    )