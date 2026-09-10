import re
import os
import time
import threading
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)


class ConnectionPoolManager:
    """
    Manages database connection pools with 20-minute expiry per user per database.
    
    Uses SQLAlchemy's QueuePool for connection pooling with automatic cleanup.
    """
    
    def __init__(self, pool_size: int = 5, max_overflow: int = 10, ttl: int = 1200):
        """
        Initialize connection pool manager.
        
        Args:
            pool_size: Number of connections to keep in pool
            max_overflow: Maximum overflow connections
            ttl: Time-to-live for connections in seconds (default: 20 minutes)
        """
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.ttl = ttl
        # Structure: {user_id: {db_id: (engine, expiry_time, cleanup_timer)}}
        self.pools: Dict[int, Dict[int, tuple]] = {}
        self.lock = threading.Lock()
    
    def get_engine(self, user_id: int, db_id: int, connection_string: str):
        """
        Get or create a connection pool engine for the user/database.
        
        Args:
            user_id: User ID
            db_id: Database connection ID
            connection_string: Database connection string
        
        Returns:
            SQLAlchemy engine
        """
        with self.lock:
            # Check if pool exists and is not expired
            if user_id in self.pools and db_id in self.pools[user_id]:
                engine, expiry_time, timer = self.pools[user_id][db_id]
                if time.time() < expiry_time:
                    # Reset timer
                    timer.cancel()
                    self.pools[user_id][db_id] = (
                        engine,
                        time.time() + self.ttl,
                        self._schedule_cleanup(user_id, db_id)
                    )
                    return engine
                else:
                    # Pool expired, clean it up
                    self._cleanup_pool(user_id, db_id)
            
            # Create new pool
            engine = create_engine(
                connection_string,
                poolclass=QueuePool,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_pre_ping=True,  # Test connections before use
                pool_recycle=3600,  # Recycle connections after 1 hour
                connect_args={
                    "connect_timeout": 5
                }
            )
            
            # Store in pools
            cleanup_timer = self._schedule_cleanup(user_id, db_id)
            self.pools.setdefault(user_id, {})[db_id] = (
                engine,
                time.time() + self.ttl,
                cleanup_timer
            )
            
            logger.info(f"Created connection pool for user {user_id}, db {db_id}")
            return engine
    
    def _schedule_cleanup(self, user_id: int, db_id: int) -> threading.Timer:
        """Schedule cleanup of a connection pool after TTL."""
        timer = threading.Timer(self.ttl, self._cleanup_pool, args=(user_id, db_id))
        timer.daemon = True
        timer.start()
        return timer
    
    def _cleanup_pool(self, user_id: int, db_id: int):
        """Clean up a connection pool."""
        with self.lock:
            if user_id in self.pools and db_id in self.pools[user_id]:
                engine, _, timer = self.pools[user_id].pop(db_id)
                timer.cancel()
                engine.dispose()
                logger.info(f"Cleaned up connection pool for user {user_id}, db {db_id}")
                
                # Clean up empty user entry
                if not self.pools[user_id]:
                    del self.pools[user_id]
    
    def remove_user_pools(self, user_id: int):
        """Remove all pools for a specific user."""
        with self.lock:
            if user_id in self.pools:
                for db_id in list(self.pools[user_id].keys()):
                    self._cleanup_pool(user_id, db_id)
    
    @contextmanager
    def get_connection(self, user_id: int, db_id: int, connection_string: str):
        """
        Get a connection from the pool.
        
        Args:
            user_id: User ID
            db_id: Database connection ID
            connection_string: Database connection string
        
        Returns:
            SQLAlchemy connection
        """

        engine = self.get_engine(user_id, db_id, connection_string)
        conn = engine.connect()
        try:
            yield conn
        except Exception as e:
            logger.error(f"Error using connection for user {user_id}, db {db_id}: {str(e)}")
            raise
        finally:
            conn.close()
    
    def test_connection(self, user_id: int, db_id: int, connection_string: str) -> Dict[str, Any]:
        """
        Test a database connection.
        
        Args:
            user_id: User ID
            db_id: Database connection ID
            connection_string: Database connection string
        
        Returns:
            Dict with success status and message
        """
        try:
            with self.get_connection(user_id, db_id, connection_string) as conn:
                conn.execute(text("SELECT 1"))
            return {"success": True, "message": "Connection successful"}
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return {"success": False, "message": f"Connection failed: {str(e)}"}


