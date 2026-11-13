"""Connection service layer (Phase 3).

Business logic for DB connection CRUD, validation, and schema introspection.
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, cast
from urllib.parse import unquote, urlparse

from sqlalchemy import text
from sqlalchemy.engine import Result

from auths.models import db
from common.table_policy import is_table_ignored, visible_tables
from connections.crypto import crypto
from connections.model import DBConnection
from connections.payloads import (
    ColumnSchema,
    ConnectionDetail,
    ConnectionPage,
    ConnectionSummary,
    FullSchema,
    ParsedConnection,
    TableSchema,
    TestConnectionResult,
)
from connections.pool_manager import connection_pool

_SCHEMA_CACHE: Dict[Tuple[int, int], Tuple[float, FullSchema]] = {}
_SCHEMA_CACHE_TTL = 300  # 5 minutes

# The display name of the demo connection.
DEMO_CONNECTION_NAME = "Demo Database (E-commerce)"


def _named_rows(result: Result) -> List[Dict[str, Any]]:
    """Rows of a query as dicts keyed by lower-cased column label.

    Reading a row by column *name* instead of by position means the SELECT
    and the reader no longer have to be kept in sync by hand: reordering the
    columns, or adding one in the middle, can no longer silently put the
    wrong value in the wrong field.

    The label case is normalised because it is not the same on every
    supported database - PostgreSQL reports ``information_schema`` labels in
    lower case and MySQL in upper case - and the driver passes those labels
    through unchanged.
    """
    return [{key.lower(): value for key, value in row.items()} for row in result.mappings()]


def get_cached_schema(user_id: int, db_id: int) -> Optional[FullSchema]:
    entry = _SCHEMA_CACHE.get((user_id, db_id))
    if not entry:
        return None
    expires_at, data = entry
    if time.time() > expires_at:
        _SCHEMA_CACHE.pop((user_id, db_id), None)
        return None
    return data


def set_cached_schema(user_id: int, db_id: int, data: FullSchema) -> None:
    _SCHEMA_CACHE[(user_id, db_id)] = (time.time() + _SCHEMA_CACHE_TTL, data)


def invalidate_schema_cache(user_id: int, db_id: int) -> None:
    _SCHEMA_CACHE.pop((user_id, db_id), None)


def parse_connection_string(connection_string: str) -> ParsedConnection:
    """Parse a database connection string into individual components."""
    try:
        parsed = urlparse(connection_string)
        return {
            "host": parsed.hostname or "",
            "port": parsed.port or 5432,
            "database": parsed.path.lstrip("/") if parsed.path else "",
            # Credentials are percent-encoded in a URL ("p%40ss" is "p@ss").
            # Unquoting them keeps the stored username and password equal
            # to the ones the operator meant, and keeps the lookup of an
            # existing connection consistent with the stored row.
            "username": unquote(parsed.username or ""),
            "password": unquote(parsed.password or ""),
        }
    except Exception as e:
        raise ValueError(f"Invalid connection string format: {e}") from e


def build_connection_string(
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    db_type: str = "postgresql",
    sslmode: str = "require",
) -> str:
    """Build a connection string from individual components."""
    if db_type == "postgresql":
        conn_str = f"postgresql://{username}:{password}@{host}:{port}/{database}"
        if sslmode:
            conn_str += f"?sslmode={sslmode}"
    else:
        conn_str = f"mysql://{username}:{password}@{host}:{port}/{database}"
    return conn_str


def get_decrypted_password(conn: DBConnection) -> str:
    return crypto.decrypt(conn.password) if conn.password else ""


def get_decrypted_connection_string(conn: DBConnection) -> str:
    return crypto.decrypt(conn.connection_string) if conn.connection_string else ""


def set_encrypted_fields(conn: DBConnection, password: str, connection_string: str):
    conn.password = crypto.encrypt(password) if password else None
    conn.connection_string = crypto.encrypt(connection_string) if connection_string else None


def save_connection(
    user_id: int,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    db_type: str = "postgresql",
    connection_string: str = None,
    name: str = None,
    sslmode: str = "require",
) -> DBConnection:
    """Save a new connection or return existing one."""
    if connection_string:
        parsed = parse_connection_string(connection_string)
        host = parsed["host"] or host
        port = port or parsed["port"] or 5432
        database = database or parsed["database"]
        username = username or parsed["username"]
        password = password or parsed["password"]
        conn_str = connection_string
        # Detect db_type from connection string
        if connection_string.startswith(("postgresql://", "postgres://")):
            db_type = "postgresql"
        elif connection_string.startswith("mysql://"):
            db_type = "mysql"
    else:
        # Validate required fields
        if not all([host, port, database, username, password]):
            raise ValueError("All database fields required when connection_string not provided")
        conn_str = build_connection_string(
            host, port, database, username, password, db_type, sslmode=sslmode
        )

    # Check for existing
    existing = DBConnection.query.filter_by(
        user_id=user_id,
        host=host,
        port=port,
        database=database,
        username=username,
        db_type=db_type,
    ).first()

    if existing:
        # Update last_used and return (naive-UTC, matching stored column).
        existing.last_used = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
        return existing

    # Create new
    new_conn = DBConnection(
        user_id=user_id,
        name=name,
        host=host,
        port=port,
        database=database,
        username=username,
        db_type=db_type,
        sslmode=sslmode if db_type == "postgresql" else None,
    )
    set_encrypted_fields(new_conn, password, conn_str)

    db.session.add(new_conn)
    db.session.commit()
    return new_conn


class DemoDatabaseNotConfigured(RuntimeError):
    """Raised when no demo database is configured for this deployment."""


def save_demo_connection(user_id: int) -> Tuple[DBConnection, bool]:
    """Attach the shared demo database to a user.

    The demo database is a separate database that holds synthetic data
    only, so a visitor can try the assistant without bringing their own.
    The URL comes from ``DEMO_DB_URL`` - a deployment setting, never a
    hardcoded credential.

    Returns the connection and whether it was created just now. Calling it
    twice for the same user reuses the existing row, so the button can be
    pressed as often as the user likes.
    """
    from config import get_settings

    url = (get_settings().DEMO_DB_URL or "").strip()
    if not url:
        raise DemoDatabaseNotConfigured("No demo database is configured on this deployment.")

    parsed = parse_connection_string(url)
    if not parsed["host"] or not parsed["database"]:
        raise ValueError("The demo database URL is incomplete")

    db_type = "mysql" if url.startswith("mysql") else "postgresql"

    existing = DBConnection.query.filter_by(
        user_id=user_id,
        host=parsed["host"],
        port=parsed["port"],
        database=parsed["database"],
        username=parsed["username"],
        db_type=db_type,
    ).first()
    if existing:
        # Touch it so the connection shows up as recently used.
        existing.last_used = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
        return existing, False

    conn = save_connection(
        user_id=user_id,
        host=parsed["host"],
        port=parsed["port"],
        database=parsed["database"],
        username=parsed["username"],
        password=parsed["password"],
        db_type=db_type,
        # The configured URL is stored verbatim, so it reaches the driver
        # exactly as the operator wrote it.
        connection_string=url,
        name=DEMO_CONNECTION_NAME,
    )
    return conn, True


def _to_summary(conn: DBConnection) -> ConnectionSummary:
    """Read an ORM row into a plain dict, without secrets.

    The model's attributes are plain Python values at runtime, but they are
    declared with ``db.Column``, which a type checker reads as ``Column[str]``
    rather than ``str``. The casts bridge that gap in one place, so both
    callers of this helper stay clean.
    """
    created_at = cast(Optional[datetime], conn.created_at)
    last_used = cast(Optional[datetime], conn.last_used)
    return {
        "id": cast(int, conn.id),
        "name": cast(Optional[str], conn.name),
        "host": cast(str, conn.host),
        "port": cast(int, conn.port),
        "database": cast(str, conn.database),
        "username": cast(str, conn.username),
        "db_type": cast(str, conn.db_type),
        "sslmode": cast(Optional[str], conn.sslmode),
        "created_at": created_at.isoformat() if created_at else None,
        "last_used": last_used.isoformat() if last_used else None,
    }


def list_connections(user_id: int, page: int = 1, per_page: int = 20) -> ConnectionPage:
    """Paginated list of connections for a user."""
    pagination = DBConnection.query.filter_by(user_id=user_id).paginate(
        page=page, per_page=per_page, error_out=False
    )
    connections: List[ConnectionSummary] = [_to_summary(c) for c in pagination.items]
    return {
        "page": page,
        "per_page": per_page,
        "total": pagination.total,
        "pages": pagination.pages,
        "connections": connections,
    }


def get_connection(user_id: int, db_id: int) -> Optional[DBConnection]:
    """Get a specific connection by ID, verifying ownership."""
    conn = db.session.get(DBConnection, db_id)
    if not conn or conn.user_id != user_id:
        return None
    return conn


def get_connection_with_tables(user_id: int, db_id: int) -> Optional[ConnectionDetail]:
    """Get connection details with table list."""
    conn = get_connection(user_id, db_id)
    if not conn:
        return None

    conn_str = get_decrypted_connection_string(conn)
    test = connection_pool.test_connection(user_id, db_id, conn_str)
    if not test["success"]:
        raise ConnectionError(test["message"])

    tables = get_tables(user_id, db_id, conn_str)
    detail: ConnectionDetail = {**_to_summary(conn), "tables": tables}
    return detail


def test_connection(user_id: int, db_id: int) -> TestConnectionResult:
    """Test a saved connection."""
    conn = get_connection(user_id, db_id)
    if not conn:
        return {"success": False, "message": "Connection not found"}

    conn_str = get_decrypted_connection_string(conn)
    result = connection_pool.test_connection(user_id, db_id, conn_str)
    if result["success"]:
        # Stored naive-UTC, matching the convention elsewhere in the codebase.
        conn.last_used = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
    return result


def delete_connection(user_id: int, db_id: int) -> bool:
    """Delete a connection and clean up its pool."""
    conn = get_connection(user_id, db_id)
    if not conn:
        return False

    # Clean up pool and cache
    connection_pool.close_pool(user_id, db_id)
    invalidate_schema_cache(user_id, db_id)

    db.session.delete(conn)
    db.session.commit()
    return True


def get_tables(user_id: int, db_id: int, connection_string: str) -> List[str]:
    """Get all tables from the database."""
    with connection_pool.get_connection(user_id, db_id, connection_string) as conn:
        if connection_string.startswith(("postgresql://", "postgres://")):
            query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """)
        elif connection_string.startswith("mysql://"):
            query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = DATABASE()
                ORDER BY table_name
            """)
        else:
            query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """)
        result = conn.execute(query)
        # Single-column SELECT: scalars() returns the table names directly.
        # Tables hidden by policy are dropped here, so every consumer of the
        # listing (the UI, the agent, the LLM schema context) sees the same
        # set of tables.
        return visible_tables(list(result.scalars()))


