"""The test fixture must never touch a real database.

The ``app_client`` fixture tears down with ``db.drop_all()``, which drops
whatever the app is bound to. The app takes its URL from the *cached*
settings object (``app.py`` binds ``settings.DATABASE_URL``), so a
``DATABASE_URL`` that leaked in from the developer's ``.env`` would make the
whole suite delete the tables of a real database.

That is not hypothetical: a test that read the settings before the fixture
ran poisoned the cache, the app bound to the developer's PostgreSQL
database, and ``drop_all()`` removed its tables. The fixture now clears the
settings cache before building the app and refuses to drop anything that is
not a throwaway SQLite file.

These tests are the tripwire for that.
"""

import pytest
from sqlalchemy.engine import make_url


@pytest.fixture()
def poisoned_cache():
    """Simulate an earlier test that read the settings outside the fixture.

    Requested *before* ``app_client`` so the cache is filled with the
    DATABASE_URL from the developer's .env before the app is built.
    """
    from config import get_settings

    return get_settings()


def _assert_throwaway_sqlite(app):
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    assert uri.startswith("sqlite://"), f"tests must never touch a real database (bound to {uri})"
    assert "phase0.db" in uri, f"tests must run against the throwaway file (bound to {uri})"


def test_app_never_binds_to_a_real_database(app_client):
    """The app under test must be bound to the throwaway SQLite file."""
    app, _ = app_client
    _assert_throwaway_sqlite(app)


def test_poisoned_settings_cache_cannot_redirect_the_app(poisoned_cache, app_client):
    """Even with a poisoned cache, the fixture must still point at SQLite.

    Reading the settings before the fixture runs is what caused the
    incident: the cached DATABASE_URL came from the developer's .env and
    the app bound to their database.
    """
    app, _ = app_client
    _assert_throwaway_sqlite(app)


def test_app_built_outside_the_fixture_also_uses_sqlite():
    """An app built without the app_client fixture must still be on SQLite.

    Several tests build the app themselves - the config tests and the
    OAuth-reload test do - and those never go through ``app_client``. The
    session-wide hermetic fixture is what covers them: without it they
    would be configured against the developer's own database.
    """
    from app import create_app

    app = create_app()
    uri = app.config["SQLALCHEMY_DATABASE_URI"]

    assert uri.startswith("sqlite://"), f"tests must never touch a real database (bound to {uri})"


def test_a_test_that_never_uses_the_app_still_cannot_see_the_real_database():
    """A test that only reads the settings must not learn the real URL.

    This is the exact step that caused the incident: reading the settings
    outside the fixture window cached the DATABASE_URL from the developer's
    .env. The hermetic fixture now makes that value a throwaway file.
    """
    from config import get_settings

    uri = get_settings().DATABASE_URL

    assert uri.startswith("sqlite://"), f"tests must never see a real database URL (got {uri})"


