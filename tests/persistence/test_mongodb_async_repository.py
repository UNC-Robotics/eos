import asyncio

import pytest
from pymongo.errors import DuplicateKeyError

from eos.persistence.mongodb_async_repository import MongoDbAsyncRepository
from tests.fixtures import db_interface


class TestMongoDbAsyncRepository:
    @pytest.fixture(scope="class")
    def repository(self, db_interface):
        return MongoDbAsyncRepository("test_collection", db_interface)

    @pytest.mark.asyncio
    async def test_create_and_get_one(self, repository):
        entity = {"name": "Test Entity", "value": 42}
        result = await repository.create(entity)
        assert result.acknowledged

        retrieved = await repository.get_one(name="Test Entity")
        assert retrieved["name"] == "Test Entity"
        assert retrieved["value"] == 42

    @pytest.mark.asyncio
    async def test_update_one(self, repository):
        entity = {"name": "Update Test", "value": 10}
        await repository.create(entity)

        updated_entity = {"value": 20}
        result = await repository.update_one(updated_entity, name="Update Test")
        assert result.modified_count == 1

        retrieved = await repository.get_one(name="Update Test")
        assert retrieved["value"] == 20

    @pytest.mark.asyncio
    async def test_delete_one(self, repository):
        entity = {"name": "Delete Test", "value": 30}
        await repository.create(entity)

        result = await repository.delete_one(name="Delete Test")
        assert result.deleted_count == 1

        retrieved = await repository.get_one(name="Delete Test")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_get_all(self, repository):
        entities = [
            {"name": "Entity 1", "value": 1},
            {"name": "Entity 2", "value": 2},
            {"name": "Entity 3", "value": 3},
        ]
        await asyncio.gather(*[repository.create(entity) for entity in entities])

        retrieved = await repository.get_all()
        assert len(retrieved) >= 3
        assert all(entity["name"] in [e["name"] for e in retrieved] for entity in entities)

    @pytest.mark.asyncio
    async def test_count_and_exists(self, repository):
        await repository.delete_all()

        entities = [
            {"name": "Count 1", "value": 1},
            {"name": "Count 2", "value": 2},
        ]
        await asyncio.gather(*[repository.create(entity) for entity in entities])

        count = await repository.count()
        assert count == 2

    @pytest.mark.asyncio
    async def test_delete_many(self, repository):
        await repository.delete_all()

        entities = [
            {"name": "Delete Many 1", "value": 1},
            {"name": "Delete Many 2", "value": 2},
            {"name": "Keep", "value": 3},
        ]
        await asyncio.gather(*[repository.create(entity) for entity in entities])

        result = await repository.delete_many(name={"$regex": "Delete Many"})
        assert result.deleted_count == 2

        remaining = await repository.get_all()
        assert len(remaining) == 1
        assert remaining[0]["name"] == "Keep"

    @pytest.mark.asyncio
    async def test_create_indices(self, repository):
        indices = [("name", 1), ("value", -1)]
        await repository.create_indices(indices, unique=True)
        await repository.delete_all()

        # Verify that the index was created
        info = await repository._collection.index_information()
        assert "name_1_value_-1" in info

        # Test uniqueness constraint
        await repository.create({"name": "Unique Test", "value": 300})
        with pytest.raises(DuplicateKeyError):
            await repository.create({"name": "Unique Test", "value": 300})

    @pytest.mark.asyncio
    async def test_transaction_commit(self, repository, db_interface):
        await repository.delete_all()

        async with db_interface.session_factory() as session:
            entity = {"name": "Transaction Test", "value": 100}
            await repository.create(entity, session=session)
            await session.commit_transaction()

        retrieved = await repository.get_one(name="Transaction Test")
        assert retrieved is not None
        retrieved.pop("_id")
        assert retrieved == {"name": "Transaction Test", "value": 100}

    @pytest.mark.asyncio
    async def test_transaction_abort(self, repository, db_interface):
        try:
            async with db_interface.session_factory() as session:
                entity = {"name": "Abort Test", "value": 200}
                await repository.create(entity, session=session)
                raise Exception("Simulated error")
        except Exception:
            pass  # The transaction will be automatically aborted

        retrieved = await repository.get_one(name="Abort Test")
        assert retrieved is None
