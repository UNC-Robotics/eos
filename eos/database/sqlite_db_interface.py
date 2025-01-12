from eos.configuration.entities.eos_config import DbConfig

from pathlib import Path
import sqlite3
from sqlite3 import Connection

from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AbstractSqlDbInterface


class SqliteDbInterface(AbstractSqlDbInterface):
    """SQLite-specific database interface implementation."""

    DB_FILE_EXTENSION = ".db"
    IN_MEMORY_PATH = ":memory:"

    def __init__(self, db_config: DbConfig):
        """Initialize database interface with configuration."""
        self._is_in_memory = db_config.sqlite_in_memory
        super().__init__(db_config)

    def _get_connection_args(self) -> dict:
        return {
            "connect_args": {
                "check_same_thread": False,  # Allow multi-threading
                "timeout": 30,  # Connection timeout in seconds
            },
            "creator": self._configure_connection,
        }

    def _configure_connection(self, _: any) -> Connection:
        """Configure SQLite connection with optimized settings and WAL mode.

        Args:
            _: Ignored connection record from SQLAlchemy pool

        Returns:
            Configured SQLite connection
        """
        conn = sqlite3.connect(self.IN_MEMORY_PATH if self._is_in_memory else str(self._get_db_path()))

        # Only use WAL mode for file-based databases
        if not self._is_in_memory:
            conn.execute("PRAGMA journal_mode=WAL")

        conn.execute("PRAGMA synchronous=NORMAL")  # Balance between safety and speed
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache size
        conn.execute("PRAGMA busy_timeout=60000")  # 60 second busy timeout

        return conn

    def _get_db_path(self) -> Path:
        """Construct the complete database file path."""
        if self._is_in_memory:
            return Path(self.IN_MEMORY_PATH)
        return (Path(self._db_config.sqlite_db_dir) / f"{self._db_name}{self.DB_FILE_EXTENSION}").resolve()

    def build_db_url(self, use_system_db: bool = False) -> str:
        """Build the synchronous database URL."""
        if self._is_in_memory:
            return "sqlite:///:memory:"
        return f"sqlite:///{self._get_db_path()}"

    def build_async_db_url(self, use_system_db: bool = False) -> str:
        """Build the asynchronous database URL."""
        if self._is_in_memory:
            return "sqlite+aiosqlite:///:memory:"
        return f"sqlite+aiosqlite:///{self._get_db_path()}"

    async def _create_database(self) -> None:
        if not self._is_in_memory:
            db_path = self._get_db_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_path.touch(exist_ok=True)
            log.debug(f"Ensured SQLite database exists at '{db_path.parent}'")
        else:
            log.debug("Using in-memory SQLite database")

    async def _drop_database(self) -> None:
        """Drop the SQLite database by deleting the file or clearing memory."""
        try:
            await self.close()

            if not self._is_in_memory:
                db_path = self._get_db_path()
                if db_path.exists():
                    db_path.unlink()
                    log.info(f"Deleted SQLite database file '{db_path}'")
            else:
                log.info("Dropped in-memory SQLite database")

        except Exception as e:
            log.error(f"Failed to drop SQLite database: {e!s}")
            raise

    async def _database_exists(self) -> bool:
        if self._is_in_memory:
            return False  # Always create tables for in-memory database
        db_path = Path(self._db_config.sqlite_db_dir) / Path(self._db_name + ".db")
        return db_path.exists()
