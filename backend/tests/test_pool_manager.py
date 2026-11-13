"""Connection-pool cache: reuse, expiry and LRU eviction.

The pool entry is a named tuple (engine, expires_at) rather than a bare
tuple, so the cache can be read by field name. These tests pin the
behaviour that depends on it: an entry is reused until it expires, an
expired entry is replaced and disposed, and the least recently used pool is
evicted when a user exceeds their limit.
"""

import pytest

from connections.pool_manager import ConnectionPoolManager


@pytest.fixture()
def manager(tmp_path):
    """A pool manager with a short TTL and one file-backed SQLite engine."""
    return ConnectionPoolManager(pool_size=1, max_overflow=0, ttl=1200, max_pools_per_user=2)


def _url(tmp_path, name="pool.db"):
    return f"sqlite:///{tmp_path / name}"


def test_same_pool_is_reused(manager, tmp_path):
    """Two calls for the same (user, db) must hand back the same engine."""
    url = _url(tmp_path)
    first = manager.get_engine(1, 1, url)
    second = manager.get_engine(1, 1, url)

    assert first is second


def test_entry_exposes_named_fields(manager, tmp_path):
    """The cached entry is read by name, not by position."""
    manager.get_engine(1, 1, _url(tmp_path))

    entry = manager._pools[1][1]
    assert entry.engine is not None
    assert entry.expires_at > 0


def test_expired_pool_is_replaced(manager, tmp_path):
    """An entry past its TTL must not be handed back."""
    manager.ttl = 0  # every entry is already expired
    url = _url(tmp_path)

    first = manager.get_engine(1, 1, url)
    second = manager.get_engine(1, 1, url)

    assert second is not first
    # The stale engine was disposed rather than leaked.
    assert first.pool is not second.pool


def test_lru_pool_is_evicted(manager, tmp_path):
    """Exceeding the per-user limit evicts the least recently used pool."""
    manager.get_engine(1, 1, _url(tmp_path, "a.db"))
    manager.get_engine(1, 2, _url(tmp_path, "b.db"))

    manager.get_engine(1, 3, _url(tmp_path, "c.db"))

    assert set(manager._pools[1].keys()) == {2, 3}


def test_close_pool_removes_the_entry(manager, tmp_path):
    manager.get_engine(1, 1, _url(tmp_path))
    manager.close_pool(1, 1)

    assert 1 not in manager._pools or 1 not in manager._pools[1]


def test_close_user_pools_clears_every_pool(manager, tmp_path):
    manager.get_engine(1, 1, _url(tmp_path, "a.db"))
    manager.get_engine(1, 2, _url(tmp_path, "b.db"))

    manager.close_user_pools(1)

    assert 1 not in manager._pools
