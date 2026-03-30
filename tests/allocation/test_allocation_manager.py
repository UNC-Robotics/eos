from eos.allocation.exceptions import (
    EosDeviceNotFoundError,
    EosResourceNotFoundError,
)
from eos.allocation.entities.reservation import ReservationStatus
from tests.fixtures import *

LAB_ID = "small_lab"
DEVICE = ("small_lab", "magnetic_mixer")
DEVICE_2 = ("small_lab", "evaporator")


def _first_resource(configuration_manager):
    """Get the first resource name from the loaded lab."""
    lab = configuration_manager.labs[LAB_ID]
    return next(iter(lab.resources.keys()))


@pytest.mark.parametrize("setup_lab_protocol", [(LAB_ID, "water_purification")], indirect=True)
class TestAllocationManager:
    @pytest.mark.asyncio
    async def test_allocate_device(self, db, allocation_manager):
        await allocation_manager.allocate_devices(db, [DEVICE], "test_owner")
        assert allocation_manager.is_device_allocated(*DEVICE)
        alloc = allocation_manager.get_device_allocation(*DEVICE)
        assert alloc.owner == "test_owner"

    @pytest.mark.asyncio
    async def test_deallocate_device(self, db, allocation_manager):
        await allocation_manager.allocate_devices(db, [DEVICE], "test_owner")
        assert allocation_manager.is_device_allocated(*DEVICE)
        await allocation_manager.deallocate_devices(db, [DEVICE])
        assert not allocation_manager.is_device_allocated(*DEVICE)

    @pytest.mark.asyncio
    async def test_allocate_nonexistent_device(self, db, allocation_manager):
        with pytest.raises(EosDeviceNotFoundError):
            await allocation_manager.allocate_devices(db, [("nonexistent_lab", "dev")], "test_owner")

    @pytest.mark.asyncio
    async def test_allocate_resource(self, db, allocation_manager, configuration_manager):
        res_name = _first_resource(configuration_manager)
        await allocation_manager.allocate_resources(db, [res_name], "test_owner")
        assert allocation_manager.is_resource_allocated(res_name)
        alloc = allocation_manager.get_resource_allocation(res_name)
        assert alloc.owner == "test_owner"

    @pytest.mark.asyncio
    async def test_deallocate_resource(self, db, allocation_manager, configuration_manager):
        res_name = _first_resource(configuration_manager)
        await allocation_manager.allocate_resources(db, [res_name], "test_owner")
        assert allocation_manager.is_resource_allocated(res_name)
        await allocation_manager.deallocate_resources(db, [res_name])
        assert not allocation_manager.is_resource_allocated(res_name)

    @pytest.mark.asyncio
    async def test_allocate_nonexistent_resource(self, db, allocation_manager):
        with pytest.raises(EosResourceNotFoundError):
            await allocation_manager.allocate_resources(db, ["nonexistent"], "test_owner")

    @pytest.mark.asyncio
    async def test_get_unallocated_devices(self, db, allocation_manager):
        unallocated = allocation_manager.get_all_unallocated_devices()
        assert DEVICE in unallocated

        await allocation_manager.allocate_devices(db, [DEVICE], "test_owner")
        unallocated = allocation_manager.get_all_unallocated_devices()
        assert DEVICE not in unallocated

    @pytest.mark.asyncio
    async def test_get_unallocated_resources(self, db, allocation_manager, configuration_manager):
        res_name = _first_resource(configuration_manager)
        unallocated = allocation_manager.get_all_unallocated_resources()
        assert res_name in unallocated

        await allocation_manager.allocate_resources(db, [res_name], "test_owner")
        unallocated = allocation_manager.get_all_unallocated_resources()
        assert res_name not in unallocated

    @pytest.mark.asyncio
    async def test_deallocate_all_by_owner(self, db, allocation_manager, configuration_manager):
        res_name = _first_resource(configuration_manager)
        await allocation_manager.allocate_devices(db, [DEVICE], "test_owner")
        await allocation_manager.allocate_resources(db, [res_name], "test_owner")
        assert allocation_manager.is_device_allocated(*DEVICE)
        assert allocation_manager.is_resource_allocated(res_name)

        await allocation_manager.deallocate_all_by_owner(db, "test_owner")
        assert not allocation_manager.is_device_allocated(*DEVICE)
        assert not allocation_manager.is_resource_allocated(res_name)

    @pytest.mark.asyncio
    async def test_reservation_immediate_grant(self, db, allocation_manager):
        """Reservation is granted immediately when resources are free."""
        reservation = await allocation_manager.request_reservation(
            db, devices=[DEVICE], resources=[], owner="scientist_1"
        )
        assert reservation.status == ReservationStatus.GRANTED
        assert allocation_manager.is_device_allocated(*DEVICE)

    @pytest.mark.asyncio
    async def test_reservation_pending_when_busy(self, db, allocation_manager):
        """Reservation is queued when resources are busy."""
        await allocation_manager.allocate_devices(db, [DEVICE], "task_1")

        reservation = await allocation_manager.request_reservation(
            db, devices=[DEVICE], resources=[], owner="scientist_1"
        )
        assert reservation.status == ReservationStatus.PENDING

    @pytest.mark.asyncio
    async def test_reservation_granted_after_release(self, db, allocation_manager):
        """Pending reservation is granted when resources become free."""
        await allocation_manager.allocate_devices(db, [DEVICE], "task_1")

        reservation = await allocation_manager.request_reservation(
            db, devices=[DEVICE], resources=[], owner="scientist_1"
        )
        assert reservation.status == ReservationStatus.PENDING

        await allocation_manager.deallocate_devices(db, [DEVICE])
        await allocation_manager.process_reservations(db)

        alloc = allocation_manager.get_device_allocation(*DEVICE)
        assert alloc is not None
        assert alloc.owner == "scientist_1"

    @pytest.mark.asyncio
    async def test_cancel_reservation(self, db, allocation_manager):
        """Cancelling a granted reservation releases the device."""
        reservation = await allocation_manager.request_reservation(
            db, devices=[DEVICE], resources=[], owner="scientist_1"
        )
        assert reservation.status == ReservationStatus.GRANTED

        await allocation_manager.cancel_reservation(db, reservation.id)
        assert not allocation_manager.is_device_allocated(*DEVICE)
