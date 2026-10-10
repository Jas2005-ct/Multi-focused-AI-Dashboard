import re
from pydantic import BaseModel, Field, field_validator


class DBConnectionRequest(BaseModel):
    host: str = Field("localhost", description="Database host")
    port: int = Field(5432, description="Database port")
    database: str = Field(None, description="Database name")
    username: str = Field(None, description="Database username")
    password: str = Field(None, description="Database password")
    db_type: str = Field("postgresql", description="Database type (postgresql, mysql)")
    connection_string: str = Field(None, description="Database connection string")
    
    @field_validator('port')
    @classmethod
    def validate_port(cls, v):
        if v is not None and not (1 <= v <= 65535):
            raise ValueError('Port must be between 1 and 65535')
        return v
    
    @field_validator('db_type')
    @classmethod
    def validate_db_type(cls, v):
        allowed = ['postgresql', 'postgres', 'mysql']
        if v and v.lower() not in allowed:
            raise ValueError(f'db_type must be one of: {allowed}')
        return v.lower() if v else v


class QueryResponse(BaseModel):
    output_query: str = Field(..., description="Optimized SQL query")


class MetadataAnswer(BaseModel):
    type: str = Field("answer", description="Discriminator for metadata answer")
    answer: str = Field(..., description="Natural language answer about DB structure")
    tables: list[str] | None = Field(default=None, description="List of table names when applicable")


class QueryAnswer(BaseModel):
    type: str = Field("query", description="Discriminator for generated query")
    output_query: str = Field(..., description="Optimized SQL query")


class PromptRequest(BaseModel):
    sentence: str = Field(..., description="Natural language sentence to optimize", max_length=5000)
    db_id: int = Field(None, description="Database connection ID for schema context")
    
    @field_validator('sentence')
    @classmethod
    def validate_sentence_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Sentence cannot be empty')
        return v.strip()


class SelectConnectionRequest(BaseModel):
    db_id: int = Field(None, description="Database connection ID to select")
    page: int = Field(1, ge=1, description="Page number for listing")
    per_page: int = Field(20, ge=1, le=100, description="Items per page")


class DeleteConnectionRequest(BaseModel):
    db_id: int = Field(..., description="Database connection ID to delete")


class AIQueryRequest(BaseModel):
    """Request for AI-powered SQL generation or data answers."""
    query: str = Field(..., description="Natural language query", max_length=5000)
    connection_id: int = Field(..., description="Database connection ID", alias="connection_id")
    mode: str = Field("auto", pattern="^(auto|sql|answer)$", description="Mode: auto (agent), sql (direct LCEL), answer (data only)")

    @field_validator('query')
    @classmethod
    def validate_query_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Query cannot be empty')
        return v.strip()


class AIQueryResponse(BaseModel):
    """Response from AI query endpoint."""
    success: bool = True
    type: str = Field(..., description="Response type: query or answer")
    sql: str | None = Field(None, description="Generated SQL query (when type=query)")
    answer: str | None = Field(None, description="Natural language answer (when type=answer)")
    rows: list[dict] | None = Field(None, description="Data rows (when type=answer)")
    count: int | None = Field(None, description="Row count (when type=answer)")
    tables: list[str] | None = Field(None, description="Table names referenced")
    toolCalls: list[dict] | None = Field(None, description="Tool calls made by agent")
    metadata: dict | None = Field(None, description="Additional metadata")
    usage: dict | None = Field(None, description="LLM usage statistics")

