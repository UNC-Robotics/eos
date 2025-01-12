from abc import ABC, abstractmethod
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine, Engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase
from eos.configuration.entities.eos_config import DbConfig
from eos.logging.logger import log


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models"""


DbSession = Session
AsyncDbSession = AsyncSession


class AbstractSqlDbInterface(ABC):
    """Abstract base class for SQL database interfaces."""

    def __init__(self, db_config: DbConfig):
        """Initialize database interface with configuration."""
        self._db_config = db_config
        self._db_name = db_config.db_name

        self._sync_engine = self._create_sync_engine()
        self._async_engine = self._create_async_engine()
        self._sync_session_factory = self._create_sync_session_factory()
        self._async_session_factory = self._create_async_session_factory()

        log.debug(f"Database interface initialized for database '{self._db_name}'")

    @abstractmethod
    def _get_connection_args(self) -> dict:
        """Get database connection pool arguments."""

    @abstractmethod
    def build_db_url(self, use_system_db: bool = False) -> str:
        """Build database connection URL."""

    @abstractmethod
    def build_async_db_url(self, use_system_db: bool = False) -> str:
        """Build async database connection URL."""

    @abstractmethod
    async def _create_database(self) -> None:
        """Create database if it doesn't exist."""

    @abstractmethod
    async def _drop_database(self) -> None:
        """Drop the database if it exists."""

    def _create_sync_engine(self) -> Engine:
        """Create synchronous database engine."""
        return create_engine(
            self.build_db_url(), echo=self._db_config.echo, pool_pre_ping=True, **self._get_connection_args()
        )

    def _create_async_engine(self) -> AsyncEngine:
        """Create asynchronous database engine."""
        return create_async_engine(
            self.build_async_db_url(), echo=self._db_config.echo, pool_pre_ping=True, **self._get_connection_args()
        )

    def _create_sync_session_factory(self) -> sessionmaker:
        """Create synchronous session factory."""
        return sessionmaker(
            self._sync_engine,
            class_=Session,
            expire_on_commit=False,
        )

    def _create_async_session_factory(self) -> async_sessionmaker:
        """Create asynchronous session factory."""
        return async_sessionmaker(
            self._async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def initialize_database(self) -> None:
        """Initialize database and create all tables."""
        try:
            exists = await self._database_exists()
            if not exists:
                await self._create_database()

            # Create tables if they don't exist
            async with self._async_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception as e:
            log.error(f"Failed to initialize database: {e!s}")
            raise

    async def clear_db(self) -> None:
        """Clean all tables in the database by deleting their contents using a session."""
        async with self.get_async_session() as session:
            try:
                for table in reversed(Base.metadata.sorted_tables):
                    await session.execute(table.delete())
                log.debug("Cleared DB")
            except Exception as e:
                log.error(f"Failed to clear DB: {e!s}")
                raise

    @abstractmethod
    async def _database_exists(self) -> bool:
        """Check if database exists."""

    @contextmanager
    def get_session(self) -> DbSession:
        """Get a synchronous database session with automatic cleanup and rollback on error."""
        session = self._sync_session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @asynccontextmanager
    async def get_async_session(self) -> AsyncDbSession:
        """Get an asynchronous database session with automatic cleanup and rollback on error."""
        session = self._async_session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def check_connection(self) -> bool:
        """Test database connection and return True if successful."""
        try:
            async with self._async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            log.error(f"Database connection check failed: {e!s}")
            return False

    async def close(self) -> None:
        """Close all database connections."""
        await self._async_engine.dispose()
        self._sync_engine.dispose()
        log.debug("Closed all database connections")

    @property
    def sync_engine(self) -> Engine:
        """Get the synchronous database engine."""
        return self._sync_engine

    @property
    def async_engine(self) -> AsyncEngine:
        """Get the asynchronous database engine."""
        return self._async_engine
