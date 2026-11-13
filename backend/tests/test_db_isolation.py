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
