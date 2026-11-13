"""Schema rows are read by column name, not by position.

The information_schema queries serve both PostgreSQL and MySQL, and the two
drivers report the column labels in different cases - PostgreSQL in lower
case, MySQL in upper case. Reading a row by name means the SELECT and the
reader no longer have to be kept in sync by hand: reordering the columns or
adding one in the middle can no longer silently put the wrong value in the
wrong field.

The fake information_schema below declares its columns in UPPER CASE, which
is what a MySQL server reports, so these tests fail if the case
normalisation is dropped.
"""

import pytest
from sqlalchemy import Engine, event, text

# (table_name, column_name, data_type, is_nullable, column_default, ordinal_position)
_FAKE_ROWS = [
    ("alpha", "id", "INTEGER", "NO", None, 1),
    ("alpha", "kind", "TEXT", "YES", "'row'", 2),
]


@pytest.fixture()
def mysql_style_engine(app_client, tmp_path) -> Engine:
    """An engine whose information_schema reports UPPER CASE column labels.

    Uses a dedicated (user_id, db_id) so it gets its own pooled engine and
    does not share state with the other schema tests.
    """
    from connections import service as svc

    def _on_connect(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("ATTACH ':memory:' AS information_schema")
        cursor.execute(
            "CREATE TABLE information_schema.columns ("
            "TABLE_SCHEMA TEXT, TABLE_NAME TEXT, COLUMN_NAME TEXT, DATA_TYPE TEXT, "
            "IS_NULLABLE TEXT, COLUMN_DEFAULT TEXT, ORDINAL_POSITION INTEGER)"
        )
        for table_name, column_name, data_type, is_nullable, default, position in _FAKE_ROWS:
            cursor.execute(
                "INSERT INTO information_schema.columns VALUES " "('public', ?, ?, ?, ?, ?, ?)",
                (table_name, column_name, data_type, is_nullable, default, position),
            )
        cursor.execute(
            "CREATE TABLE information_schema.tables (TABLE_SCHEMA TEXT, TABLE_NAME TEXT)"
        )
        cursor.execute("INSERT INTO information_schema.tables VALUES ('public', 'alpha')")
        dbapi_conn.commit()
        cursor.close()

    engine = svc.connection_pool.get_engine(77, 88, f"sqlite:///{tmp_path / 'named.db'}")
    event.listen(engine, "connect", _on_connect)
    svc.invalidate_schema_cache(77, 88)
    try:
        yield engine
    finally:
        event.remove(engine, "connect", _on_connect)
        svc.invalidate_schema_cache(77, 88)


def test_fake_schema_reports_upper_case_labels(mysql_style_engine):
    """Guard for the test itself: the fake must really be upper case."""
    with mysql_style_engine.connect() as conn:
        row = (
            conn.execute(text("SELECT table_name, column_name FROM information_schema.columns"))
            .mappings()
            .first()
        )
    assert list(row.keys()) == ["TABLE_NAME", "COLUMN_NAME"]


def test_full_schema_reads_columns_by_name(mysql_style_engine):
    """Each field must come from its own column, not from a shifted position."""
    from connections import service as svc

    schema = svc.get_full_schema(77, 88, "sqlite:///:memory:")

    assert len(schema["tables"]) == 1
    table = schema["tables"][0]
    assert table["table_name"] == "alpha"
    assert table["columns"] == [
        {"name": "id", "type": "INTEGER", "nullable": False, "default": None},
        {"name": "kind", "type": "TEXT", "nullable": True, "default": "'row'"},
    ]


def test_table_schema_reads_columns_by_name(mysql_style_engine):
    from connections import service as svc

    schema = svc.get_table_schema(77, 88, "sqlite:///:memory:", "alpha")

    assert schema["table_name"] == "alpha"
    assert schema["columns"] == [
        {"name": "id", "type": "INTEGER", "nullable": False, "default": None},
        {"name": "kind", "type": "TEXT", "nullable": True, "default": "'row'"},
    ]


def test_get_tables_returns_table_names(mysql_style_engine):
    from connections import service as svc

    assert svc.get_tables(77, 88, "sqlite:///:memory:") == ["alpha"]
