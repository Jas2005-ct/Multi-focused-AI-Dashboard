from pydantic import BaseModel, Field


class DBConnectionRequest(BaseModel):
    host: str = Field("localhost", description="Database host")
    port: int = Field(5432, description="Database port")
    database: str = Field(None, description="Database name")
    username: str = Field(None, description="Database username")
    password: str = Field(None, description="Database password")
    connection_string: str = Field(None, description="Database connection string")


class QueryResponse(BaseModel):
    output_query: str = Field(..., description="Optimized SQL query")


class PromptRequest(BaseModel):
    sentence: str = Field(..., description="Natural language sentence to optimize")
    db_id: int = Field(None, description="Database connection ID for schema context")


class SelectConnectionRequest(BaseModel):
    db_id: int = Field(..., description="Database connection ID to select")


class DeleteConnectionRequest(BaseModel):
    db_id: int = Field(..., description="Database connection ID to delete")

