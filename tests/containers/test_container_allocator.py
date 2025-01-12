from eos.resource_allocation.exceptions import (
    EosContainerAllocatedError,
    EosContainerNotFoundError,
)
from tests.fixtures import *


@pytest.mark.parametrize("setup_lab_experiment", [("small_lab", "water_purification")], indirect=True)
class TestContainerAllocator:
    @pytest.mark.asyncio
    async def test_allocate_container(self, db, container_allocation_manager):
        container_id = "ec1ca48cd5d14c0c8cde376476e0d98d"
        await container_allocation_manager.allocate(db, container_id, "owner", "water_purification_1")
        container = await container_allocation_manager.get_allocation(db, container_id)

        assert container.id == container_id
        assert container.owner == "owner"
        assert container.experiment_id == "water_purification_1"

    @pytest.mark.asyncio
    async def test_allocate_container_already_allocated(self, db, container_allocation_manager):
        container_id = "ec1ca48cd5d14c0c8cde376476e0d98d"
        await container_allocation_manager.allocate(db, container_id, "owner", "water_purification_1")

        with pytest.raises(EosContainerAllocatedError):
            await container_allocation_manager.allocate(db, container_id, "owner", "water_purification_1")

    @pytest.mark.asyncio
    async def test_allocate_nonexistent_container(self, db, container_allocation_manager):
        container_id = "nonexistent_container_id"
        with pytest.raises(EosContainerNotFoundError):
            await container_allocation_manager.allocate(db, container_id, "owner", "water_purification_1")

    @pytest.mark.asyncio
    async def test_deallocate_container(self, db, container_allocation_manager):
        container_id = "ec1ca48cd5d14c0c8cde376476e0d98d"
        await container_allocation_manager.allocate(db, container_id, "owner", "water_purification_1")

        await container_allocation_manager.deallocate(db, container_id)
        container = await container_allocation_manager.get_allocation(db, container_id)

        assert container is None

    @pytest.mark.asyncio
    async def test_deallocate_container_not_allocated(self, db, container_allocation_manager):
        container_id = "ec1ca48cd5d14c0c8cde376476e0d98d"
        await container_allocation_manager.deallocate(db, container_id)

        allocation = await container_allocation_manager.get_allocation(db, container_id)
        assert allocation is None

    @pytest.mark.asyncio
    async def test_is_allocated(self, db, container_allocation_manager):
        container_id = "ec1ca48cd5d14c0c8cde376476e0d98d"
        assert not await container_allocation_manager.is_allocated(db, container_id)

        await container_allocation_manager.allocate(db, container_id, "owner", "water_purification_1")
        assert await container_allocation_manager.is_allocated(db, container_id)

    @pytest.mark.asyncio
    async def test_get_allocations_by_owner(self, db, container_allocation_manager):
        container_id_1 = "ec1ca48cd5d14c0c8cde376476e0d98d"
        container_id_2 = "84eb17d61e884ffd9d1fdebcbad1532b"
        container_id_3 = "a3b958aea8bd435386cdcbab20a2d3ec"

        await container_allocation_manager.allocate(db, container_id_1, "owner", "water_purification_1")
        await container_allocation_manager.allocate(db, container_id_2, "owner", "water_purification_1")
        await container_allocation_manager.allocate(db, container_id_3, "another_owner", "water_purification_1")

        allocations = await container_allocation_manager.get_allocations(db, owner="owner")
        assert allocations[0].id == container_id_1
        assert allocations[1].id == container_id_2
        assert len(allocations) == 2

        allocations = await container_allocation_manager.get_allocations(db, owner="another_owner")
        assert allocations[0].id == container_id_3
        assert len(allocations) == 1

    @pytest.mark.asyncio
    async def test_get_all_allocations(self, db, container_allocation_manager):
        container_id_1 = "ec1ca48cd5d14c0c8cde376476e0d98d"
        container_id_2 = "84eb17d61e884ffd9d1fdebcbad1532b"
        container_id_3 = "a3b958aea8bd435386cdcbab20a2d3ec"

        await container_allocation_manager.allocate(db, container_id_1, "owner", "water_purification_1")
        await container_allocation_manager.allocate(db, container_id_2, "owner", "water_purification_1")
        await container_allocation_manager.allocate(db, container_id_3, "another_owner", "water_purification_1")

        allocations = await container_allocation_manager.get_allocations(db)
        assert len(allocations) == 3
        assert {allocation.id for allocation in allocations} == {
            container_id_1,
            container_id_2,
            container_id_3,
        }

    @pytest.mark.asyncio
    async def test_get_all_unallocated_containers(self, db, container_allocation_manager):
        container_id_1 = "ec1ca48cd5d14c0c8cde376476e0d98d"
        container_id_2 = "84eb17d61e884ffd9d1fdebcbad1532b"
        container_id_3 = "a3b958aea8bd435386cdcbab20a2d3ec"

        initial_unallocated_containers = await container_allocation_manager.get_all_unallocated(db)

        await container_allocation_manager.allocate(db, container_id_1, "owner1", "water_purification_1")
        await container_allocation_manager.allocate(db, container_id_2, "owner2", "water_purification_1")

        new_unallocated_containers = await container_allocation_manager.get_all_unallocated(db)
        assert len(new_unallocated_containers) == len(initial_unallocated_containers) - 2
        assert container_id_1 not in new_unallocated_containers
        assert container_id_2 not in new_unallocated_containers
        assert container_id_3 in new_unallocated_containers

    @pytest.mark.asyncio
    async def test_deallocate_all_containers(self, db, container_allocation_manager):
        container_id_1 = "ec1ca48cd5d14c0c8cde376476e0d98d"
        container_id_2 = "84eb17d61e884ffd9d1fdebcbad1532b"
        container_id_3 = "a3b958aea8bd435386cdcbab20a2d3ec"

        await container_allocation_manager.allocate(db, container_id_1, "owner1", "water_purification_1")
        await container_allocation_manager.allocate(db, container_id_2, "owner2", "water_purification_1")
        await container_allocation_manager.allocate(db, container_id_3, "owner3", "water_purification_1")

        assert await container_allocation_manager.get_allocations(db) != []

        await container_allocation_manager.deallocate_all(db)

        assert await container_allocation_manager.get_allocations(db) == []

    @pytest.mark.asyncio
    async def test_deallocate_all_containers_by_owner(self, db, container_allocation_manager):
        container_id_1 = "ec1ca48cd5d14c0c8cde376476e0d98d"
        container_id_2 = "84eb17d61e884ffd9d1fdebcbad1532b"
        container_id_3 = "a3b958aea8bd435386cdcbab20a2d3ec"

        await container_allocation_manager.allocate(db, container_id_1, "owner1", "water_purification_1")
        await container_allocation_manager.allocate(db, container_id_2, "owner2", "water_purification_1")
        await container_allocation_manager.allocate(db, container_id_3, "owner2", "water_purification_1")

        await container_allocation_manager.deallocate_all_by_owner(db, "owner2")

        owner2_allocations = await container_allocation_manager.get_allocations(db, owner="owner2")
        assert owner2_allocations == []
        assert await container_allocation_manager.get_allocations(db) == [
            await container_allocation_manager.get_allocation(db, container_id_1)
        ]
