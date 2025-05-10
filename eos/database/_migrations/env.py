"""Alembic environment configuration for database migrations."""

from alembic import context
from sqlalchemy import engine_from_config, pool

from eos.database.abstract_sql_db_interface import Base, AbstractSqlDbInterface
from eos.utils.di.di_container import get_di_container
from eos.logging.logger import log

# ruff: noqa: F401
import eos.database.models


def get_db_url() -> str:
    """Get the SQLAlchemy URL from the registered database interface."""
    db_interface = get_di_container().get(AbstractSqlDbInterface)
    return db_interface.build_db_url()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode without requiring a live database connection."""
    context.configure(
        url=get_db_url(),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a live database connection."""
    configuration = context.config.get_section(context.config.config_ini_section)
    configuration["sqlalchemy.url"] = get_db_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            info={"logger": log},
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
