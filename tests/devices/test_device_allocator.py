from eos.resource_allocation.exceptions import (
    EosDeviceAllocatedError,
    EosDeviceNotFoundError,
)
from tests.fixtures import *

LAB_ID = "small_lab"


@pytest.mark.parametrize("setup_lab_experiment", [(LAB_ID, "water_purification")], indirect=True)
class TestDeviceAllocator:
    @pytest.mark.asyncio
    async def test_allocate_device(self, db, device_allocation_manager):
        device_id = "magnetic_mixer"
        await device_allocation_manager.allocate(db, LAB_ID, device_id, "owner", "water_purification_1")

        allocation = await device_allocation_manager.get_allocation(db, LAB_ID, device_id)

        assert allocation.id == device_id
        assert allocation.lab_id == LAB_ID
        assert allocation.device_type == "magnetic_mixer"
        assert allocation.owner == "owner"
        assert allocation.experiment_id == "water_purification_1"

    @pytest.mark.asyncio
    async def test_allocate_device_already_allocated(self, db, device_allocation_manager):
        device_id = "magnetic_mixer"
        await device_allocation_manager.allocate(db, LAB_ID, device_id, "owner", "water_purification_1")

        with pytest.raises(EosDeviceAllocatedError):
            await device_allocation_manager.allocate(db, LAB_ID, device_id, "owner", "water_purification_1")

    @pytest.mark.asyncio
    async def test_allocate_nonexistent_device(self, db, device_allocation_manager):
        device_id = "nonexistent_device_id"
        with pytest.raises(EosDeviceNotFoundError):
            await device_allocation_manager.allocate(db, LAB_ID, device_id, "owner", "water_purification_1")

    @pytest.mark.asyncio
    async def test_deallocate_device(self, db, device_allocation_manager):
        device_id = "magnetic_mixer"
        await device_allocation_manager.allocate(db, LAB_ID, device_id, "owner", "water_purification_1")

        await device_allocation_manager.deallocate(db, LAB_ID, device_id)
        allocation = await device_allocation_manager.get_allocation(db, LAB_ID, device_id)

        assert allocation is None

    @pytest.mark.asyncio
    async def test_deallocate_device_not_allocated(self, db, device_allocation_manager):
        device_id = "magnetic_mixer"
        await device_allocation_manager.deallocate(db, LAB_ID, device_id)
        assert await device_allocation_manager.get_allocation(db, LAB_ID, device_id) is None

    @pytest.mark.asyncio
    async def test_is_allocated(self, db, device_allocation_manager):
        device_id = "magnetic_mixer"
        assert not await device_allocation_manager.is_allocated(db, LAB_ID, device_id)

        await device_allocation_manager.allocate(db, LAB_ID, device_id, "owner", "water_purification_1")
        assert await device_allocation_manager.is_allocated(db, LAB_ID, device_id)

    @pytest.mark.asyncio
    async def test_get_allocations_by_owner(self, db, device_allocation_manager):
        device_id_1 = "magnetic_mixer"
        device_id_2 = "evaporator"
        device_id_3 = "substance_fridge"

        await device_allocation_manager.allocate(db, LAB_ID, device_id_1, "owner1", "water_purification_1")
        await device_allocation_manager.allocate(db, LAB_ID, device_id_2, "owner1", "water_purification_1")
        await device_allocation_manager.allocate(db, LAB_ID, device_id_3, "owner2", "water_purification_1")

        allocations = await device_allocation_manager.get_allocations(db, owner="owner1")

        assert len(allocations) == 2
        assert device_id_1 in [allocation.id for allocation in allocations]
        assert device_id_2 in [allocation.id for allocation in allocations]

    @pytest.mark.asyncio
    async def test_get_all_allocations(self, db, device_allocation_manager):
        device_id_1 = "magnetic_mixer"
        device_id_2 = "evaporator"
        device_id_3 = "substance_fridge"

        await device_allocation_manager.allocate(db, LAB_ID, device_id_1, "owner", "water_purification_1")
        await device_allocation_manager.allocate(db, LAB_ID, device_id_2, "owner", "water_purification_1")
        await device_allocation_manager.allocate(db, LAB_ID, device_id_3, "owner", "water_purification_1")

        allocations = await device_allocation_manager.get_allocations(db)

        assert len(allocations) == 3
        assert device_id_1 in [allocation.id for allocation in allocations]
        assert device_id_2 in [allocation.id for allocation in allocations]
        assert device_id_3 in [allocation.id for allocation in allocations]

    @pytest.mark.asyncio
    async def test_get_all_unallocated(self, db, device_allocation_manager):
        device_id_1 = "magnetic_mixer"
        device_id_2 = "evaporator"
        device_id_3 = "substance_fridge"

        initial_unallocated_devices = await device_allocation_manager.get_all_unallocated(db)

        await device_allocation_manager.allocate(db, LAB_ID, device_id_1, "owner", "water_purification_1")
        await device_allocation_manager.allocate(db, LAB_ID, device_id_2, "owner", "water_purification_1")

        new_unallocated_devices = await device_allocation_manager.get_all_unallocated(db)

        assert len(new_unallocated_devices) == len(initial_unallocated_devices) - 2
        assert device_id_1 not in new_unallocated_devices
        assert device_id_2 not in new_unallocated_devices
        assert device_id_3 in new_unallocated_devices

    @pytest.mark.asyncio
    async def test_deallocate_all(self, db, device_allocation_manager):
        device_id_1 = "magnetic_mixer"
        device_id_2 = "evaporator"
        device_id_3 = "substance_fridge"

        await device_allocation_manager.allocate(db, LAB_ID, device_id_1, "owner", "water_purification_1")
        await device_allocation_manager.allocate(db, LAB_ID, device_id_2, "owner", "water_purification_1")
        await device_allocation_manager.allocate(db, LAB_ID, device_id_3, "owner", "water_purification_1")

        assert await device_allocation_manager.get_allocations(db) != []

        await device_allocation_manager.deallocate_all(db)

        assert await device_allocation_manager.get_allocations(db) == []

    @pytest.mark.asyncio
    async def test_deallocate_all_by_owner(self, db, device_allocation_manager):
        device_id_1 = "magnetic_mixer"
        device_id_2 = "evaporator"
        device_id_3 = "substance_fridge"

        await device_allocation_manager.allocate(db, LAB_ID, device_id_1, "owner1", "water_purification_1")
        await device_allocation_manager.allocate(db, LAB_ID, device_id_2, "owner2", "water_purification_1")
        await device_allocation_manager.allocate(db, LAB_ID, device_id_3, "owner2", "water_purification_1")

        await device_allocation_manager.deallocate_all_by_owner(db, "owner2")

        owner2_allocations = await device_allocation_manager.get_allocations(db, owner="owner2")
        assert owner2_allocations == []
        assert await device_allocation_manager.get_allocations(db) == [
            await device_allocation_manager.get_allocation(db, LAB_ID, device_id_1)
        ]
