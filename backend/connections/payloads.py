"""Typed payloads for the connections layer.

The service layer returns plain dicts. Naming their shape here turns a typo
in a key into a type error instead of a runtime ``KeyError``, and makes the
shape discoverable from the signature.

These are ``TypedDict``s rather than Pydantic models on purpose: they
describe data that is produced and consumed inside the backend, so they carry
no runtime cost and change no behaviour. The HTTP-facing shapes live in
``connections/schemas.py`` and ``ai_dashboard/schemas.py``.
"""

from typing import Any, Dict, List, Optional, TypedDict


class ParsedConnection(TypedDict):
    """The components of a connection string."""

    host: str
    port: int
    database: str
    username: str
    password: str


class ConnectionSummary(TypedDict):
    """A saved connection, without secrets."""

    id: int
    name: Optional[str]
    host: str
    port: int
    database: str
    username: str
    db_type: str
    sslmode: Optional[str]
    created_at: Optional[str]
    last_used: Optional[str]


class ConnectionDetail(ConnectionSummary):
    """A saved connection plus the tables it exposes."""

    tables: List[str]


class ConnectionPage(TypedDict):
    """One page of saved connections."""

    page: int
    per_page: int
    total: int
    pages: int
    connections: List[ConnectionSummary]


class TestConnectionResult(TypedDict):
    """The outcome of probing a saved connection."""

    success: bool
    message: str


class ColumnSchema(TypedDict):
    """One column of a target table."""

    name: str
    type: str
    nullable: bool
    default: Optional[str]


class TableSchema(TypedDict):
    """A target table and its columns."""

    table_name: str
    columns: List[ColumnSchema]


class FullSchema(TypedDict):
    """Every table and column in the target database."""

    tables: List[TableSchema]


class PoolStats(TypedDict):
    """Connection-pool counters, for monitoring."""

    users_with_pools: int
    total_pools: int
    pool_ttl_seconds: int
    max_pools_per_user: int


# A row as the driver returned it: column name -> value.
Row = Dict[str, Any]
