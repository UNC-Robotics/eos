import asyncio
from functools import partial

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    create_async_engine,
)
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AbstractSqlDbInterface, Base
from eos.database.alembic_commands import alembic_upgrade, alembic_downgrade


class PostgresqlDbInterface(AbstractSqlDbInterface):
    """PostgreSQL-specific database interface implementation.

    :param db_config: Database configuration object
    :type db_config: DbConfig
    """

    def _get_connection_args(self) -> dict:
        """Get connection pool arguments for PostgreSQL.

        :returns: Dictionary of connection arguments
        :rtype: dict
        """
        return {
            "pool_size": self._db_config.pool_size,
            "max_overflow": self._db_config.max_overflow,
            "pool_timeout": self._db_config.pool_timeout,
        }

    def build_db_url(self, use_system_db: bool = False) -> str:
        """Build synchronous database URL.

        :param use_system_db: Whether to connect to postgres system database
        :type use_system_db: bool
        :returns: Database URL string
        :rtype: str
        """
        db = "postgres" if use_system_db else self._db_name
        return (
            f"postgresql+psycopg://{self._db_config.username}:{self._db_config.password}"
            f"@{self._db_config.host}:{self._db_config.port}/{db}"
        )

    def build_async_db_url(self, use_system_db: bool = False) -> str:
        """Build asynchronous database URL.

        :param use_system_db: Whether to connect to postgres system database
        :type use_system_db: bool
        :returns: Database URL string
        :rtype: str
        """
        db = "postgres" if use_system_db else self._db_name
        return (
            f"postgresql+asyncpg://{self._db_config.username}:{self._db_config.password}"
            f"@{self._db_config.host}:{self._db_config.port}/{db}"
        )

    async def initialize_database(self) -> None:
        """Initialize database by creating it if needed and running migrations.

        :raises Exception: If initialization fails
        """
        try:
            exists = await self._database_exists()
            if not exists:
                await self._create_database()

            await self.run_migrations()

            # Create tables if they don't exist
            async with self._async_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        except Exception as e:
            log.error(f"Failed to initialize database: {e!s}")
            raise

    async def _database_exists(self) -> bool:
        """Check if PostgreSQL database exists.

        :returns: True if database exists, False otherwise
        :rtype: bool
        """
        system_engine = create_async_engine(self.build_async_db_url(use_system_db=True), isolation_level="AUTOCOMMIT")

        try:
            async with system_engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :db_name").bindparams(db_name=self._db_name)
                )
                return result.scalar() is not None
        finally:
            await system_engine.dispose()

    async def _create_database(self) -> None:
        """Create PostgreSQL database if it doesn't exist.

        :raises Exception: If database creation fails
        """
        system_engine = create_async_engine(self.build_async_db_url(use_system_db=True), isolation_level="AUTOCOMMIT")

        try:
            async with system_engine.connect() as conn:
                await conn.execute(text(f"CREATE DATABASE {self._db_name} ENCODING 'UTF8'"))
                log.info(f"Created PostgreSQL database '{self._db_name}'")
        finally:
            await system_engine.dispose()

    async def _drop_database(self) -> None:
        """Drop the PostgreSQL database if it exists.

        :raises Exception: If database drop fails
        """
        system_engine = create_async_engine(self.build_async_db_url(use_system_db=True), isolation_level="AUTOCOMMIT")

        try:
            async with system_engine.connect() as conn:
                await conn.execute(
                    text(
                        """
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = :db_name AND pid != pg_backend_pid()
                        """
                    ).bindparams(db_name=self._db_name)
                )
                await conn.execute(text(f"DROP DATABASE IF EXISTS {self._db_name}"))
                log.info(f"Dropped PostgreSQL database '{self._db_name}'")
        finally:
            await system_engine.dispose()

    async def run_migrations(self) -> None:
        """Run any pending database migrations."""
        try:
            await asyncio.to_thread(alembic_upgrade)
        except Exception as e:
            log.error(f"Failed to run migrations: {e!s}")
            raise

    async def downgrade_migrations(self, revision: str = "-1") -> None:
        """Downgrade database schema to a specific revision.

        :param revision: Target revision to downgrade to, defaults to "-1"
        :type revision: str
        :raises Exception: If downgrade fails
        """
        try:
            await asyncio.to_thread(partial(alembic_downgrade, revision=revision))
            log.info(f"Database downgraded to revision: {revision}")
        except Exception as e:
            log.error(f"Failed to downgrade migrations: {e!s}")
            raise
