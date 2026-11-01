"""Schema introspection: exactly ONE information_schema roundtrip + TTL cache.

Regression for the N+1 regime: get_full_schema used to run 1 query for
tables plus one per-table column query — N+1 roundtrips — and repeated
the whole sweep on every prompt. The current implementation issues a
single batched SELECT over information_schema.columns and memoizes by
(user_id, db_id), invalidated on delete.

Strategy: attach a fake `information_schema.columns` (SQLite supports
attached schemas) and count the SQL statements that reference it, so the
assertion pins the exact "single batched query" property.
"""

import pytest
from sqlalchemy import Engine, event

_FAKE_SCHEMA_ROWS = [
    # (table_name, column_name, data_type, is_nullable, column_default, ordinal_position)
    ("alpha", "id", "INTEGER", "NO", None, 1),
    ("alpha", "name", "TEXT", "YES", None, 2),
    ("beta", "id", "INTEGER", "NO", None, 1),
    ("beta", "kind", "TEXT", "YES", "'row'", 2),
]


@pytest.fixture()
def _fresh_settings():
    """Defuse the LRU settings cache around every test in this module."""
    from config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def batched_engine(app_client, _fresh_settings, tmp_path) -> tuple[Engine, list[str]]:
    """Pooled engine for (user 1, db 1) + a capture list of schema statements."""
    from connections import service as svc  # deferred: see conftest note

    schema_calls: list[str] = []

    def _on_connect(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        # information_schema is not a native SQLite schema: attach an
        # in-memory database under that name, then fill `columns`.
        cursor.execute("ATTACH ':memory:' AS information_schema")
        cursor.execute(
            "CREATE TABLE information_schema.columns ("
            "table_schema TEXT, table_name TEXT, column_name TEXT, data_type TEXT,"
            "is_nullable TEXT, column_default, ordinal_position INTEGER)"
        )
        for row in _FAKE_SCHEMA_ROWS:
            cursor.execute(
                "INSERT INTO information_schema.columns VALUES ('public', ?, ?, ?, ?, ?, ?)",
                row,
            )
        dbapi_conn.commit()
        cursor.close()

    def _before_cursor_execute(_conn, _cursor, statement, *_args):
        if "information_schema.columns" in statement:
            schema_calls.append(statement)

    engine = svc.connection_pool.get_engine(1, 1, f"sqlite:///{tmp_path / 'batch.db'}")
    event.listen(engine, "connect", _on_connect)
    event.listen(engine, "before_cursor_execute", _before_cursor_execute)
    svc._SCHEMA_CACHE.clear()  # isolate from other tests in the process
    try:
        yield engine, schema_calls
    finally:
        event.remove(engine, "connect", _on_connect)
        event.remove(engine, "before_cursor_execute", _before_cursor_execute)
        svc._SCHEMA_CACHE.clear()


def test_full_schema_is_single_batch_query(batched_engine):
    """Two tables must be introspected with exactly ONE schema statement."""
    from connections import service as svc

    _engine, schema_calls = batched_engine
    svc.invalidate_schema_cache(1, 1)

    schema = svc.get_full_schema(1, 1, "sqlite:///:memory:")

    assert (
        len(schema_calls) == 1
    ), f"expected one batched information_schema query, got: {schema_calls}"

    tables = {t["table_name"]: t["columns"] for t in schema["tables"]}
    assert set(tables) == {"alpha", "beta"}
    # Ordering and grouping must survive the single roundtrip.
    assert tables["alpha"] == [
        {"name": "id", "type": "INTEGER", "nullable": False, "default": None},
        {"name": "name", "type": "TEXT", "nullable": True, "default": None},
    ]
    assert tables["beta"][1] == {
        "name": "kind",
        "type": "TEXT",
        "nullable": True,
        "default": "'row'",
    }


def test_cache_serves_and_invalidates(batched_engine):
    """Cache hits avoid a second roundtrip; invalidation forces a refresh."""
    from connections import service as svc

    _engine, schema_calls = batched_engine

    first = svc.get_full_schema(1, 1, "sqlite:///:memory:")
    assert len(schema_calls) == 1

    cached = svc.get_full_schema(1, 1, "sqlite:///:memory:")
    assert cached == first
    assert len(schema_calls) == 1, "cache hit must not re-run the schema query"

    svc.invalidate_schema_cache(1, 1)
    refreshed = svc.get_full_schema(1, 1, "sqlite:///:memory:")
    assert refreshed == first
    assert len(schema_calls) == 2, "post-invalidation must re-run the query"
