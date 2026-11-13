"""Refuse writes to a real database server while the test suite runs.

The suite is supposed to run entirely on throwaway SQLite files. This
module is the last line of defence: even if a test builds its own engine
from a URL it read out of the developer's ``.env``, a write against it is
refused instead of silently landing in their data.

Why it sits at the SQLAlchemy layer
-----------------------------------

A socket-level guard does **not** work here. psycopg2 talks to libpq, a C
library that opens its own sockets and never goes through Python's
``socket`` module. A socket guard was tried and silently let a
``DROP TABLE`` through - it only failed because a foreign key happened to
block that particular statement. SQLAlchemy's ``before_cursor_execute``
event is the one place every driver and every ORM path goes through.

Reads stay allowed: a test may legitimately inspect a real database's
schema, which is how the ignored-table feature was verified. Only writes
are refused.

The statement classification uses sqlglot, which is already a dependency
and already used by ``ai.guards``. It does not have to guess from
keywords: a CTE that ends in an INSERT is an INSERT, and a SELECT is a
SELECT.
"""

import sqlglot
from sqlglot import exp

# The URL schemes that address a real database server. SQLite is the only
# one the test suite is allowed to write to.
REAL_DB_SCHEMES = frozenset(
    {
        "postgresql",
        "postgres",
        "mysql",
        "mariadb",
        "mssql",
        "oracle",
        "cockroachdb",
    }
)

# Statement types that change data or schema. Anything else is a read.
WRITE_EXPRESSIONS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
)


def is_write_statement(statement: str) -> bool:
    """True when the SQL changes data or schema.

    Unparsable SQL is treated as a write: if the statement cannot be
    classified, it cannot be shown to be harmless either.
    """
    try:
        parsed = sqlglot.parse_one(statement, read="postgres")
    except Exception:  # noqa: BLE001 - unparsable SQL is not trusted
        return True

    if parsed is None:
        return True
    return isinstance(parsed, WRITE_EXPRESSIONS)


def is_real_database_url(url) -> bool:
    """True when the URL addresses a real database server."""
    return url.get_backend_name() in REAL_DB_SCHEMES


def refuse_real_database_writes(conn, cursor, statement, parameters, context, executemany) -> None:
    """SQLAlchemy ``before_cursor_execute`` hook: block writes to real databases.

    Raises ``RuntimeError`` before the statement is sent, so the database
    never sees it.
    """
    url = conn.engine.url
    if not is_real_database_url(url):
        return

    if is_write_statement(statement):
        raise RuntimeError(
            f"tests must never write to a real database server "
            f"({url.drivername}://{url.host}/{url.database}): "
            f"{statement!r}. Use a throwaway SQLite file instead."
        )


__all__ = [
    "REAL_DB_SCHEMES",
    "WRITE_EXPRESSIONS",
    "is_real_database_url",
    "is_write_statement",
    "refuse_real_database_writes",
]
