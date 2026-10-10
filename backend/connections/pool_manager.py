"""Connection pool manager with LRU + TTL expiry (Phase 3).

Fixes Timer leak by using lazy expiry + explicit close instead of
threading.Timer per pool.
"""

import time
import threading
import logging
from typing import Dict, Tuple
from contextlib import contextmanager
from collections import OrderedDict

from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from sqlalchemy.engine import Engine

from config import get_settings

logger = logging.getLogger(__name__)


class ConnectionPoolManager:
    """
    Manages database connection pools with LRU + TTL expiry.

    Uses SQLAlchemy's QueuePool. Pools expire after TTL and are
    cleaned up on next access (lazy) or explicit close.
    """

    def __init__(
        self,
        pool_size: int = 5,
        max_overflow: int = 10,
        ttl: int = 1200,
        max_pools_per_user: int = 10,
    ):
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.ttl = ttl
        self.max_pools_per_user = max_pools_per_user

        # Structure: {user_id: OrderedDict[db_id, (engine, expiry_time)]}
        # OrderedDict maintains LRU order (move_to_end on access)
        self._pools: Dict[int, OrderedDict[int, Tuple[Engine, float]]] = {}
        self._lock = threading.RLock()

    def _make_engine(self, connection_string: str) -> Engine:
        """Create a new SQLAlchemy engine with appropriate dialect options."""
        settings = get_settings()
        db_url = connection_string

        # Ensure proper dialect prefix for SQLAlchemy
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        elif db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif db_url.startswith("mysql://"):
            db_url = db_url.replace("mysql://", "mysql+pymysql://", 1)

        connect_args = {"connect_timeout": 5}

        # PostgreSQL-specific SSL handling
        if db_url.startswith("postgresql+psycopg2://"):
            # sslmode is already in query string from build_connection_string
            pass
        elif db_url.startswith("mysql+pymysql://"):
            connect_args["ssl"] = {"ssl_mode": "REQUIRED"}

        return create_engine(
            db_url,
            poolclass=QueuePool,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args=connect_args,
        )

    def _evict_lru_if_needed(self, user_id: int):
        """Evict LRU pool if user exceeds max_pools_per_user."""
        user_pools = self._pools.get(user_id)
        if user_pools and len(user_pools) >= self.max_pools_per_user:
            # Evict oldest (first item in OrderedDict)
            lru_db_id, (engine, _) = user_pools.popitem(last=False)
            engine.dispose()
            logger.info(f"Evicted LRU pool for user {user_id}, db {lru_db_id}")

    def get_engine(self, user_id: int, db_id: int, connection_string: str) -> Engine:
        """
        Get or create a connection pool engine for the user/database.

        On access: moves pool to MRU position, refreshes expiry.
        On miss: creates new engine, evicts LRU if needed.
        """
        with self._lock:
            # Get or create user's pool dict
            user_pools = self._pools.setdefault(user_id, OrderedDict())

            # Check if pool exists and is not expired
            if db_id in user_pools:
                engine, expiry_time = user_pools[db_id]
                if time.time() < expiry_time:
                    # Hit: refresh expiry, move to MRU
                    user_pools[db_id] = (engine, time.time() + self.ttl)
                    user_pools.move_to_end(db_id)
                    return engine
                else:
                    # Expired: dispose and remove
                    engine.dispose()
                    user_pools.pop(db_id)
                    logger.info(f"Expired pool removed for user {user_id}, db {db_id}")

            # Miss or expired: create new pool
            self._evict_lru_if_needed(user_id)
            engine = self._make_engine(connection_string)
            user_pools[db_id] = (engine, time.time() + self.ttl)
            logger.info(f"Created connection pool for user {user_id}, db {db_id}")
            return engine

    @contextmanager
    def get_connection(self, user_id: int, db_id: int, connection_string: str):
        """Get a connection from the pool."""
        engine = self.get_engine(user_id, db_id, connection_string)
        conn = engine.connect()
        try:
            yield conn
        except Exception as e:
            logger.error(f"Error using connection for user {user_id}, db {db_id}: {e}")
            raise
        finally:
            conn.close()

    def test_connection(self, user_id: int, db_id: int, connection_string: str) -> dict:
        """Test a database connection."""
        try:
            with self.get_connection(user_id, db_id, connection_string) as conn:
                conn.execute(text("SELECT 1"))
            return {"success": True, "message": "Connection successful"}
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return {"success": False, "message": f"Connection failed: {e}"}

    def close_pool(self, user_id: int, db_id: int) -> None:
        """Explicitly close and remove a specific pool."""
        with self._lock:
            if user_id in self._pools and db_id in self._pools[user_id]:
                engine, _ = self._pools[user_id].pop(db_id)
                engine.dispose()
                logger.info(f"Explicitly closed pool for user {user_id}, db {db_id}")

    def close_user_pools(self, user_id: int) -> None:
        """Close all pools for a user."""
        with self._lock:
            if user_id in self._pools:
                for db_id, (engine, _) in self._pools[user_id].items():
                    engine.dispose()
                self._pools.pop(user_id)
                logger.info(f"Closed all pools for user {user_id}")

    def get_stats(self) -> dict:
        """Get pool statistics for monitoring."""
        with self._lock:
            total = sum(len(p) for p in self._pools.values())
            return {
                "users_with_pools": len(self._pools),
                "total_pools": total,
                "pool_ttl_seconds": self.ttl,
                "max_pools_per_user": self.max_pools_per_user,
            }


# Global instance
connection_pool = ConnectionPoolManager()