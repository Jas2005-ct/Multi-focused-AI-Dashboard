"""A fake DBAPI connection, so the guard can be tested without a server.

SQLAlchemy's ``before_cursor_execute`` event only fires on a real
connection, so testing the guard needs a connection. Pointing it at a
PostgreSQL server would defeat the purpose (and CI has no server), so
this module provides a minimal DBAPI connection that satisfies the
psycopg2 dialect without opening a socket.

Everything else is real: the real PostgreSQL dialect compiles the SQL,
the real event fires, and the real guard code runs. Only the socket is
replaced.
"""

from typing import Any

from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2


def _is_read(statement: str) -> bool:
    """True when the statement only reads.

    Uses the same classifier as the guard, so the fake answers exactly
    what the guard would call a read.
    """
    from tests.db_guard import is_write_statement

    return not is_write_statement(statement)


# A DBAPI description entry: name, type code, display size, internal
# size, precision, scale, null_ok.
_COLUMN = ("pg_class_relname", 25, None, None, None, None, True)


class FakeCursor:
    """A cursor that records statements instead of executing them."""

    def __init__(self, log: list[str], connection=None):
        self._log = log
        self.connection = connection
        self.description: Any = None
        self.rowcount = -1
        self.arraysize = 1
        self._rows: list = []

    def execute(self, statement, parameters=None, *args, **kwargs):
        self._log.append(str(statement))
        self._rows = []
        # A read gets a row back, a write gets none. This matters: SQLAlchemy
        # asks "does this table exist?" before dropping it, and a fake that
        # always answers "no" would make drop_all a no-op - the write would
        # never be attempted, and the test would prove nothing.
        if _is_read(str(statement)):
            self.description = (_COLUMN,)
            self._rows = [("pg_class_relname",)]
        else:
            self.description = None
        self.rowcount = -1

    def executemany(self, statement, parameters=None, *args, **kwargs):
        self._log.append(str(statement))

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def fetchone(self):
        if not self._rows:
            return None
        return self._rows.pop(0)

    def fetchmany(self, size=None):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()


class FakeConnection:
    """A DBAPI connection that accepts statements and does nothing."""

    def __init__(self, log: list[str]):
        self._log = log
        # The psycopg2 dialect reads `notices` after every statement.
        self.notices: list = []

    def cursor(self):
        # The psycopg2 dialect reads `cursor.connection` when it builds
        # the result, so the cursor needs a back-reference.
        return FakeCursor(self._log, connection=self)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()


def fake_creator(log: list[str]):
    """A ``creator`` callable for SQLAlchemy's connection pool."""

    def _connect():
        return FakeConnection(log)

    return _connect


class FakePGDialect(PGDialect_psycopg2):
    """The real PostgreSQL dialect, minus the libpq-specific connect hooks.

    ``on_connect`` would otherwise register UUID/hstore/JSON types with
    libpq, which needs a real connection. Everything that matters for the
    guard is untouched: the dialect, the URL and the SQL are all real.
    """

    # The fake DBAPI is not a real driver, so the statement cache would
    # only get in the way.
    supports_statement_cache = False

    def on_connect(self):
        return None

    def initialize(self, connection):
        # Skip the hstore detection - it queries a real server.
        self.supports_sane_multi_rowcount = True
