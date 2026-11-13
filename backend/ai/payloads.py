"""Typed payloads for the AI layer.

The agent, the SQL chain and the introspection tools exchange plain dicts.
Naming their shape here turns a typo in a key into a type error instead of a
runtime ``KeyError``, and makes the shape discoverable from the signature.

These are ``TypedDict``s rather than Pydantic models on purpose: they
describe data that is produced and consumed inside the backend, so they carry
no runtime cost and change no behaviour. The HTTP-facing shapes live in
``ai_dashboard/schemas.py``.
"""

from typing import Any, Dict, List, Optional, TypedDict

from connections.payloads import FullSchema, TableSchema

# A row as the driver returned it: column name -> value.
Row = Dict[str, Any]


class ToolCallTrace(TypedDict):
    """One tool invocation, recorded for debugging."""

    name: str
    args: Dict[str, Any]
    result: Any


class UsageSummary(TypedDict):
    """Token counters for the LLM client."""

    total_requests: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int


class RouterResult(TypedDict, total=False):
    """The payload the AI layer hands back to the route.

    One shape for every path, because the route consumes it as a bag: it
    checks for ``error`` first, then branches on ``type``. A union of narrower
    TypedDicts does not narrow on ``"error" in result``, and mypy requires
    identical key sets when assigning one TypedDict to another — so the
    variants are expressed as which keys are present, not as separate types.

    Every key is optional because which ones are present depends on the path:
    the agent fills in the result fields, the SQL chain fills in ``sql`` /
    ``error_type``, and a failure fills in ``error`` / ``error_type``.
    """

    type: str
    answer: str
    sql: str
    output_query: str
    metadata: Dict[str, Any]
    toolCalls: List[ToolCallTrace]
    tables: List[str]
    rows: List[Row]
    count: Optional[int]
    table: Optional[str]
    error: str
    error_type: str
    usage: UsageSummary


__all__ = [
    "FullSchema",
    "Row",
    "RouterResult",
    "TableSchema",
    "ToolCallTrace",
    "UsageSummary",
]
