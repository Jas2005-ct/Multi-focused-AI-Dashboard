"""Which tables are hidden from the listings, the agent and generated SQL.

A single place decides whether a table is off-limits, so the listing, the
agent's tools and the SQL guard cannot drift apart. A table that is hidden
from the listing but still reachable through ``sample_rows`` or a raw
``SELECT`` would not really be hidden at all - the agent only has to guess
the name.

The lists come from the environment (see ``Settings``):

``IGNORED_TABLE_PREFIXES``
    Every table whose name starts with one of these prefixes is hidden -
    ``auth_`` hides ``auth_users``, ``django_`` hides ``django_migrations``.
``IGNORED_TABLES``
    The listed table names are hidden by exact name.

Matching is case-insensitive because the same table can be reported in
different cases by PostgreSQL and MySQL.
"""

from config import get_settings


def is_table_ignored(table_name: str) -> bool:
    """True when the table is hidden by the ignored-table policy."""
    if not table_name:
        return False

    # Strip quoting: the same table arrives as `users`, "users" or `users`.
    name = table_name.strip().strip('"').strip("`").lower()
    if not name:
        return False

    settings = get_settings()
    if name in settings.ignored_tables:
        return True
    return any(name.startswith(prefix) for prefix in settings.ignored_table_prefixes)


def visible_tables(table_names: list[str]) -> list[str]:
    """The subset of ``table_names`` that is not hidden by the policy."""
    return [name for name in table_names if not is_table_ignored(name)]


__all__ = ["is_table_ignored", "visible_tables"]
