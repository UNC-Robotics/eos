from eos.allocation.entities.allocation_request import (
    AllocationRequest,
    ActiveAllocationRequest,
    AllocationType,
    AllocationRequestStatus,
)
from eos.allocation.exceptions import (
    EosDeviceAllocatedError,
    EosDeviceNotFoundError,
    EosResourceAllocatedError,
    EosResourceNotFoundError,
    EosAllocationRequestError,
)
from eos.experiments.entities.experiment import ExperimentSubmission
from tests.fixtures import *

LAB_ID = "small_lab"
EXPERIMENT_NAME = "water_purification_1"


@pytest.fixture
async def experiment(db, experiment_manager):
    existing = await experiment_manager.get_experiment(db, EXPERIMENT_NAME)
    if not existing:
        submission = ExperimentSubmission(name=EXPERIMENT_NAME, type="water_purification", owner="test")
        await experiment_manager.create_experiment(db, submission)
        await db.commit()


@pytest.mark.parametrize("setup_lab_experiment", [(LAB_ID, "water_purification")], indirect=True)
class TestDeviceAllocation:
    @pytest.mark.asyncio
    async def test_allocate_device(self, db, allocation_manager, experiment):
        device_id = "magnetic_mixer"
        await allocation_manager.allocate_device(db, LAB_ID, device_id, "owner", EXPERIMENT_NAME)

        allocation = await allocation_manager.get_device_allocation(db, LAB_ID, device_id)

        assert allocation.name == device_id
        assert allocation.lab_name == LAB_ID
        assert allocation.owner == "owner"
        assert allocation.experiment_name == EXPERIMENT_NAME

    @pytest.mark.asyncio
    async def test_allocate_device_already_allocated(self, db, allocation_manager, experiment):
        device_id = "magnetic_mixer"
        await allocation_manager.allocate_device(db, LAB_ID, device_id, "owner", EXPERIMENT_NAME)

        with pytest.raises(EosDeviceAllocatedError):
            await allocation_manager.allocate_device(db, LAB_ID, device_id, "owner", EXPERIMENT_NAME)

    @pytest.mark.asyncio
    async def test_allocate_nonexistent_device(self, db, allocation_manager, experiment):
        device_id = "nonexistent_device_id"
        with pytest.raises(EosDeviceNotFoundError):
            await allocation_manager.allocate_device(db, LAB_ID, device_id, "owner", EXPERIMENT_NAME)

    @pytest.mark.asyncio
    async def test_deallocate_device(self, db, allocation_manager, experiment):
        device_id = "magnetic_mixer"
        await allocation_manager.allocate_device(db, LAB_ID, device_id, "owner", EXPERIMENT_NAME)

        await allocation_manager.deallocate_device(db, LAB_ID, device_id)
        allocation = await allocation_manager.get_device_allocation(db, LAB_ID, device_id)

        assert allocation is None

    @pytest.mark.asyncio
    async def test_deallocate_device_not_allocated(self, db, allocation_manager):
        device_id = "magnetic_mixer"
        result = await allocation_manager.deallocate_device(db, LAB_ID, device_id)
        assert result is False
        assert await allocation_manager.get_device_allocation(db, LAB_ID, device_id) is None

    @pytest.mark.asyncio
    async def test_is_device_allocated(self, db, allocation_manager, experiment):
        device_id = "magnetic_mixer"
        assert not await allocation_manager.is_device_allocated(db, LAB_ID, device_id)

        await allocation_manager.allocate_device(db, LAB_ID, device_id, "owner", EXPERIMENT_NAME)
        assert await allocation_manager.is_device_allocated(db, LAB_ID, device_id)

    @pytest.mark.asyncio
    async def test_get_device_allocations_by_owner(self, db, allocation_manager, experiment):
        device_id_1 = "magnetic_mixer"
        device_id_2 = "evaporator"
        device_id_3 = "substance_fridge"

        await allocation_manager.allocate_device(db, LAB_ID, device_id_1, "owner1", EXPERIMENT_NAME)
        await allocation_manager.allocate_device(db, LAB_ID, device_id_2, "owner1", EXPERIMENT_NAME)
        await allocation_manager.allocate_device(db, LAB_ID, device_id_3, "owner2", EXPERIMENT_NAME)

        allocations = await allocation_manager.get_device_allocations(db, owner="owner1")

        assert len(allocations) == 2
        assert device_id_1 in [allocation.name for allocation in allocations]
        assert device_id_2 in [allocation.name for allocation in allocations]

    @pytest.mark.asyncio
    async def test_get_all_device_allocations(self, db, allocation_manager, experiment):
        device_id_1 = "magnetic_mixer"
        device_id_2 = "evaporator"
        device_id_3 = "substance_fridge"

        await allocation_manager.allocate_device(db, LAB_ID, device_id_1, "owner", EXPERIMENT_NAME)
        await allocation_manager.allocate_device(db, LAB_ID, device_id_2, "owner", EXPERIMENT_NAME)
        await allocation_manager.allocate_device(db, LAB_ID, device_id_3, "owner", EXPERIMENT_NAME)

        allocations = await allocation_manager.get_device_allocations(db)

        assert len(allocations) == 3
        assert device_id_1 in [allocation.name for allocation in allocations]
        assert device_id_2 in [allocation.name for allocation in allocations]
        assert device_id_3 in [allocation.name for allocation in allocations]

    @pytest.mark.asyncio
    async def test_get_all_unallocated_devices(self, db, allocation_manager, experiment):
        device_id_1 = "magnetic_mixer"
        device_id_2 = "evaporator"
        device_id_3 = "substance_fridge"

        initial_unallocated_devices = await allocation_manager.get_all_unallocated_devices(db)

        await allocation_manager.allocate_device(db, LAB_ID, device_id_1, "owner", EXPERIMENT_NAME)
        await allocation_manager.allocate_device(db, LAB_ID, device_id_2, "owner", EXPERIMENT_NAME)

        new_unallocated_devices = await allocation_manager.get_all_unallocated_devices(db)

        assert len(new_unallocated_devices) == len(initial_unallocated_devices) - 2
        assert (LAB_ID, device_id_1) not in new_unallocated_devices
        assert (LAB_ID, device_id_2) not in new_unallocated_devices
        assert (LAB_ID, device_id_3) in new_unallocated_devices

    @pytest.mark.asyncio
    async def test_bulk_allocate_devices(self, db, allocation_manager, experiment):
        devices = [
            (LAB_ID, "magnetic_mixer"),
            (LAB_ID, "evaporator"),
            (LAB_ID, "substance_fridge"),
        ]

        await allocation_manager.bulk_allocate_devices(db, devices, "owner", EXPERIMENT_NAME)

        for lab_name, device_name in devices:
            allocation = await allocation_manager.get_device_allocation(db, lab_name, device_name)
            assert allocation is not None
            assert allocation.owner == "owner"

    @pytest.mark.asyncio
    async def test_bulk_deallocate_devices(self, db, allocation_manager, experiment):
        devices = [
            (LAB_ID, "magnetic_mixer"),
            (LAB_ID, "evaporator"),
            (LAB_ID, "substance_fridge"),
        ]

        await allocation_manager.bulk_allocate_devices(db, devices, "owner", EXPERIMENT_NAME)
        await allocation_manager.bulk_deallocate_devices(db, devices)

        for lab_name, device_name in devices:
            allocation = await allocation_manager.get_device_allocation(db, lab_name, device_name)
            assert allocation is None


