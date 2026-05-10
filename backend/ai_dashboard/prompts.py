import json
import logging
import re
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


def _clean_llm_response(content: str) -> str:
    """Clean markdown code blocks and extra whitespace from LLM response."""
    content = content.strip()
    
    # Remove markdown code block wrappers
    if content.startswith('```json'):
        content = content[7:]
    elif content.startswith('```'):
        content = content[3:]
    
    if content.endswith('```'):
        content = content[:-3]
    
    return content.strip()


def _validate_sql_safety(query: str) -> tuple[bool, str]:
    """
    Validate SQL query for potentially dangerous patterns.
    
    Returns:
        Tuple of (is_safe, error_message)
    """
    query_upper = query.upper().strip()
    
    # Dangerous patterns that should not be in generated queries
    dangerous_patterns = [
        # Multiple statements (injection attempt)
        (r';\s*(DROP|DELETE|INSERT|UPDATE|CREATE|ALTER|GRANT|REVOKE|TRUNCATE|EXEC|EXECUTE|UNION|SELECT)', 
         "Multiple SQL statements detected - potential injection"),
        # Union-based injection
        (r'UNION\s+SELECT', "UNION SELECT detected - potential injection"),
        # Comment-based injection attempts
        (r'/\*.*\*/', "Block comment detected - potential injection"),
        (r'--.*$', "Line comment detected - potential injection", re.MULTILINE),
        # Stacked queries
        (r';\s*[^\s]', "Stacked query detected - potential injection"),
        # Time-based blind injection
        (r'(SLEEP|BENCHMARK|WAITFOR|DELAY)\s*\(', "Time delay function detected - potential injection"),
        # Out-of-band injection
        (r'(LOAD_FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE)', "File operation detected - potential injection"),
        # xp_cmdshell and similar
        (r'XP_CMDSHELL|SP_OACREATE|SP_OAMETHOD', "System command execution detected"),
    ]
    
    for pattern in dangerous_patterns:
        flags = pattern[2] if len(pattern) > 2 else 0
        if re.search(pattern[0], query_upper, flags):
            return False, pattern[1]
    
    # Ensure query starts with allowed keywords (SELECT, WITH for CTEs)
    allowed_starts = ['SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE']
    first_word = query_upper.split()[0] if query_upper.split() else ''
    
    if first_word not in allowed_starts:
        return False, f"Query must start with SELECT, WITH, INSERT, UPDATE, or DELETE. Found: {first_word}"
    
    return True, ""


@dataclass
class LLMConfig:
    """Configuration for LLM API requests."""
    url: str = "https://openrouter.ai/api/v1/chat/completions"
    model: str = "openai/gpt-oss-120b:free"
    temperature: float = 0.1
    max_tokens: int = 500
    timeout: int = 30
    max_retries: int = 3



