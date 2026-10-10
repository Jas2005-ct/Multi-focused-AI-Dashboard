"""Connection schemas (Phase 3)."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


class ConnectionCreate(BaseModel):
    """Request to create a new connection."""
    name: Optional[str] = Field(None, max_length=100)
    host: str = Field("localhost", max_length=255)
    port: int = Field(5432, ge=1, le=65535)
    database: str = Field(..., max_length=100)
    username: str = Field(..., max_length=100)
    password: str = Field(..., min_length=1)
    db_type: str = Field("postgresql", pattern="^(postgresql|mysql)$")
    connection_string: Optional[str] = None
    sslmode: Optional[str] = Field("require", pattern="^(require|disable|allow|prefer|verify-ca|verify-full)$")

    @field_validator("db_type")
    @classmethod
    def validate_db_type(cls, v):
        return v.lower()


class ConnectionUpdate(BaseModel):
    """Request to update a connection (partial)."""
    name: Optional[str] = Field(None, max_length=100)
    host: Optional[str] = None
    port: Optional[int] = Field(None, ge=1, le=65535)
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    sslmode: Optional[str] = Field(None, pattern="^(require|disable|allow|prefer|verify-ca|verify-full)$")


class ConnectionResponse(BaseModel):
    """Connection response (no secrets)."""
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


class ConnectionDetailResponse(ConnectionResponse):
    """Connection with table list."""
    tables: List[str] = []


class PaginatedConnections(BaseModel):
    page: int
    per_page: int
    total: int
    pages: int
    connections: List[ConnectionResponse]


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str


class TablesResponse(BaseModel):
    tables: List[str]


class TableSchemaResponse(BaseModel):
    table_name: str
    columns: List[dict]