# Global connection pool manager instance
connection_pool = ConnectionPoolManager()


# Schema cache with 10-minute TTL
_schema_cache: Dict[int, Dict[int, tuple]] = {}  # {user_id: {db_id: (schema, expiry_time)}}
_schema_cache_lock = threading.Lock()


def get_tables(user_id: int, db_id: int, connection_string: str) -> List[str]:
    """
    Get all tables from the database.
    
    Args:
        user_id: User ID
        db_id: Database connection ID
        connection_string: Database connection string
    
    Returns:
        List of table names
    """
    try:
        # Detect database type and use appropriate query
        if connection_string.startswith(('postgresql://', 'postgres://')):
            query = """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """
        elif connection_string.startswith('mysql://'):
            query = """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = DATABASE()
                ORDER BY table_name
            """
        else:
            # Default to PostgreSQL
            query = """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """
        
        with connection_pool.get_connection(user_id, db_id, connection_string) as conn:
            result = conn.execute(text(query))
            tables = [row[0] for row in result]
        return tables
    except Exception as e:
        logger.error(f"Failed to get tables: {str(e)}")
        raise


def get_table_schema(user_id: int, db_id: int, connection_string: str, table_name: str) -> Dict[str, Any]:
    """
    Get schema information for a specific table.
    
    Args:
        user_id: User ID
        db_id: Database connection ID
        connection_string: Database connection string
        table_name: Table name
    
    Returns:
        Dict with table schema information
    """
    try:
        # Detect database type and use appropriate schema filter
        if connection_string.startswith(('postgresql://', 'postgres://')):
            schema_filter = "table_schema = 'public'"
        elif connection_string.startswith('mysql://'):
            schema_filter = "table_schema = DATABASE()"
        else:
            schema_filter = "table_schema = 'public'"
        
        query = f"""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = :table_name AND {schema_filter}
            ORDER BY ordinal_position
        """
        
        with connection_pool.get_connection(user_id, db_id, connection_string) as conn:
            result = conn.execute(text(query), {"table_name": table_name})
            
            columns = []
            for row in result:
                columns.append({
                    "name": row[0],
                    "type": row[1],
                    "nullable": row[2] == "YES",
                    "default": row[3]
                })
        
        return {"table_name": table_name, "columns": columns}
    except Exception as e:
        logger.error(f"Failed to get table schema: {str(e)}")
        raise


def get_full_schema(user_id: int, db_id: int, connection_string: str) -> Dict[str, Any]:
    """
    Get full database schema with caching.
    
    Args:
        user_id: User ID
        db_id: Database connection ID
        connection_string: Database connection string
    
    Returns:
        Dict with full schema information
    """
    with _schema_cache_lock:
        # Check cache
        if user_id in _schema_cache and db_id in _schema_cache[user_id]:
            schema, expiry_time = _schema_cache[user_id][db_id]
            if time.time() < expiry_time:
                return schema
        
        # Fetch fresh schema
        tables = get_tables(user_id, db_id, connection_string)
        full_schema = {"tables": []}
        
        for table in tables:
            table_schema = get_table_schema(user_id, db_id, connection_string, table)
            full_schema["tables"].append(table_schema)
        
        # Cache for 10 minutes
        _schema_cache.setdefault(user_id, {})[db_id] = (
            full_schema,
            time.time() + 600
        )
        return full_schema


def invalidate_schema_cache(user_id: int, db_id: int = None) -> None:
    """
    Invalidate schema cache for a specific user/database or all databases for a user.
    
    Args:
        user_id: User ID
        db_id: Optional database connection ID. If None, invalidate all for user.
    """
    with _schema_cache_lock:
        if user_id in _schema_cache:
            if db_id is not None:
                _schema_cache[user_id].pop(db_id, None)
                logger.info(f"Invalidated schema cache for user {user_id}, db {db_id}")
            else:
                _schema_cache.pop(user_id, None)
                logger.info(f"Invalidated all schema caches for user {user_id}")


