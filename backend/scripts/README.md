# Demo database scripts

`seed_demo.py` loads the bundled synthetic e-commerce dataset into the
demo database (`DEMO_DB_URL`) and prepares the read-only access role.

## What it does

1. Resolves the target database from `--url` or the `DEMO_DB_URL`
   environment variable.
2. Runs two safety rails (it writes to a real server, so it refuses to
   be loose):
   - the database name must contain `demo`, unless
     `--allow-any-database` is passed;
   - it refuses to run against a database holding the application's own
     tables (`users`, `refresh_tokens`, `db_connections`).
3. Drops and recreates the four demo tables and loads the data:
   - `customers` — 12,854 rows
   - `products` — 1,440 rows
   - `orders` — 50,000 rows
   - `order_items` — 50,000 rows
4. Creates (or updates) the read-only `demo_reader` role with SELECT
   grants, plus `ALTER DEFAULT PRIVILEGES` for future tables.

## Usage

```bash
cd backend

# against the local server (DEMO_DB_URL is already set in .env)
python scripts/seed_demo.py --reader-password "demo_reader_local"

# against a specific database
python scripts/seed_demo.py --url postgresql://user:pass@host:5432/demo_ai_db
```

The script is idempotent - it drops and recreates the demo tables, so it
is safe to re-run to refresh the data.

## Safety notes

- The demo database is a **separate** database from the application's
  own; it holds nothing but sample data.
- The read-only role is enforced by the database itself: the demo
  database refuses INSERT / UPDATE / DELETE / CREATE / DROP even if the
  application asked for it.
- A socket-level guard in the test suite (see `tests/db_guard.py`) and
  the hermetic fixture (see `tests/conftest.py`) keep the suite away from
  real databases. CI has no Postgres server, so the seed script is
  manual-only - it is not part of the test suite.
