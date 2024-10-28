from typing import Any

from motor.core import AgnosticClientSession
from pymongo.results import DeleteResult, UpdateResult, InsertOneResult

from eos.persistence.abstract_async_repository import AbstractAsyncRepository
from eos.persistence.async_mongodb_interface import AsyncMongoDbInterface


class MongoDbAsyncRepository(AbstractAsyncRepository):
    """
    Provides CRUD operations for a MongoDB collection.
    """

    def __init__(self, collection_name: str, db_interface: AsyncMongoDbInterface):
        self._collection = db_interface.get_db().get_collection(collection_name)

    async def create_indices(self, indices: list[tuple[str, int]], unique: bool = False) -> None:
        """
        Create indices on the collection synchronously.

        :param indices: List of tuples of field names and order (1 for ascending, -1 for descending).
        :param unique: Whether the index should be unique.
        """
        index_name = "_".join(f"{field}_{order}" for field, order in indices)

        if index_name not in await self._collection.index_information():
            await self._collection.create_index(indices, unique=unique, name=index_name)

    async def create(self, entity: dict[str, Any], session: AgnosticClientSession | None = None) -> InsertOneResult:
        """
        Create a new entity in the collection.

        :param entity: The entity to create.
        :param session: The optional session to use for the operation.
        :return: The result of the insert operation.
        """
        return await self._collection.insert_one(entity, session=session)

    async def count(self, session: AgnosticClientSession | None = None, **kwargs) -> int:
        """
        Count the number of entities that match the query in the collection.

        :param session: The optional session to use for the operation.
        :param kwargs: Query parameters.
        :return: The number of entities.
        """
        return await self._collection.count_documents(session=session, filter=kwargs)

    async def exists(self, session: AgnosticClientSession | None = None, **kwargs) -> bool:
        """
        Check if an entity exists in the collection.

        :param session: The optional session to use for the operation.
        :param kwargs: Query parameters.
        :return: Whether the entity exists.
        """
        return await self._collection.find_one(kwargs, {"_id": 1}, session=session) is not None

    async def get_one(self, session: AgnosticClientSession | None = None, **kwargs) -> dict[str, Any]:
        """
        Get a single entity from the collection.

        :param session: The optional session to use for the operation.
        :param kwargs: Query parameters.
        :return: The entity as a dictionary.
        """
        return await self._collection.find_one(kwargs, session=session)

    async def get_all(self, session: AgnosticClientSession | None = None, **kwargs) -> list[dict[str, Any]]:
        """
        Get all entities from the collection, optionally filtered by query parameters.

        :param session: The optional session to use for the operation.
        :param kwargs: Query parameters.
        :return: List of entities as dictionaries.
        """
        return await self._collection.find(kwargs, session=session).to_list(None)

    async def update_one(
        self, updated_entity: dict[str, Any], session: AgnosticClientSession | None = None, **kwargs
    ) -> UpdateResult:
        """
        Update an entity in the collection.

        :param updated_entity: The updated entity (or some of its fields).
        :param session: The optional session to use for the operation.
        :param kwargs: Query parameters.
        :return: The result of the update operation.
        """
        return await self._collection.update_one(kwargs, {"$set": updated_entity}, upsert=True, session=session)

    async def delete_one(self, session: AgnosticClientSession | None = None, **kwargs) -> DeleteResult:
        """
        Delete an entity from the collection, optionally filtered by query parameters.

        :param session: The optional session to use for the operation.
        :param kwargs: Query parameters.
        :return: The result of the delete operation.
        """
        return await self._collection.delete_one(kwargs, session=session)

    async def delete_many(self, session: AgnosticClientSession | None = None, **kwargs) -> DeleteResult:
        """
        Delete multiple entities from the collection, optionally filtered by query parameters.

        :param session: The optional session to use for the operation.
        :param kwargs: Query parameters.
        :return: The result of the delete operation.
        """
        return await self._collection.delete_many(kwargs, session=session)

    async def delete_all(self, session: AgnosticClientSession | None = None) -> DeleteResult:
        """
        Delete all entities from the collection.

        :param session: The optional session to use for the operation.
        :return: The result of the delete operation.
        """
        return await self._collection.delete_many({}, session=session)
