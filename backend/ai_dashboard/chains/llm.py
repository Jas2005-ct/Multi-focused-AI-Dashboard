"""Chat model factory.

Phase 1 of the LangChain refactor: everything the old prompts.py did with
requests.Session, manual headers, urllib3 Retry and timeouts is replaced by
a single ChatOpenAI instance pointed at OpenRouter's OpenAI-compatible API.
"""

import logging

from langchain_openai import ChatOpenAI

from settings import OPEN_ROUTER_API_KEY, OPEN_ROUTER_MODEL

logger = logging.getLogger(__name__)

OPEN_ROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"


def get_llm(
    temperature: float = 0.1,
    max_tokens: int = 500,
    timeout: int = 30,
    max_retries: int = 3,
) -> ChatOpenAI:
    """Create a chat model client for OpenRouter.

    Args:
        temperature: Sampling temperature (low = more deterministic SQL).
        max_tokens: Maximum tokens the model may generate.
        timeout: Request timeout in seconds.
        max_retries: Automatic retries on 429/5xx with backoff.

    Returns:
        A configured ChatOpenAI instance.
    """
    return ChatOpenAI(
        model=OPEN_ROUTER_MODEL,
        base_url=OPEN_ROUTER_BASE_URL,
        api_key=OPEN_ROUTER_API_KEY,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )
