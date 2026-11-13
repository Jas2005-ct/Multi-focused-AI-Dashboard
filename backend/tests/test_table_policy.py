"""The ignored-table policy: what is hidden, and from where.

A table that is hidden from the listing but still reachable through
``sample_rows`` or a raw ``SELECT`` would not really be hidden - the agent
only has to guess the name. These tests pin the policy at every layer: the
policy helper itself, the service (listings and schema), the agent's tools
and the SQL guard.
"""

import pytest
from sqlalchemy import event, text

# Tables the fake database exposes: two ordinary ones and four that the
# policy hides (two by prefix, two by exact name).
_TABLES = [
    "orders",
    "users",
    "auth_users",
    "django_migrations",
    "refresh_tokens",
    "db_connections",
]

# Distinct pool ids so this fixture never collides with another test's
# cached engine.
_USER_ID = 4242
_DB_ID = 4243


@pytest.fixture()
def ignore_policy(monkeypatch):
    """Configure the ignored-table policy for one test.

    The properties are patched on the ``Settings`` class, so they apply to
    every instance - including one built after the settings cache is
    cleared - and they cannot leak past the test. Patching a cached
    instance instead would silently stop applying as soon as something
    else cleared that cache.
    """
    from config import Settings

    def _configure(prefixes: str = "auth_,django_", tables: str = "refresh_tokens,db_connections"):
        monkeypatch.setattr(
            Settings,
            "ignored_table_prefixes",
            property(lambda _self: [p.strip().lower() for p in prefixes.split(",") if p.strip()]),
        )
        monkeypatch.setattr(
            Settings,
            "ignored_tables",
            property(lambda _self: [t.strip().lower() for t in tables.split(",") if t.strip()]),
        )

    _configure()
    return _configure


