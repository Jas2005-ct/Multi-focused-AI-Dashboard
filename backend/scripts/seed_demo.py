"""Seed the shared demo database with a synthetic e-commerce dataset.

The demo database is a *separate* database from the application's own: it
holds nothing but fake rows, so a visitor who connects to it can only ever
see sample data. It is what the "Add demo database" button points at, and
what the AI assistant queries during a demo.

Usage
-----
    python scripts/seed_demo.py
    python scripts/seed_demo.py --url postgresql://user:pass@host:5432/demo_ai_db
    python scripts/seed_demo.py --reader-password "s3cret"

The URL comes from ``--url`` or the ``DEMO_DB_URL`` environment variable.
The script is idempotent: it drops and recreates the four demo tables, so
it can be re-run to refresh the data.

Safety
------
Two rails, because this script writes to a real server:

* the target database name must contain "demo" (override with
  ``--allow-any-database``), and
* the script refuses to run against a database that holds the application's
  own tables (``users``, ``refresh_tokens``, ``db_connections``), so it can
  never touch the app's data even by mistake.

The read-only role is the point of the whole exercise: ``demo_reader`` may
only SELECT, so the demo database refuses writes no matter what the
application asks of it.
"""

from __future__ import annotations

import argparse
import csv
import os
import secrets
import statistics
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql
from psycopg2.extras import execute_values

# Read backend/.env so DEMO_DB_URL is picked up without exporting it by
# hand. Existing environment variables win - load_dotenv never overrides.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_CSV = Path(__file__).resolve().parent / "data" / "sample-ecommerce-orders.csv"
READER_ROLE = "demo_reader"

# The tables this script owns. Nothing else in the target database is
# touched.
DEMO_TABLES = ("customers", "products", "orders", "order_items")

# Tables that mean "this is the application's own database, hands off".
APPLICATION_TABLES = {"users", "refresh_tokens", "db_connections"}

CENTS = Decimal("0.01")

SCHEMA_SQL = """
DROP TABLE IF EXISTS order_items, orders, products, customers CASCADE;

CREATE TABLE customers (
    customer_id         INTEGER PRIMARY KEY,
    email               TEXT NOT NULL,
    country             TEXT NOT NULL,
    acquisition_channel TEXT NOT NULL,
    first_order_at      TIMESTAMP NOT NULL
);

CREATE TABLE products (
    sku        TEXT PRIMARY KEY,
    category   TEXT NOT NULL,
    list_price NUMERIC(12, 2) NOT NULL
);

CREATE TABLE orders (
    order_id        INTEGER PRIMARY KEY,
    ordered_at      TIMESTAMP NOT NULL,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    channel         TEXT NOT NULL,
    device          TEXT NOT NULL,
    currency        TEXT NOT NULL,
    payment_method  TEXT NOT NULL,
    status          TEXT NOT NULL,
    order_total     NUMERIC(12, 2) NOT NULL,
    shipping_cost   NUMERIC(12, 2) NOT NULL,
    is_first_order  BOOLEAN NOT NULL,
    days_to_deliver INTEGER
);

CREATE TABLE order_items (
    order_id      INTEGER NOT NULL REFERENCES orders(order_id),
    sku           TEXT NOT NULL REFERENCES products(sku),
    quantity      INTEGER NOT NULL,
    unit_price    NUMERIC(12, 2) NOT NULL,
    discount_pct  NUMERIC(5, 4) NOT NULL,
    line_total    NUMERIC(12, 2) NOT NULL,
    refund_amount NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (order_id, sku)
);

CREATE INDEX idx_orders_customer   ON orders(customer_id);
CREATE INDEX idx_orders_ordered_at ON orders(ordered_at);
CREATE INDEX idx_orders_status     ON orders(status);
CREATE INDEX idx_order_items_sku   ON order_items(sku);
"""


def money(value: Decimal) -> Decimal:
    """Round to cents, the way the source data does."""
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--url",
        default=None,
        help="Target database URL. Defaults to the DEMO_DB_URL environment variable.",
    )
    parser.add_argument(
        "--csv",
        default=str(DEFAULT_CSV),
        help="Source CSV file (default: the bundled sample).",
    )
    parser.add_argument(
        "--reader-password",
        default=os.environ.get("DEMO_DB_READER_PASSWORD"),
        help="Password for the read-only demo_reader role. Generated if omitted.",
    )
    parser.add_argument(
        "--allow-any-database",
        action="store_true",
        help="Allow a target database whose name does not contain 'demo'.",
    )
    parser.add_argument(
        "--skip-reader-role",
        action="store_true",
        help="Do not create the read-only demo_reader role.",
    )
    return parser.parse_args(argv)


def resolve_url(args: argparse.Namespace) -> str:
    url = args.url or os.environ.get("DEMO_DB_URL") or ""
    if not url:
        raise SystemExit(
            "No target URL. Pass --url or set DEMO_DB_URL "
            "(e.g. postgresql://postgres:postgres@localhost:5432/demo_ai_db)."
        )
    return url


def assert_safe_target(conn, database_name: str, allow_any: bool) -> None:
    """Refuse to seed a database that is not a demo database.

    Two rails: the name has to say "demo", and the database must not hold
    the application's own tables. Either one alone would be enough to
    protect the developer's data - together they make a mistake very hard.
    """
    if "demo" not in database_name.lower() and not allow_any:
        raise SystemExit(
            f"Refusing to seed {database_name!r}: the database name must contain "
            f"'demo'. Pass --allow-any-database if this really is a demo database."
        )

    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )
        existing = {row[0] for row in cur.fetchall()}

    clash = existing & APPLICATION_TABLES
    if clash:
        raise SystemExit(
            f"Refusing to seed {database_name!r}: it holds application tables "
            f"{sorted(clash)}. That is the app's own database - never touch it."
        )


def read_source(
    path: Path,
) -> Tuple[
    List[Tuple[Any, ...]],
    List[Tuple[Any, ...]],
    List[Tuple[Any, ...]],
    List[Tuple[Any, ...]],
    Dict[str, Any],
]:
    """Read the source CSV and shape it into the four demo tables.

    Returns the rows for each table plus a small report of what the data
    looked like, so the caller can print an honest summary.
    """
    if not path.exists():
        raise SystemExit(f"Source CSV not found: {path}")

    customers: Dict[int, Dict[str, Any]] = {}
    products: Dict[str, Dict[str, Any]] = {}
    orders: List[Tuple[Any, ...]] = []
    items: List[Tuple[Any, ...]] = []

    rounding_differences = 0
    rows_read = 0

    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows_read += 1
            customer_id = int(row["customer_id"])
            sku = row["product_sku"]
            ordered_at = row["ordered_at"]

            quantity = int(row["quantity"])
            unit_price = Decimal(row["unit_price"])
            discount = Decimal(row["discount_pct"])
            shipping = Decimal(row["shipping_cost"])
            order_total = Decimal(row["order_total"])
            refund = Decimal(row["refund_amount"])

            # The source data's own total is the authority: the line total
            # is derived from it, so "line_total + shipping_cost" equals
            # "order_total" for every single row.
            line_total = money(order_total - shipping)

            # Reported, not corrected: a few hundred rows in the source
            # data rounded the discount differently than the others.
            recomputed = money(unit_price * quantity * (Decimal(1) - discount))
            if recomputed != line_total:
                rounding_differences += 1

            days_to_deliver = row["days_to_deliver"].strip()
            deliver_days = int(days_to_deliver) if days_to_deliver else None

            orders.append(
                (
                    int(row["order_id"]),
                    ordered_at,
                    customer_id,
                    row["channel"],
                    row["device"],
                    row["currency"],
                    row["payment_method"],
                    row["status"],
                    str(order_total),
                    str(shipping),
                    "true" if row["is_first_order"].lower() == "true" else "false",
                    deliver_days,
                )
            )

            items.append(
                (
                    int(row["order_id"]),
                    sku,
                    quantity,
                    str(unit_price),
                    str(discount),
                    str(line_total),
                    str(refund),
                )
            )

            existing = customers.get(customer_id)
            if existing is None:
                customers[customer_id] = {
                    "email": row["customer_email"],
                    "country": row["country"],
                    "channel": row["channel"],
                    "first_order_at": ordered_at,
                }
            elif ordered_at < existing["first_order_at"]:
                # The acquisition channel is the one of the customer's
                # earliest order - that is how they found the shop.
                existing["channel"] = row["channel"]
                existing["first_order_at"] = ordered_at

            product = products.get(sku)
            if product is None:
                products[sku] = {"category": row["product_category"], "prices": [unit_price]}
            else:
                product["prices"].append(unit_price)

    report = {
        "rows_read": rows_read,
        "rounding_differences": rounding_differences,
    }
    return (
        [
            (cid, data["email"], data["country"], data["channel"], data["first_order_at"])
            for cid, data in customers.items()
        ],
        [
            (sku, data["category"], str(money(statistics.median(data["prices"]))))
            for sku, data in products.items()
        ],
        orders,
        items,
        report,
    )


def insert_rows(conn, table: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    """Insert rows in bulk.

    ``execute_values`` builds one multi-row INSERT per page, which is
    dramatically faster than 50,000 individual INSERTs. psycopg2's
    ``copy_expert`` would be faster still, but it only reads real files -
    an in-memory buffer is silently treated as empty, which loads nothing
    at all without raising an error.
    """
    column_list = ", ".join(columns)
    statement = f"INSERT INTO {table} ({column_list}) VALUES %s"
    with conn.cursor() as cur:
        execute_values(cur, statement, rows, page_size=1000)


def create_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()


def ensure_reader_role(conn, password: str) -> None:
    """Create (or update) the read-only role and grant it SELECT only."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (READER_ROLE,))
        exists = cur.fetchone() is not None

        statement = (
            "ALTER ROLE {} LOGIN PASSWORD {}" if exists else "CREATE ROLE {} LOGIN PASSWORD {}"
        )
        cur.execute(
            sql.SQL(statement).format(
                sql.Identifier(READER_ROLE),
                sql.Literal(password),
            )
        )
        cur.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(READER_ROLE))
        )
        cur.execute(
            sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(
                sql.Identifier(READER_ROLE)
            )
        )
        cur.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {}"
            ).format(sql.Identifier(READER_ROLE))
        )
    conn.commit()


def print_summary(conn, report: Dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM customers")
        customers = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM products")
        products = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM orders")
        orders = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM order_items")
        items = cur.fetchone()[0]

        cur.execute("SELECT sum(order_total) FROM orders")
        revenue = cur.fetchone()[0]

        cur.execute("SELECT status, count(*) FROM orders GROUP BY status ORDER BY 2 DESC")
        by_status = cur.fetchall()

        cur.execute(
            "SELECT p.category, count(*), round(sum(i.line_total), 2) "
            "FROM order_items i JOIN products p ON p.sku = i.sku "
            "GROUP BY p.category ORDER BY 3 DESC"
        )
        by_category = cur.fetchall()

        cur.execute("SELECT min(ordered_at), max(ordered_at) FROM orders")
        first, last = cur.fetchone()

    print()
    print("  tables")
    print(f"    customers  {customers:>8,}")
    print(f"    products   {products:>8,}")
    print(f"    orders     {orders:>8,}")
    print(f"    order_items{items:>9,}")
    print()
    print(f"  revenue        {revenue:>12,}")
    print(f"  date range     {first}  ->  {last}")
    print()
    print("  orders by status")
    for status, count in by_status:
        print(f"    {status:<12} {count:>8,}")
    print()
    print("  revenue by category")
    for category, count, amount in by_category:
        print(f"    {category:<12} {count:>8,} orders   {amount:>12,}")
    print()
    if report["rounding_differences"]:
        print(
            f"  note: {report['rounding_differences']} rows "
            f"({report['rounding_differences'] / report['rows_read']:.1%}) inherited a "
            "different rounding of the discount from the source data. The stored "
            "totals are exact."
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    url = resolve_url(args)

    database_name = urlparse(url).path.lstrip("/")
    if not database_name:
        raise SystemExit(f"Could not read a database name from {url!r}")

    print(f"Target database: {database_name}")

    conn = psycopg2.connect(url)
    try:
        assert_safe_target(conn, database_name, args.allow_any_database)

        print(f"Reading {args.csv} ...")
        customers, products, orders, items, report = read_source(Path(args.csv))
        print(f"  {report['rows_read']:,} source rows")

        print("Creating schema ...")
        create_schema(conn)

        print("Loading data ...")
        insert_rows(
            conn,
            "customers",
            ("customer_id", "email", "country", "acquisition_channel", "first_order_at"),
            customers,
        )
        insert_rows(conn, "products", ("sku", "category", "list_price"), products)
        insert_rows(
            conn,
            "orders",
            (
                "order_id",
                "ordered_at",
                "customer_id",
                "channel",
                "device",
                "currency",
                "payment_method",
                "status",
                "order_total",
                "shipping_cost",
                "is_first_order",
                "days_to_deliver",
            ),
            orders,
        )
        insert_rows(
            conn,
            "order_items",
            (
                "order_id",
                "sku",
                "quantity",
                "unit_price",
                "discount_pct",
                "line_total",
                "refund_amount",
            ),
            items,
        )
        conn.commit()

        if args.skip_reader_role:
            print("\nSkipped the read-only role (--skip-reader-role).")
        else:
            password = args.reader_password or secrets.token_urlsafe(16)
            ensure_reader_role(conn, password)
            print(f"\nRead-only role {READER_ROLE!r} ready.")
            if not args.reader_password:
                print(f"  password: {password}")
                print("  (generated - set DEMO_DB_READER_PASSWORD to choose it)")

        print_summary(conn, report)
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