def _postgres_engine():
    """A PostgreSQL engine whose connections never touch the network.

    The guard runs on ``before_cursor_execute``, which only fires on a
    real connection, so testing it needs one. Pointing it at a PostgreSQL
    server would defeat the purpose, and CI has no server - so the
    connection is replaced with a fake DBAPI connection.

    Everything else is real: the PostgreSQL dialect compiles the SQL, the
    event fires, and the guard code runs unchanged. Only the socket is
    gone, so the test proves the refusal without needing a database.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.dialects import registry

    from tests.fake_dbapi import FakePGDialect, fake_creator

    # Register the fake driver under the postgres namespace, so the URL
    # still reads as postgresql and the guard still classifies it as a
    # real database.
    registry.register("postgresql.fake", "tests.fake_dbapi", "FakePGDialect")
    assert FakePGDialect is not None

    executed: list[str] = []

    engine = create_engine(
        "postgresql+fake://postgres:0728@localhost:5432/ai_user",
        creator=fake_creator(executed),
    )
    return engine, executed


def _writes(statements) -> list[str]:
    """The subset of ``statements`` that changes data or schema."""
    from tests.db_guard import is_write_statement

    return [s for s in statements if is_write_statement(s)]


def test_writing_to_a_real_database_server_is_refused():
    """The guard must block a write against a live database.

    The URL being a SQLite string is not enough on its own: a test could
    build its own engine from a URL it read elsewhere. This guard refuses
    the write at the SQLAlchemy level, so the test fails loudly instead
    of quietly reaching the developer's data.

    The check has to sit at the SQLAlchemy layer. A socket-level guard
    does not work: psycopg2 talks to libpq, a C library that opens its
    own sockets and never touches Python's ``socket`` module - a socket
    guard silently let a ``DROP TABLE`` through.
    """
    from sqlalchemy import text

    engine, executed = _postgres_engine()

    with pytest.raises(RuntimeError, match="must never write to a real database"):
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE users"))

    assert not _writes(executed), f"a write reached the database: {executed}"


def test_reading_a_real_database_is_still_allowed():
    """Reads must stay possible - only writes are forbidden.

    A test may legitimately inspect a real database (checking a schema
    filter, for instance). Blocking reads would make that verification
    impossible for no safety gain.
    """
    from sqlalchemy import text

    engine, executed = _postgres_engine()

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    assert executed, "the read must still be allowed through"


def test_drop_all_against_a_real_database_is_refused():
    """The incident mechanism itself must be refused.

    On 2026-11-13 the fixture's ``db.drop_all()`` ran against the
    developer's live database and removed its tables. This drops the very
    same ORM tables, against the very same server, and the guard must stop
    it before the first ``DROP TABLE`` reaches the database.
    """
    from auths.models import db

    engine, executed = _postgres_engine()

    with pytest.raises(RuntimeError, match="must never write to a real database"):
        db.metadata.drop_all(engine)

    assert not _writes(executed), f"a write reached the database: {executed}"


def test_create_all_against_a_real_database_is_refused():
    """Creating tables in a real database must be refused too.

    ``checkfirst=False`` so the CREATE is emitted unconditionally: with
    the check, the fake's "the table already exists" answer would skip
    the statement and the test would prove nothing.
    """
    from sqlalchemy import Column, Integer
    from sqlalchemy.orm import declarative_base

    Base = declarative_base()

    class Widget(Base):
        __tablename__ = "widget_probe"
        id = Column(Integer, primary_key=True)

    engine, executed = _postgres_engine()

    with pytest.raises(RuntimeError, match="must never write to a real database"):
        Base.metadata.create_all(engine, checkfirst=False)

    assert not _writes(executed), f"a write reached the database: {executed}"


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO users (email) VALUES ('x@example.com')",
        "UPDATE users SET email = 'x@example.com'",
        "DELETE FROM users",
        "DROP TABLE users",
        "CREATE TABLE t (id INTEGER)",
        "ALTER TABLE users ADD COLUMN x INTEGER",
        "TRUNCATE TABLE users",
        "MERGE INTO users USING users ON true WHEN MATCHED THEN UPDATE SET email = 'x'",
    ],
)
def test_every_write_statement_is_classified_as_a_write(statement):
    """The classifier must catch every way of changing a database."""
    from tests.db_guard import is_write_statement

    assert is_write_statement(statement) is True


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT * FROM users",
        "SELECT 1",
        "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent",
        "SHOW tables",
        "EXPLAIN SELECT * FROM users",
    ],
)
def test_read_statements_are_not_classified_as_writes(statement):
    """A read must never be mistaken for a write."""
    from tests.db_guard import is_write_statement

    assert is_write_statement(statement) is False


def test_unparsable_sql_is_treated_as_a_write():
    """SQL that cannot be classified cannot be shown to be harmless."""
    from tests.db_guard import is_write_statement

    assert is_write_statement("this is not sql at all ;;;") is True


def test_sqlite_is_not_a_real_database():
    """The suite's own database must never be blocked."""
    from tests.db_guard import is_real_database_url

    assert is_real_database_url(make_url("sqlite:///phase0.db")) is False
    assert is_real_database_url(make_url("sqlite:///:memory:")) is False
    assert is_real_database_url(make_url("postgresql://u:p@host:5432/db")) is True
    assert is_real_database_url(make_url("mysql://u:p@host:3306/db")) is True
