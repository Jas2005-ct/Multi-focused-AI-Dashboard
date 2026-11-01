import logging
import os

from alembic import context
from alembic.config import Config

# Load the Alembic configuration from the ini file
config = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))

# Logging setup disabled to avoid config parser errors.
logger = logging.getLogger("alembic.env")


def get_engine():
    from sqlalchemy import create_engine

    url = config.get_main_option("sqlalchemy.url")
    return create_engine(url)


def get_engine_url():
    # Use the config's SQLAlchemy URL
    return config.get_main_option("sqlalchemy.url")


def get_metadata():
    if hasattr(config, "target_metadata"):
        return config.target_metadata
    return None


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=get_metadata(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = get_engine()
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            process_revision_directives=config.get_main_option("process_revision_directives")
            or "True",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