@pytest.mark.parametrize("setup_lab_experiment", [(LAB_ID, "water_purification")], indirect=True)
class TestResourceAllocation:
    @pytest.mark.asyncio
    async def test_allocate_resource(self, db, allocation_manager, experiment):
        resource_id = "ec1ca48cd5d14c0c8cde376476e0d98d"
        await allocation_manager.allocate_resource(db, resource_id, "owner", EXPERIMENT_NAME)
        allocation = await allocation_manager.get_resource_allocation(db, resource_id)

        assert allocation.name == resource_id
        assert allocation.owner == "owner"
        assert allocation.experiment_name == EXPERIMENT_NAME

    @pytest.mark.asyncio
    async def test_allocate_resource_already_allocated(self, db, allocation_manager, experiment):
        resource_id = "ec1ca48cd5d14c0c8cde376476e0d98d"
        await allocation_manager.allocate_resource(db, resource_id, "owner", EXPERIMENT_NAME)

        with pytest.raises(EosResourceAllocatedError):
            await allocation_manager.allocate_resource(db, resource_id, "owner", EXPERIMENT_NAME)

    @pytest.mark.asyncio
    async def test_allocate_nonexistent_resource(self, db, allocation_manager, experiment):
        resource_id = "nonexistent_resource_id"
        with pytest.raises(EosResourceNotFoundError):
            await allocation_manager.allocate_resource(db, resource_id, "owner", EXPERIMENT_NAME)

    @pytest.mark.asyncio
    async def test_deallocate_resource(self, db, allocation_manager, experiment):
        resource_id = "ec1ca48cd5d14c0c8cde376476e0d98d"
        await allocation_manager.allocate_resource(db, resource_id, "owner", EXPERIMENT_NAME)

        await allocation_manager.deallocate_resource(db, resource_id)
        allocation = await allocation_manager.get_resource_allocation(db, resource_id)

        assert allocation is None

    @pytest.mark.asyncio
    async def test_deallocate_resource_not_allocated(self, db, allocation_manager):
        resource_id = "ec1ca48cd5d14c0c8cde376476e0d98d"
        result = await allocation_manager.deallocate_resource(db, resource_id)

        assert result is False
        allocation = await allocation_manager.get_resource_allocation(db, resource_id)
        assert allocation is None

    @pytest.mark.asyncio
    async def test_is_resource_allocated(self, db, allocation_manager, experiment):
        resource_id = "ec1ca48cd5d14c0c8cde376476e0d98d"
        assert not await allocation_manager.is_resource_allocated(db, resource_id)

        await allocation_manager.allocate_resource(db, resource_id, "owner", EXPERIMENT_NAME)
        assert await allocation_manager.is_resource_allocated(db, resource_id)

    @pytest.mark.asyncio
    async def test_get_resource_allocations_by_owner(self, db, allocation_manager, experiment):
        resource_id_1 = "ec1ca48cd5d14c0c8cde376476e0d98d"
        resource_id_2 = "84eb17d61e884ffd9d1fdebcbad1532b"
        resource_id_3 = "a3b958aea8bd435386cdcbab20a2d3ec"

        await allocation_manager.allocate_resource(db, resource_id_1, "owner", EXPERIMENT_NAME)
        await allocation_manager.allocate_resource(db, resource_id_2, "owner", EXPERIMENT_NAME)
        await allocation_manager.allocate_resource(db, resource_id_3, "another_owner", EXPERIMENT_NAME)

        allocations = await allocation_manager.get_resource_allocations(db, owner="owner")
        assert len(allocations) == 2
        assert resource_id_1 in [a.name for a in allocations]
        assert resource_id_2 in [a.name for a in allocations]

        allocations = await allocation_manager.get_resource_allocations(db, owner="another_owner")
        assert len(allocations) == 1
        assert allocations[0].name == resource_id_3

    @pytest.mark.asyncio
    async def test_get_all_resource_allocations(self, db, allocation_manager, experiment):
        resource_id_1 = "ec1ca48cd5d14c0c8cde376476e0d98d"
        resource_id_2 = "84eb17d61e884ffd9d1fdebcbad1532b"
        resource_id_3 = "a3b958aea8bd435386cdcbab20a2d3ec"

        await allocation_manager.allocate_resource(db, resource_id_1, "owner", EXPERIMENT_NAME)
        await allocation_manager.allocate_resource(db, resource_id_2, "owner", EXPERIMENT_NAME)
        await allocation_manager.allocate_resource(db, resource_id_3, "another_owner", EXPERIMENT_NAME)

        allocations = await allocation_manager.get_resource_allocations(db)
        assert len(allocations) == 3
        assert {allocation.name for allocation in allocations} == {
            resource_id_1,
            resource_id_2,
            resource_id_3,
        }

    @pytest.mark.asyncio
    async def test_get_all_unallocated_resources(self, db, allocation_manager, experiment):
        resource_id_1 = "ec1ca48cd5d14c0c8cde376476e0d98d"
        resource_id_2 = "84eb17d61e884ffd9d1fdebcbad1532b"
        resource_id_3 = "a3b958aea8bd435386cdcbab20a2d3ec"

        initial_unallocated_resources = await allocation_manager.get_all_unallocated_resources(db)

        await allocation_manager.allocate_resource(db, resource_id_1, "owner1", EXPERIMENT_NAME)
        await allocation_manager.allocate_resource(db, resource_id_2, "owner2", EXPERIMENT_NAME)

        new_unallocated_resources = await allocation_manager.get_all_unallocated_resources(db)
        assert len(new_unallocated_resources) == len(initial_unallocated_resources) - 2
        assert resource_id_1 not in new_unallocated_resources
        assert resource_id_2 not in new_unallocated_resources
        assert resource_id_3 in new_unallocated_resources

    @pytest.mark.asyncio
    async def test_bulk_allocate_resources(self, db, allocation_manager, experiment):
        resources = [
            "ec1ca48cd5d14c0c8cde376476e0d98d",
            "84eb17d61e884ffd9d1fdebcbad1532b",
            "a3b958aea8bd435386cdcbab20a2d3ec",
        ]

        await allocation_manager.bulk_allocate_resources(db, resources, "owner", EXPERIMENT_NAME)

        for resource_name in resources:
            allocation = await allocation_manager.get_resource_allocation(db, resource_name)
            assert allocation is not None
            assert allocation.owner == "owner"

    @pytest.mark.asyncio
    async def test_bulk_deallocate_resources(self, db, allocation_manager, experiment):
        resources = [
            "ec1ca48cd5d14c0c8cde376476e0d98d",
            "84eb17d61e884ffd9d1fdebcbad1532b",
            "a3b958aea8bd435386cdcbab20a2d3ec",
        ]

        await allocation_manager.bulk_allocate_resources(db, resources, "owner", EXPERIMENT_NAME)
        await allocation_manager.bulk_deallocate_resources(db, resources)

        for resource_name in resources:
            allocation = await allocation_manager.get_resource_allocation(db, resource_name)
            assert allocation is None


