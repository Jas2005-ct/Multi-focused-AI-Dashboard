"""Connection service layer (Phase 3).

Business logic for DB connection CRUD, validation, and schema introspection.
"""

from typing import List, Optional
from urllib.parse import urlparse

from sqlalchemy import text

from config import get_settings
from connections.model import DBConnection
from connections.crypto import crypto
from connections.pool_manager import connection_pool
from auths.models import User, db


def parse_connection_string(connection_string: str) -> dict:
    """Parse a database connection string into individual components."""
    try:
        parsed = urlparse(connection_string)
        return {
            "host": parsed.hostname or "",
            "port": parsed.port or 5432,
            "database": parsed.path.lstrip("/") if parsed.path else "",
            "username": parsed.username or "",
            "password": parsed.password or "",
        }
    except Exception as e:
        raise ValueError(f"Invalid connection string format: {e}")


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
        conn_str = build_connection_string(host, port, database, username, password, db_type)

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
        # Update last_used and return
        existing.last_used = __import__("datetime").datetime.utcnow()
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
        sslmode="require" if db_type == "postgresql" else None,
    )
    set_encrypted_fields(new_conn, password, conn_str)

    db.session.add(new_conn)
    db.session.commit()
    return new_conn


def list_connections(user_id: int, page: int = 1, per_page: int = 20):
    """Paginated list of connections for a user."""
    pagination = DBConnection.query.filter_by(user_id=user_id).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return {
        "page": page,
        "per_page": per_page,
        "total": pagination.total,
        "pages": pagination.pages,
        "connections": [
            {
                "id": c.id,
                "name": c.name,
                "host": c.host,
                "port": c.port,
                "database": c.database,
                "username": c.username,
                "db_type": c.db_type,
                "sslmode": c.sslmode,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "last_used": c.last_used.isoformat() if c.last_used else None,
            }
            for c in pagination.items
        ],
    }


def get_connection(user_id: int, db_id: int) -> Optional[DBConnection]:
    """Get a specific connection by ID, verifying ownership."""
    conn = DBConnection.query.get(db_id)
    if not conn or conn.user_id != user_id:
        return None
    return conn


def get_connection_with_tables(user_id: int, db_id: int) -> Optional[dict]:
    """Get connection details with table list."""
    conn = get_connection(user_id, db_id)
    if not conn:
        return None

    conn_str = get_decrypted_connection_string(conn)
    test = connection_pool.test_connection(user_id, db_id, conn_str)
    if not test["success"]:
        raise ConnectionError(test["message"])

    tables = get_tables(user_id, db_id, conn_str)
    return {
        "id": conn.id,
        "name": conn.name,
        "host": conn.host,
        "port": conn.port,
        "database": conn.database,
        "username": conn.username,
        "db_type": conn.db_type,
        "sslmode": conn.sslmode,
        "created_at": conn.created_at.isoformat() if conn.created_at else None,
        "last_used": conn.last_used.isoformat() if conn.last_used else None,
        "tables": tables,
    }


def test_connection(user_id: int, db_id: int) -> dict:
    """Test a saved connection."""
    conn = get_connection(user_id, db_id)
    if not conn:
        return {"success": False, "message": "Connection not found"}

    conn_str = get_decrypted_connection_string(conn)
    result = connection_pool.test_connection(user_id, db_id, conn_str)
    if result["success"]:
        conn.last_used = __import__("datetime").datetime.utcnow()
        db.session.commit()
    return result


def delete_connection(user_id: int, db_id: int) -> bool:
    """Delete a connection and clean up its pool."""
    conn = get_connection(user_id, db_id)
    if not conn:
        return False

    # Clean up pool
    connection_pool.close_pool(user_id, db_id)

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
        return [row[0] for row in result]


def get_table_schema(user_id: int, db_id: int, connection_string: str, table_name: str) -> dict:
    """Get schema for a specific table."""
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
        columns = [
            {"name": r[0], "type": r[1], "nullable": r[2] == "YES", "default": r[3]}
            for r in result
        ]
    return {"table_name": table_name, "columns": columns}