@pytest.fixture()
def fake_db(app_client, tmp_path):
    """A SQLite database with real tables and a fake information_schema."""
    from connections import service as svc

    url = f"sqlite:///{tmp_path / 'policy.db'}"

    def _on_connect(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("ATTACH ':memory:' AS information_schema")
        cursor.execute(
            "CREATE TABLE information_schema.tables (TABLE_SCHEMA TEXT, TABLE_NAME TEXT)"
        )
        cursor.execute(
            "CREATE TABLE information_schema.columns ("
            "TABLE_SCHEMA TEXT, TABLE_NAME TEXT, COLUMN_NAME TEXT, DATA_TYPE TEXT, "
            "IS_NULLABLE TEXT, COLUMN_DEFAULT TEXT, ORDINAL_POSITION INTEGER)"
        )
        for table in _TABLES:
            cursor.execute("INSERT INTO information_schema.tables VALUES ('public', ?)", (table,))
            cursor.execute(
                "INSERT INTO information_schema.columns VALUES "
                "('public', ?, 'id', 'INTEGER', 'NO', NULL, 1)",
                (table,),
            )
        dbapi_conn.commit()
        cursor.close()

    engine = svc.connection_pool.get_engine(_USER_ID, _DB_ID, url)
    event.listen(engine, "connect", _on_connect)
    with engine.begin() as conn:
        for table in _TABLES:
            conn.execute(text(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY, name TEXT)'))
            conn.execute(text(f'INSERT INTO "{table}" (name) VALUES (:n)'), {"n": "row"})
    svc.invalidate_schema_cache(_USER_ID, _DB_ID)
    try:
        yield url
    finally:
        event.remove(engine, "connect", _on_connect)
        svc.invalidate_schema_cache(_USER_ID, _DB_ID)
        # Drop the pooled engine: it is cached per (user, db) and would
        # otherwise point at this test's temporary database file.
        svc.connection_pool.close_pool(_USER_ID, _DB_ID)


class _StubConnection:
    """Stands in for a saved connection row."""

    def __init__(self, url: str):
        self._url = url

    def get_decrypted_connection_string(self) -> str:
        return self._url


@pytest.fixture()
def stub_connection(fake_db, monkeypatch):
    """Point the agent's tools at the fake database."""
    from ai.tools import introspection as introspection_tools

    monkeypatch.setattr(
        introspection_tools,
        "_resolve_connection",
        lambda _uid, _did: _StubConnection(fake_db),
    )
    return fake_db


# --- the policy helper ---------------------------------------------------


def test_prefix_match_is_case_insensitive(ignore_policy):
    from common.table_policy import is_table_ignored

    assert is_table_ignored("auth_users") is True
    assert is_table_ignored("AUTH_USERS") is True
    assert is_table_ignored("Auth_Users") is True
    assert is_table_ignored("django_migrations") is True


def test_exact_name_match(ignore_policy):
    from common.table_policy import is_table_ignored

    assert is_table_ignored("refresh_tokens") is True
    assert is_table_ignored("db_connections") is True
    # A prefix is not an exact name.
    assert is_table_ignored("refresh_tokens_log") is False


def test_quoted_names_are_normalised(ignore_policy):
    from common.table_policy import is_table_ignored

    assert is_table_ignored('"auth_users"') is True
    assert is_table_ignored("`auth_users`") is True
    assert is_table_ignored("  auth_users  ") is True


def test_empty_policy_hides_nothing(ignore_policy):
    from common.table_policy import is_table_ignored

    ignore_policy(prefixes="", tables="")
    assert is_table_ignored("auth_users") is False
    assert is_table_ignored("refresh_tokens") is False


def test_visible_tables_filters(ignore_policy):
    from common.table_policy import visible_tables

    assert visible_tables(_TABLES) == ["orders", "users"]


# --- the service layer ---------------------------------------------------


def test_get_tables_hides_policy_tables(fake_db, ignore_policy):
    from connections import service as svc

    assert svc.get_tables(_USER_ID, _DB_ID, fake_db) == ["orders", "users"]


def test_get_full_schema_hides_policy_tables(fake_db, ignore_policy):
    from connections import service as svc

    schema = svc.get_full_schema(_USER_ID, _DB_ID, fake_db)

    assert [t["table_name"] for t in schema["tables"]] == ["orders", "users"]


def test_schema_cache_does_not_hold_hidden_tables(fake_db, ignore_policy):
    """The cache is filled with the visible schema only."""
    from connections import service as svc

    svc.get_full_schema(_USER_ID, _DB_ID, fake_db)
    cached = svc.get_cached_schema(_USER_ID, _DB_ID)

    assert cached is not None
    assert [t["table_name"] for t in cached["tables"]] == ["orders", "users"]


def test_get_table_schema_refuses_hidden_table(fake_db, ignore_policy):
    from connections import service as svc

    with pytest.raises(ValueError, match="not accessible"):
        svc.get_table_schema(_USER_ID, _DB_ID, fake_db, "auth_users")


def test_get_table_schema_still_serves_visible_tables(fake_db, ignore_policy):
    from connections import service as svc

    schema = svc.get_table_schema(_USER_ID, _DB_ID, fake_db, "orders")
    assert schema["table_name"] == "orders"
    assert schema["columns"][0]["name"] == "id"


# --- the agent's tools ---------------------------------------------------


def test_describe_table_tool_refuses_hidden_table(stub_connection, ignore_policy):
    from ai.tools import introspection as introspection_tools

    with pytest.raises(ValueError, match="not accessible"):
        introspection_tools.describe_table.invoke(
            {"user_id": _USER_ID, "db_id": _DB_ID, "table_name": "auth_users"}
        )


def test_sample_rows_tool_refuses_hidden_table(stub_connection, ignore_policy):
    from ai.tools import introspection as introspection_tools

    with pytest.raises(ValueError, match="not accessible"):
        introspection_tools.sample_rows.invoke(
            {"user_id": _USER_ID, "db_id": _DB_ID, "table_name": "refresh_tokens"}
        )


def test_count_rows_tool_refuses_hidden_table(stub_connection, ignore_policy):
    from ai.tools import introspection as introspection_tools

    with pytest.raises(ValueError, match="not accessible"):
        introspection_tools.count_rows.invoke(
            {"user_id": _USER_ID, "db_id": _DB_ID, "table_name": "db_connections"}
        )


def test_sample_rows_tool_still_serves_visible_tables(stub_connection, ignore_policy):
    from ai.tools import introspection as introspection_tools

    rows = introspection_tools.sample_rows.invoke(
        {"user_id": _USER_ID, "db_id": _DB_ID, "table_name": "orders"}
    )
    assert rows and rows[0]["name"] == "row"


# --- the SQL guard -------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM auth_users",
        "SELECT * FROM public.auth_users",
        "SELECT * FROM django_migrations",
        "SELECT * FROM refresh_tokens",
        "SELECT * FROM db_connections",
        "SELECT o.id FROM orders o JOIN auth_users a ON o.user_id = a.id",
        "SELECT * FROM orders WHERE id IN (SELECT id FROM django_session)",
        "WITH t AS (SELECT * FROM auth_users) SELECT * FROM t",
        'SELECT COUNT(*) FROM "Auth_Users"',
    ],
)
def test_guard_blocks_hidden_tables(sql, ignore_policy):
    from ai.guards import validate_sql_ast

    is_safe, error = validate_sql_ast(sql)
    assert is_safe is False
    assert "not accessible" in error


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM orders",
        "SELECT * FROM users",
        "SELECT * FROM orders LIMIT 5",
        "WITH auth_thing AS (SELECT 1 AS x) SELECT * FROM auth_thing",
        "SELECT * FROM generate_series(1, 10)",
    ],
)
def test_guard_allows_visible_tables(sql, ignore_policy):
    from ai.guards import validate_sql_ast

    is_safe, error = validate_sql_ast(sql)
    assert is_safe is True, error


def test_guard_allows_everything_when_the_policy_is_empty(ignore_policy):
    from ai.guards import validate_sql_ast

    ignore_policy(prefixes="", tables="")
    is_safe, error = validate_sql_ast("SELECT * FROM auth_users")
    assert is_safe is True, error