SQL_SYSTEM_PROMPT = """
You are an expert PostgreSQL SQL Query Compiler.

Your responsibility is to convert user requests into valid, optimized PostgreSQL SQL queries.

IMPORTANT:
You must ALWAYS return ONLY a valid JSON object.
Do NOT return explanations, markdown, comments, notes, code fences, or additional text.

STRICT OUTPUT FORMAT:
{
  "output_query": "POSTGRESQL_QUERY"
}

MANDATORY RULES:
1. Output must be valid parsable JSON
2. Response must contain ONLY one key:
   - output_query
3. SQL query must:
   - be valid PostgreSQL syntax
   - be production-safe
   - be properly formatted as a single string
4. Escape internal double quotes using:
   \\\"
5. Never include:
   - markdown
   - ``` blocks
   - comments
   - natural language explanations
   - extra JSON keys
6. If aggregation is required:
   - always use proper GROUP BY
7. Use explicit column names whenever possible
8. Avoid SELECT *
9. Generate optimized SQL queries whenever possible
10. Preserve exact table and column names provided by the user

VALID RESPONSE EXAMPLE:
{"output_query":"SELECT id, name FROM users WHERE name = \\"John\\";"}

INVALID RESPONSE EXAMPLES:

Example 1:
```json
{"output_query":"SELECT * FROM users"}
````

Example 2:
Here is your query:
{"output_query":"SELECT * FROM users"}

Example 3:
{
"query":"SELECT * FROM users"
}

FINAL INSTRUCTION:
Return ONLY the JSON object.
"""

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
    config: LLMConfig,
    schema_context: Optional[str] = None
) -> tuple[int, str]:
    """
    Make LLM API call with retry and timeout handling.
    
    Args:
        sentence: User input request
        config: LLM configuration
        schema_context: Optional database schema context
        
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
    
    # Build system prompt with schema context if provided
    system_prompt = SQL_SYSTEM_PROMPT
    if schema_context:
        system_prompt = f"{schema_context}\n\n{SQL_SYSTEM_PROMPT}"
    
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_prompt(sentence.sentence)}
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
        
        # Log full response for debugging (truncate if too large)
        debug_data = str(data)[:500] + "..." if len(str(data)) > 500 else str(data)
        logger.debug(f"LLM API raw response: {debug_data}")
        
        # Check for API error responses
        if "error" in data:
            error_msg = data["error"].get("message", "Unknown API error")
            error_code = data["error"].get("code", "unknown")
            raise ValueError(f"API error: {error_code} - {error_msg}")
        
        # Validate response structure
        if "choices" not in data or not data["choices"]:
            logger.error(f"Unexpected API response structure: {debug_data}")
            raise ValueError(f"API response missing 'choices' field. Got keys: {list(data.keys())}")
        
        if "message" not in data["choices"][0]:
            raise ValueError("API response missing 'message' in first choice")
            
        content = data["choices"][0]["message"].get("content")
        if not content:
            raise ValueError("API response has empty content")
        
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
    # Clean markdown code blocks
    cleaned = _clean_llm_response(content)
    
    # Try to extract JSON from text that might contain other content
    # Look for JSON object pattern
    json_match = re.search(r'\{[^{}]*"output_query"[^{}]*\}', cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)
    
    try:
        # Try parsing as JSON first
        parsed = json.loads(cleaned)
        
        # Handle nested structure
        if isinstance(parsed, dict):
            if "output_query" in parsed:
                return QueryResponse(output_query=parsed["output_query"])
            return QueryResponse.model_validate(parsed)
        
        raise ValueError(f"Unexpected response type: {type(parsed)}")
        
    except json.JSONDecodeError as e:
        # Try more flexible regex fallback to extract SQL
        # Handle cases like: {"output_query": "SELECT ..."} or {"output_query":"SELECT..."}
        pattern = r'"output_query"\s*:\s*"(.*?(?<!\\))(?:"\s*\}|$)'
        match = re.search(pattern, cleaned, re.DOTALL)
        if match:
            sql = match.group(1).replace('\\"', '"').replace("\\'", "'").replace('\\n', '\n')
            logger.info(f"Extracted SQL using regex fallback from: {cleaned[:100]}...")
            return QueryResponse(output_query=sql.strip())
        
        # If response looks like raw SQL (contains SELECT, INSERT, etc.), use it directly
        sql_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER']
        upper_cleaned = cleaned.upper().strip()
        if any(upper_cleaned.startswith(kw) for kw in sql_keywords):
            logger.info(f"Using raw SQL response: {cleaned[:100]}...")
            return QueryResponse(output_query=cleaned.strip())
        
        # Last resort - log the problematic content
        logger.warning(f"Response not valid JSON, using as raw text: {cleaned[:200]}")
        return QueryResponse(output_query=cleaned.strip())
        
    except ValidationError as e:
        logger.error(f"Pydantic validation error: {e}")
        raise ValueError(f"Response validation failed: {e}")


def get_query_format(
    sentence: PromptRequest,
    config: Optional[LLMConfig] = None,
    schema_context: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convert natural language to SQL query using LLM.
    
    Args:
        sentence: User input wrapped in PromptRequest
        config: Optional custom LLM configuration
        schema_context: Optional database schema context for better accuracy
        
    Returns:
        Dict containing output_query or error details
    """
    config = config or LLMConfig()
    
    try:
        total_tokens, content = _call_llm_api(sentence, config, schema_context)
        
        logger.debug(f"Raw LLM content: {content}")
        
        result = _parse_response(content)
        
        # Validate SQL safety before returning
        is_safe, error_msg = _validate_sql_safety(result.output_query)
        if not is_safe:
            logger.warning(f"Potentially unsafe SQL detected: {error_msg}")
            return {"error": f"Generated query failed security validation: {error_msg}", "error_type": "security_error"}
        
        return {"output_query": result.output_query}
        
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


