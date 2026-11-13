"""Connection pool manager with LRU + TTL expiry (Phase 3).

Fixes Timer leak by using lazy expiry + explicit close instead of
threading.Timer per pool.
"""

import logging
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from typing import Dict, NamedTuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

from connections.payloads import PoolStats, TestConnectionResult

logger = logging.getLogger(__name__)


class _PoolEntry(NamedTuple):
    """A pooled engine and the timestamp at which it expires."""

    engine: Engine
    expires_at: float


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

        # Structure: {user_id: OrderedDict[db_id, _PoolEntry]}
        # OrderedDict maintains LRU order (move_to_end on access)
        self._pools: Dict[int, OrderedDict[int, _PoolEntry]] = {}
        self._lock = threading.RLock()

    def _make_engine(self, connection_string: str) -> Engine:
        """Create a new SQLAlchemy engine with appropriate dialect options."""
        db_url = connection_string

        # Ensure proper dialect prefix for SQLAlchemy
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        elif db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif db_url.startswith("mysql://"):
            db_url = db_url.replace("mysql://", "mysql+pymysql://", 1)

        # connect_args are dialect-specific: pysqlite rejects psycopg2/pymysql
        # params with TypeError, so scope them per engine family.
        if db_url.startswith("postgresql+psycopg2://"):
            connect_args = {"connect_timeout": 5}
        elif db_url.startswith("mysql+pymysql://"):
            connect_args = {"connect_timeout": 5, "ssl": {"ssl_mode": "REQUIRED"}}
        else:
            connect_args = {}

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
            lru_db_id, entry = user_pools.popitem(last=False)
            logger.info(f"Evicted LRU pool for user {user_id}, db {lru_db_id}")
            return entry.engine
        return None

    def get_engine(self, user_id: int, db_id: int, connection_string: str) -> Engine:
        """
        Get or create a connection pool engine for the user/database.

        On access: moves pool to MRU position, refreshes expiry.
        On miss: builds the engine *outside* the global lock (so concurrent
        users are never blocked by another user's engine instantiation),
        then installs it under a re-acquired lock with a double-check so two
        threads missing simultaneously do not create duplicate engines.
        Expired/evicted engines are always disposed outside the lock, since
        release/Dialect connect can block and deadlock bystanders.
        """
        to_dispose: list[Engine] = []

        # Pass 1 — lock covers only dictionary bookkeeping.
        with self._lock:
            user_pools = self._pools.setdefault(user_id, OrderedDict())

            if db_id in user_pools:
                entry = user_pools[db_id]
                if time.time() < entry.expires_at:
                    # Hit: refresh expiry, move to MRU
                    user_pools[db_id] = _PoolEntry(
                        engine=entry.engine, expires_at=time.time() + self.ttl
                    )
                    user_pools.move_to_end(db_id)
                    return entry.engine
                # Expired: remove now; disposal happens outside the lock
                to_dispose.append(user_pools.pop(db_id).engine)
                logger.info(f"Expired pool removed for user {user_id}, db {db_id}")

            evicted = self._evict_lru_if_needed(user_id)
            if evicted:
                to_dispose.append(evicted)

        # Pass 2 — expensive engine construction with no lock held.
        engine = self._make_engine(connection_string)

        # Pass 3 — install under the lock with a double-check.
        with self._lock:
            user_pools = self._pools.setdefault(user_id, OrderedDict())
            existing = user_pools.get(db_id)
            if existing is not None and time.time() < existing.expires_at:
                # Another thread installed a fresh pool while we built ours:
                # keep theirs, discard ours.
                to_dispose.append(engine)
                engine, expiry_time = existing.engine, existing.expires_at
            else:
                if existing is not None:
                    to_dispose.append(existing.engine)
                expiry_time = time.time() + self.ttl
                user_pools[db_id] = _PoolEntry(engine=engine, expires_at=expiry_time)
            user_pools.move_to_end(db_id)

        for stale in to_dispose:
            try:
                stale.dispose()
            except Exception as e:
                logger.warning(f"Error disposing engine: {e}")

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

    def test_connection(
        self, user_id: int, db_id: int, connection_string: str
    ) -> TestConnectionResult:
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
                entry = self._pools[user_id].pop(db_id)
                entry.engine.dispose()
                logger.info(f"Explicitly closed pool for user {user_id}, db {db_id}")

    # Backward-compatibility alias for legacy code
    _cleanup_pool = close_pool

    def close_user_pools(self, user_id: int) -> None:
        """Close all pools for a user."""
        with self._lock:
            if user_id in self._pools:
                for entry in self._pools[user_id].values():
                    entry.engine.dispose()
                self._pools.pop(user_id)
                logger.info(f"Closed all pools for user {user_id}")

    def get_stats(self) -> PoolStats:
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
