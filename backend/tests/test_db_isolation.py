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
    from sqlalchemy import create_engine, text

    engine = create_engine("postgresql://postgres:0728@localhost:5432/ai_user")

    with pytest.raises(RuntimeError, match="must never write to a real database"):
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE users"))


def test_reading_a_real_database_is_still_allowed():
    """Reads must stay possible - only writes are forbidden.

    A test may legitimately inspect a real database (checking a schema
    filter, for instance). Blocking reads would make that verification
    impossible for no safety gain.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine("postgresql://postgres:0728@localhost:5432/ai_user")

    with engine.connect() as conn:
        value = conn.execute(text("SELECT 1")).scalar()

    assert value == 1


def test_drop_all_against_a_real_database_is_refused():
    """The incident mechanism itself must be refused.

    On 2026-11-13 the fixture's ``db.drop_all()`` ran against the
    developer's live database and removed its tables. This drops the very
    same ORM tables, against the very same server, and the guard must stop
    it before the first ``DROP TABLE`` reaches the database.
    """
    from sqlalchemy import create_engine

    from auths.models import db

    engine = create_engine("postgresql://postgres:0728@localhost:5432/ai_user")

    with pytest.raises(RuntimeError, match="must never write to a real database"):
        db.metadata.drop_all(engine)


def test_create_all_against_a_real_database_is_refused():
    """Creating tables in a real database must be refused too."""
    from sqlalchemy import Column, Integer, create_engine
    from sqlalchemy.orm import declarative_base

    Base = declarative_base()

    class Widget(Base):
        __tablename__ = "widget_probe"
        id = Column(Integer, primary_key=True)

    engine = create_engine("postgresql://postgres:0728@localhost:5432/ai_user")

    with pytest.raises(RuntimeError, match="must never write to a real database"):
        Base.metadata.create_all(engine)