@pytest.mark.parametrize("setup_lab_experiment", [(LAB_ID, "water_purification")], indirect=True)
class TestMixedAllocation:
    @pytest.mark.asyncio
    async def test_deallocate_all_by_owner_mixed(self, db, allocation_manager, experiment):
        await allocation_manager.allocate_device(db, LAB_ID, "magnetic_mixer", "owner1", EXPERIMENT_NAME)
        await allocation_manager.allocate_device(db, LAB_ID, "evaporator", "owner2", EXPERIMENT_NAME)

        await allocation_manager.allocate_resource(db, "ec1ca48cd5d14c0c8cde376476e0d98d", "owner1", EXPERIMENT_NAME)
        await allocation_manager.allocate_resource(db, "84eb17d61e884ffd9d1fdebcbad1532b", "owner2", EXPERIMENT_NAME)

        await allocation_manager.deallocate_all_by_owner(db, "owner2")

        owner2_device_allocations = await allocation_manager.get_device_allocations(db, owner="owner2")
        owner2_resource_allocations = await allocation_manager.get_resource_allocations(db, owner="owner2")
        assert owner2_device_allocations == []
        assert owner2_resource_allocations == []

        owner1_device_allocations = await allocation_manager.get_device_allocations(db, owner="owner1")
        owner1_resource_allocations = await allocation_manager.get_resource_allocations(db, owner="owner1")
        assert len(owner1_device_allocations) == 1
        assert len(owner1_resource_allocations) == 1


