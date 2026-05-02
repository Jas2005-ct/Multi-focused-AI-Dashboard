import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pydantic import ValidationError

from settings import OPEN_ROUTER_API_KEY
from ai_dashboard.schemas import QueryResponse, PromptRequest

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for LLM API requests."""
    url: str = "https://openrouter.ai/api/v1/chat/completions"
    model: str = "openai/gpt-oss-120b:free"
    temperature: float = 0.1
    max_tokens: int = 500
    timeout: int = 30
    max_retries: int = 3


SQL_SYSTEM_PROMPT = """You are a senior PostgreSQL SQL Query Compiler.

Your job is to convert user business requests into syntactically valid raw SQL queries.

Rules:
1. Return only executable SQL query.
2. No explanation.
3. No markdown.
4. No introductory text.

Return strictly in this JSON format:
{"output_query": "YOUR_SQL_QUERY_HERE"}"""


def _build_prompt(user_text: str) -> str:
    """Build user prompt with structured output instruction."""
    return f"Convert this request to a PostgreSQL query: {user_text}"


def _create_session(config: LLMConfig) -> requests.Session:
    """Create HTTP session with retry strategy and timeouts."""
    session = requests.Session()
    
    # Retry on transient errors (429, 500, 502, 503, 504)
    retry_strategy = Retry(
        total=config.max_retries,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    return session


def _call_llm_api(
    sentence: PromptRequest,
    config: LLMConfig
) -> tuple[int, str]:
    """
    Make LLM API call with retry and timeout handling.
    
    Args:
        sentence: User input request
        config: LLM configuration
        
    Returns:
        Tuple of (total_tokens, content)
        
    Raises:
        requests.RequestException: For API/connection errors
        ValueError: For unexpected response structure
    """
    headers = {
        "Authorization": f"Bearer {OPEN_ROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": SQL_SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(sentence.input)}
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "response_format": {"type": "json_object"}
    }
    
    session = _create_session(config)
    
    try:
        response = session.post(
            url=config.url,
            headers=headers,
            json=payload,
            timeout=config.timeout
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Validate response structure
        if "choices" not in data or not data["choices"]:
            raise ValueError("API response missing 'choices' field")
        
        if "message" not in data["choices"][0]:
            raise ValueError("API response missing 'message' in first choice")
            
        content = data["choices"][0]["message"].get("content")
        if not content:
            raise ValueError("API response has empty content")
        
        # Parse content if it's a JSON string inside content
        try:
            parsed_content = json.loads(content)
            if isinstance(parsed_content, dict) and "output_query" in parsed_content:
                content = parsed_content["output_query"]
        except json.JSONDecodeError:
            pass  # Content is not JSON, use as-is
        
        total_tokens = data.get("usage", {}).get("total_tokens", 0)
        
        logger.info(f"LLM request completed. Tokens used: {total_tokens}")
        return total_tokens, content
        
    except requests.Timeout:
        logger.error("LLM API request timed out")
        raise requests.RequestException("Request timed out after {}s".format(config.timeout))
        
    except requests.HTTPError as e:
        logger.error(f"LLM API HTTP error: {e.response.status_code} - {e.response.text}")
        raise
        
    finally:
        session.close()


def _parse_response(content: str) -> QueryResponse:
    """
    Parse and validate LLM response into QueryResponse.
    
    Args:
        content: Raw content from LLM
        
    Returns:
        Validated QueryResponse object
        
    Raises:
        ValueError: For JSON parsing or validation errors
    """
    try:
        # Try parsing as JSON first
        parsed = json.loads(content)
        
        # Handle nested structure
        if isinstance(parsed, dict):
            if "output_query" in parsed:
                return QueryResponse(output_query=parsed["output_query"])
            return QueryResponse.model_validate(parsed)
        
        raise ValueError(f"Unexpected response type: {type(parsed)}")
        
    except json.JSONDecodeError as e:
        # If not valid JSON, treat as raw SQL (fallback)
        logger.warning(f"Response not valid JSON, using as raw SQL: {content[:100]}")
        return QueryResponse(output_query=content.strip())
        
    except ValidationError as e:
        logger.error(f"Pydantic validation error: {e}")
        raise ValueError(f"Response validation failed: {e}")


def get_query_format(
    sentence: PromptRequest,
    config: Optional[LLMConfig] = None
) -> Dict[str, Any]:
    """
    Convert natural language to SQL query using LLM.
    
    Args:
        sentence: User input wrapped in PromptRequest
        config: Optional custom LLM configuration
        
    Returns:
        Dict containing output_query or error details
    """
    config = config or LLMConfig()
    
    try:
        total_tokens, content = _call_llm_api(sentence, config)
        
        logger.debug(f"Raw LLM content: {content}")
        
        result = _parse_response(content)
        
        return {
            "output_query": result.output_query,
            "metadata": {
                "tokens_used": total_tokens,
                "model": config.model
            }
        }
        
    except requests.RequestException as e:
        error_msg = f"API request failed: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg, "error_type": "api_error"}
        
    except ValueError as e:
        error_msg = f"Response parsing failed: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg, "error_type": "parsing_error"}
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.exception(error_msg)
        return {"error": error_msg, "error_type": "unexpected_error"}