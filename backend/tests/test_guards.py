"""Safety-guard regression: writes must report the read-only message.

Historical failure: the write-type tuple in `validate_sql_ast` listed
`exp.Truncate`, which sqlglot does not define (it is `exp.TruncateTable`).
Building that tuple raised AttributeError, which the generic handler turned
into "Validation error: module 'sqlglot.expressions' has no attribute
'Truncate'" — so the intended "Write operations not permitted" message was
unreachable and every write attempt reported a confusing internal error.

The writes were still rejected, so this was a message bug rather than a
security hole. These tests lock the message.
"""

import pytest

from ai.guards import validate_sql_ast


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO users (email) VALUES ('a@b.c')",
        "UPDATE users SET email = 'a@b.c'",
        "DELETE FROM users",
        "TRUNCATE TABLE users",
        "DROP TABLE users",
        "CREATE TABLE t (id INT)",
        "ALTER TABLE users ADD COLUMN x INT",
        "MERGE INTO users USING src ON users.id = src.id WHEN MATCHED THEN UPDATE SET users.x = src.x",
    ],
)
def test_write_statements_report_read_only(sql):
    is_safe, error = validate_sql_ast(sql)
    assert is_safe is False
    assert "Write operations not permitted" in error


def test_select_is_allowed():
    assert validate_sql_ast("SELECT id FROM users") == (True, "")


def test_cte_is_allowed():
    is_safe, error = validate_sql_ast("WITH t AS (SELECT 1 AS x) SELECT * FROM t")
    assert is_safe is True
    assert error == ""


def test_non_select_non_write_is_rejected_by_shape():
    is_safe, error = validate_sql_ast("SHOW TABLES")
    assert is_safe is False
    assert "must start with SELECT or WITH" in error


def test_multiple_statements_are_rejected():
    is_safe, error = validate_sql_ast("SELECT 1; SELECT 2")
    assert is_safe is False
    assert "Multiple statements not allowed" in error


def test_dangerous_function_is_rejected():
    is_safe, error = validate_sql_ast("SELECT pg_sleep(10)")
    assert is_safe is False
    assert "Dangerous function detected" in error


def test_comments_are_not_rejected_despite_the_guard():
    """Documents a gap: the "comments not allowed" guard never fires.

    `validate_sql_ast` looks for `exp.Comment` nodes, but sqlglot keeps
    comments in an expression's `comments` attribute instead of as nodes, so
    the walk finds none. Comments therefore pass validation and are
    re-serialised into the SQL that is executed.

    That is harmless in practice — the SQL is parsed and validated as an AST
    before it runs, so a comment cannot smuggle anything — but it contradicts
    the guard's stated policy. Making it fire would start rejecting queries
    that work today, so it is left alone and pinned here instead.
    """
    is_safe, error = validate_sql_ast("-- a comment\nSELECT 1")
    assert is_safe is True
    assert error == ""


def test_comments_survive_into_the_executed_sql():
    from ai.guards import add_safety_limits

    assert "/* a comment */" in add_safety_limits("-- a comment\nSELECT 1")
