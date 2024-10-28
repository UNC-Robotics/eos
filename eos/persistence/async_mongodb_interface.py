from motor.core import AgnosticDatabase
from motor.motor_asyncio import AsyncIOMotorClient

from eos.configuration.entities.eos_config import DbConfig
from eos.logging.logger import log
from eos.persistence.async_mongodb_session_factory import AsyncMongoDbSessionFactory


class AsyncMongoDbInterface:
    """
    Gives asynchronous access to a MongoDB database.
    """

    def __init__(
        self,
        db_credentials: DbConfig,
        db_name: str = "eos",
    ):
        self._db_credentials = db_credentials

        self._db_client = AsyncIOMotorClient(
            f"mongodb://{self._db_credentials.username}:{self._db_credentials.password}"
            f"@{self._db_credentials.host}:{self._db_credentials.port}"
        )

        self._db: AgnosticDatabase = self._db_client[db_name]
        self.session_factory = AsyncMongoDbSessionFactory(self._db_client)

        log.debug(f"Async Db manager initialized with database '{db_name}'.")

    def get_db(self) -> AgnosticDatabase:
        """Get the database."""
        return self._db

    async def clean_db(self) -> None:
        """Clean the database."""
        collections = await self._db.list_collection_names()
        for collection in collections:
            await self._db[collection].drop()