@pytest.mark.parametrize("setup_lab_experiment", [(LAB_ID, "water_purification")], indirect=True)
class TestAllocationRequests:
    @pytest.mark.asyncio
    async def test_request_allocations(self, db, allocation_manager, experiment):
        request = AllocationRequest(
            requester="test_requester",
            reason="Needed for experiment",
            experiment_name=EXPERIMENT_NAME,
        )
        request.add_allocation("magnetic_mixer", LAB_ID, AllocationType.DEVICE)
        request.add_allocation("026749f8f40342b38157f9824ae2f512", LAB_ID, AllocationType.RESOURCE)

        def callback(active_request: ActiveAllocationRequest):
            assert active_request.status == AllocationRequestStatus.ALLOCATED
            assert len(active_request.allocations) == 2
            assert any(
                a.name == "magnetic_mixer" and a.allocation_type == AllocationType.DEVICE
                for a in active_request.allocations
            )
            assert any(
                a.name == "026749f8f40342b38157f9824ae2f512" and a.allocation_type == AllocationType.RESOURCE
                for a in active_request.allocations
            )

        active_request = await allocation_manager.request_allocations(db, request, callback)

        assert active_request.requester == request.requester
        assert active_request.experiment_name == request.experiment_name
        assert active_request.reason == request.reason
        assert active_request.priority == request.priority
        assert active_request.status == AllocationRequestStatus.PENDING

        await allocation_manager.process_requests(db)

    @pytest.mark.asyncio
    async def test_request_allocations_priority(self, db, allocation_manager, experiment):
        requests = [
            AllocationRequest(
                requester=f"test_requester{i}",
                reason="Needed for experiment",
                experiment_name=EXPERIMENT_NAME,
                priority=100 + i,
            )
            for i in range(1, 4)
        ]
        for request in requests:
            request.add_allocation("magnetic_mixer", LAB_ID, AllocationType.DEVICE)

        active_requests = [await allocation_manager.request_allocations(db, req, lambda x: None) for req in requests]
        await allocation_manager.process_requests(db)

        active_request_3 = await allocation_manager.get_active_request(db, active_requests[2].id)
        assert active_request_3.status == AllocationRequestStatus.ALLOCATED
        assert active_request_3.requester == "test_requester3"
        assert active_request_3.priority == 103

        active_request_2 = await allocation_manager.get_active_request(db, active_requests[1].id)
        assert active_request_2.status == AllocationRequestStatus.PENDING
        assert active_request_2.requester == "test_requester2"
        assert active_request_2.priority == 102

        active_request_1 = await allocation_manager.get_active_request(db, active_requests[0].id)
        assert active_request_1.status == AllocationRequestStatus.PENDING
        assert active_request_1.requester == "test_requester1"
        assert active_request_1.priority == 101

        await allocation_manager.release_allocations(db, active_request_3)
        await allocation_manager.process_requests(db)

        active_request_2 = await allocation_manager.get_active_request(db, active_requests[1].id)
        assert active_request_2.status == AllocationRequestStatus.ALLOCATED
        assert active_request_2.requester == "test_requester2"
        assert active_request_2.priority == 102

        active_request_1 = await allocation_manager.get_active_request(db, active_requests[0].id)
        assert active_request_1.status == AllocationRequestStatus.PENDING
        assert active_request_1.requester == "test_requester1"
        assert active_request_1.priority == 101

    @pytest.mark.asyncio
    async def test_release_allocations(self, db, allocation_manager, experiment):
        request = AllocationRequest(
            requester="test_requester",
            reason="Needed for experiment",
            experiment_name=EXPERIMENT_NAME,
            priority=1,
        )
        request.add_allocation("magnetic_mixer", LAB_ID, AllocationType.DEVICE)
        request.add_allocation("026749f8f40342b38157f9824ae2f512", LAB_ID, AllocationType.RESOURCE)

        active_request = await allocation_manager.request_allocations(db, request, lambda x: None)

        await allocation_manager.process_requests(db)

        await allocation_manager.release_allocations(db, active_request)

        active_request = await allocation_manager.get_active_request(db, active_request.id)
        assert active_request.status == AllocationRequestStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_process_active_requests(self, db, allocation_manager, experiment):
        requests = [
            AllocationRequest(
                requester=f"test_requester{i}",
                reason="Needed for experiment",
                experiment_name=EXPERIMENT_NAME,
            )
            for i in range(1, 3)
        ]
        for request in requests:
            request.add_allocation("magnetic_mixer", LAB_ID, AllocationType.DEVICE)

        active_requests = [await allocation_manager.request_allocations(db, req, lambda x: None) for req in requests]

        await allocation_manager.process_requests(db)

        active_request = await allocation_manager.get_active_request(db, active_requests[0].id)
        assert active_request.status == AllocationRequestStatus.ALLOCATED

        active_request = await allocation_manager.get_active_request(db, active_requests[1].id)
        assert active_request.status == AllocationRequestStatus.PENDING

    @pytest.mark.asyncio
    async def test_abort_active_request(self, db, allocation_manager, experiment):
        request = AllocationRequest(
            requester="test_requester",
            reason="Needed for experiment",
            experiment_name=EXPERIMENT_NAME,
        )
        request.add_allocation("magnetic_mixer", LAB_ID, AllocationType.DEVICE)
        request.add_allocation("magnetic_mixer_2", LAB_ID, AllocationType.DEVICE)

        active_request = await allocation_manager.request_allocations(db, request, lambda x: None)

        await allocation_manager.abort_request(db, active_request.id)

        active_request = await allocation_manager.get_active_request(db, active_request.id)
        assert active_request.status == AllocationRequestStatus.ABORTED

        assert not await allocation_manager.is_device_allocated(db, LAB_ID, "magnetic_mixer")
        assert not await allocation_manager.is_device_allocated(db, LAB_ID, "magnetic_mixer_2")

    @pytest.mark.asyncio
    async def test_get_all_active_requests(self, db, allocation_manager, experiment):
        requests = [
            AllocationRequest(
                requester=f"test_requester{i}",
                reason="Needed for experiment",
                experiment_name=EXPERIMENT_NAME,
            )
            for i in range(1, 3)
        ]
        requests[0].add_allocation("magnetic_mixer", LAB_ID, AllocationType.DEVICE)
        requests[1].add_allocation("026749f8f40342b38157f9824ae2f512", LAB_ID, AllocationType.RESOURCE)

        for request in requests:
            await allocation_manager.request_allocations(db, request, lambda x: None)

        all_active_requests = await allocation_manager.get_all_active_requests(db)
        assert len(all_active_requests) == 2
        assert all_active_requests[0].requester == requests[0].requester
        assert all_active_requests[0].experiment_name == requests[0].experiment_name
        assert all_active_requests[0].allocations == requests[0].allocations

        assert all_active_requests[1].requester == requests[1].requester
        assert all_active_requests[1].experiment_name == requests[1].experiment_name
        assert all_active_requests[1].allocations == requests[1].allocations

    @pytest.mark.asyncio
    async def test_get_active_request_nonexistent(self, db, allocation_manager):
        nonexistent_id = 34
        assert await allocation_manager.get_active_request(db, nonexistent_id) is None

    @pytest.mark.asyncio
    async def test_delete_requests(self, db, allocation_manager, experiment):
        request = AllocationRequest(
            requester="test_requester",
            reason="Needed for experiment",
            experiment_name=EXPERIMENT_NAME,
        )
        request.add_allocation("magnetic_mixer", LAB_ID, AllocationType.DEVICE)

        active_request = await allocation_manager.request_allocations(db, request, lambda x: None)

        await allocation_manager.process_requests(db)
        await allocation_manager.release_allocations(db, active_request)

        active_request = await allocation_manager.get_active_request(db, active_request.id)
        assert active_request.status == AllocationRequestStatus.COMPLETED

        await allocation_manager._delete_completed_and_aborted_requests(db)

        assert len(await allocation_manager.get_all_active_requests(db)) == 0

    @pytest.mark.asyncio
    async def test_all_or_nothing_allocation(self, db, allocation_manager, experiment):
        request = AllocationRequest(
            requester="test_requester",
            reason="Needed for experiment",
            experiment_name=EXPERIMENT_NAME,
        )
        request.add_allocation("magnetic_mixer", LAB_ID, AllocationType.DEVICE)
        request.add_allocation("nonexistent_device", LAB_ID, AllocationType.DEVICE)

        with pytest.raises(EosAllocationRequestError):
            active_request = await allocation_manager.request_allocations(db, request, lambda x: None)
            await allocation_manager.process_requests(db)

        assert active_request.status == AllocationRequestStatus.PENDING

        assert not await allocation_manager.is_device_allocated(db, LAB_ID, "magnetic_mixer")

        with pytest.raises(EosDeviceNotFoundError):
            await allocation_manager.is_device_allocated(db, LAB_ID, "nonexistent_device")