def get_table_schema(
    user_id: int, db_id: int, connection_string: str, table_name: str
) -> TableSchema:
    """Get schema for a specific table."""
    if is_table_ignored(table_name):
        raise ValueError(f"Table '{table_name}' is not accessible")

    with connection_pool.get_connection(user_id, db_id, connection_string) as conn:
        if connection_string.startswith(("postgresql://", "postgres://")):
            schema_filter = "table_schema = 'public'"
        elif connection_string.startswith("mysql://"):
            schema_filter = "table_schema = DATABASE()"
        else:
            schema_filter = "table_schema = 'public'"

        query = text(f"""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = :table_name AND {schema_filter}
            ORDER BY ordinal_position
        """)
        result = conn.execute(query, {"table_name": table_name})
        columns: List[ColumnSchema] = [
            {
                "name": row["column_name"],
                "type": row["data_type"],
                "nullable": row["is_nullable"] == "YES",
                "default": row["column_default"],
            }
            for row in _named_rows(result)
        ]
    return {"table_name": table_name, "columns": columns}


def get_full_schema(user_id: int, db_id: int, connection_string: str) -> FullSchema:
    """Get full database schema with all tables and columns in a single batch query."""
    cached = get_cached_schema(user_id, db_id)
    if cached is not None:
        return cached

    with connection_pool.get_connection(user_id, db_id, connection_string) as conn:
        if connection_string.startswith(("postgresql://", "postgres://")):
            schema_filter = "table_schema = 'public'"
        elif connection_string.startswith("mysql://"):
            schema_filter = "table_schema = DATABASE()"
        else:
            schema_filter = "table_schema = 'public'"

        query = text(f"""
            SELECT table_name, column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE {schema_filter}
            ORDER BY table_name, ordinal_position
        """)
        result = conn.execute(query)
        tables_dict: Dict[str, List[ColumnSchema]] = {}
        for row in _named_rows(result):
            t_name = row["table_name"]
            # Hidden tables are dropped before the schema is cached, so the
            # cache never holds them and the LLM never sees them in its
            # schema context.
            if is_table_ignored(t_name):
                continue
            if t_name not in tables_dict:
                tables_dict[t_name] = []
            tables_dict[t_name].append(
                {
                    "name": row["column_name"],
                    "type": row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                    "default": row["column_default"],
                }
            )

    full_schema: FullSchema = {
        "tables": [{"table_name": t, "columns": cols} for t, cols in tables_dict.items()]
    }
    set_cached_schema(user_id, db_id, full_schema)
    return full_schema


def format_schema_for_llm(schema: FullSchema, max_chars: int = 4000) -> str:
    """
    Format database schema for inclusion in LLM prompt, capped to max_chars.

    Args:
        schema: Schema dictionary
        max_chars: Hard cap to protect token budget (default 4000 chars ~1000 tokens)

    Returns:
        Formatted string for LLM, truncated with notice if needed
    """
    if not schema or "tables" not in schema:
        return ""

    lines = ["Database Schema:"]
    for table in schema["tables"]:
        table_name = table["table_name"]
        columns = ", ".join([f"{col['name']}({col['type']})" for col in table["columns"]])
        lines.append(f"  - {table_name}: {columns}")
    result = "\n".join(lines)
    if len(result) > max_chars:
        result = (
            result[:max_chars]
            + f"\n  ... truncated {len(result)-max_chars} chars (showing {max_chars}/{len(result)})"
        )
    return result