def invalidate_all_schema_caches() -> None:
    """Invalidate all schema caches (use with caution)."""
    with _schema_cache_lock:
        _schema_cache.clear()
        logger.info("Invalidated all schema caches")


def get_schema_cache_stats() -> Dict[str, Any]:
    """Get statistics about the schema cache."""
    with _schema_cache_lock:
        total_entries = sum(len(dbs) for dbs in _schema_cache.values())
        return {
            "users_cached": len(_schema_cache),
            "total_entries": total_entries,
            "cache_ttl_seconds": 600
        }


def format_schema_for_llm(schema: Dict[str, Any], max_chars: int = 4000) -> str:
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
        result = result[:max_chars] + f"\n  ... truncated {len(result)-max_chars} chars (showing {max_chars}/{len(result)})"
    return result


def parse_connection_string(connection_string: str) -> Dict[str, Any]:
    """
    Parse a database connection string into individual components.

    Supports formats:
    - postgresql://user:pass@host:port/database
    - postgres://user:pass@host:port/database
    - mysql://user:pass@host:port/database
    
    Args:
        connection_string: Database connection string
    
    Returns:
        Dictionary with host, port, database, username, password
    """
    try:
        parsed = urlparse(connection_string)
        
        result = {
            "host": parsed.hostname or "",
            "port": parsed.port or 5432,  # Default PostgreSQL port
            "database": parsed.path.lstrip('/') if parsed.path else "",
            "username": parsed.username or "",
            "password": parsed.password or "",
        }
        
        return result
    except Exception as e:
        raise ValueError(f"Invalid connection string format: {str(e)}")


def build_connection_string(
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    db_type: str = "postgresql"
) -> str:
    """
    Build a connection string from individual components.
    
    Args:
        host: Database host
        port: Database port
        database: Database name
        username: Database username
        password: Database password
        db_type: Database type (postgresql, mysql, etc.)
    
    Returns:
        Connection string
    """
    if db_type == "postgresql":
        conn_str = f"{db_type}://{username}:{password}@{host}:{port}/{database}"
        # Add SSL mode for PostgreSQL (required for cloud databases like Render)
        conn_str += "?sslmode=require"
    else:
        conn_str = f"{db_type}://{username}:{password}@{host}:{port}/{database}"
    return conn_str


@contextmanager
def create_connection(db_type: str, connection_string: str, timeout: int = 5):
    """
    Create a database connection with proper security and resource management.
    
    Uses context manager to ensure connections are properly closed.
    Implements timeout to prevent hanging on bad connections.
    
    Args:
        db_type: Database type (postgresql, mysql, etc.)
        connection_string: Database connection string
        timeout: Connection timeout in seconds
    
    Yields:
        Database connection object
    
    Raises:
        ValueError: For unsupported database types
        ConnectionError: For connection failures
    """
    conn = None
    try:
        if db_type == "postgresql":
            import psycopg2
            conn = psycopg2.connect(
                connection_string,
                connect_timeout=timeout,
                sslmode='require'  # Enforce SSL for security
            )
        elif db_type == "mysql":
            import pymysql
            parsed = urlparse(connection_string)
            conn = pymysql.connect(
                host=parsed.hostname,
                port=parsed.port or 3306,
                database=parsed.path.lstrip('/'),
                user=parsed.username,
                password=parsed.password,
                connect_timeout=timeout,
                ssl={'ssl_mode': 'REQUIRED'}  # Enforce SSL
            )
        else:
            raise ValueError(f"Unsupported database type: {db_type}")
        
        # Test the connection is actually working
        conn.cursor().execute("SELECT 1")
        
        logger.info(f"Successfully connected to {db_type} database")
        yield conn
        
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        if conn:
            conn.close()
        raise ConnectionError(f"Failed to connect to database: {str(e)}")
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed")


def test_connection_safe(db_type: str, connection_string: str) -> Dict[str, Any]:
    """
    Test a database connection safely without keeping it open.
    
    Args:
        db_type: Database type
        connection_string: Connection string
    
    Returns:
        Dict with success status and message
    """
    try:
        with create_connection(db_type, connection_string) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()
            return {
                "success": True,
                "message": "Connection successful",
                "version": version[0] if version else "Unknown"
            }
    except ConnectionError as e:
        return {"success": False, "message": str(e)}
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}