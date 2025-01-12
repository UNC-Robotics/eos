from eos.resource_allocation.entities.resource_request import (
    ResourceAllocationRequest,
    ActiveResourceAllocationRequest,
    ResourceType,
    ResourceRequestAllocationStatus,
)
from eos.resource_allocation.exceptions import EosDeviceNotFoundError, EosResourceRequestError
from tests.fixtures import *

LAB_ID = "small_lab"


@pytest.mark.parametrize("setup_lab_experiment", [(LAB_ID, "water_purification")], indirect=True)
class TestResourceAllocationManager:
    @pytest.mark.asyncio
    async def test_request_resources(self, db, resource_allocation_manager):
        request = ResourceAllocationRequest(
            requester="test_requester",
            reason="Needed for experiment",
            experiment_id="water_purification_1",
        )
        request.add_resource("magnetic_mixer", LAB_ID, ResourceType.DEVICE)
        request.add_resource("026749f8f40342b38157f9824ae2f512", "", ResourceType.CONTAINER)

        def callback(active_request: ActiveResourceAllocationRequest):
            assert active_request.status == ResourceRequestAllocationStatus.ALLOCATED
            assert len(active_request.resources) == 2
            assert any(r.id == "magnetic_mixer" for r in active_request.resources)
            assert any(r.id == "026749f8f40342b38157f9824ae2f512" for r in active_request.resources)

        active_request = await resource_allocation_manager.request_resources(db, request, callback)

        assert active_request.requester == request.requester
        assert active_request.experiment_id == request.experiment_id
        assert active_request.reason == request.reason
        assert active_request.priority == request.priority
        assert active_request.status == ResourceRequestAllocationStatus.PENDING

        await resource_allocation_manager.process_requests(db)

    @pytest.mark.asyncio
    async def test_request_resources_priority(self, db, resource_allocation_manager):
        requests = [
            ResourceAllocationRequest(
                requester=f"test_requester{i}",
                reason="Needed for experiment",
                experiment_id="water_purification_1",
                priority=100 + i,
            )
            for i in range(1, 4)
        ]
        for request in requests:
            request.add_resource("magnetic_mixer", LAB_ID, ResourceType.DEVICE)

        active_requests = [
            await resource_allocation_manager.request_resources(db, req, lambda x: None) for req in requests
        ]
        await resource_allocation_manager.process_requests(db)

        # Ensure that request 3 is processed first as it has the highest priority
        active_request_3 = await resource_allocation_manager.get_active_request(db, active_requests[2].id)
        assert active_request_3.status == ResourceRequestAllocationStatus.ALLOCATED
        assert active_request_3.requester == "test_requester3"
        assert active_request_3.priority == 103

        active_request_2 = await resource_allocation_manager.get_active_request(db, active_requests[1].id)
        assert active_request_2.status == ResourceRequestAllocationStatus.PENDING
        assert active_request_2.requester == "test_requester2"
        assert active_request_2.priority == 102

        active_request_1 = await resource_allocation_manager.get_active_request(db, active_requests[0].id)
        assert active_request_1.status == ResourceRequestAllocationStatus.PENDING
        assert active_request_1.requester == "test_requester1"
        assert active_request_1.priority == 101

        await resource_allocation_manager.release_resources(db, active_request_3)
        await resource_allocation_manager.process_requests(db)

        # Request 2 is next
        active_request_2 = await resource_allocation_manager.get_active_request(db, active_requests[1].id)
        assert active_request_2.status == ResourceRequestAllocationStatus.ALLOCATED
        assert active_request_2.requester == "test_requester2"
        assert active_request_2.priority == 102

        active_request_1 = await resource_allocation_manager.get_active_request(db, active_requests[0].id)
        assert active_request_1.status == ResourceRequestAllocationStatus.PENDING
        assert active_request_1.requester == "test_requester1"
        assert active_request_1.priority == 101

    @pytest.mark.asyncio
    async def test_release_resources(self, db, resource_allocation_manager):
        request = ResourceAllocationRequest(
            requester="test_requester",
            reason="Needed for experiment",
            experiment_id="water_purification_1",
            priority=1,
        )
        request.add_resource("magnetic_mixer", LAB_ID, ResourceType.DEVICE)
        request.add_resource("026749f8f40342b38157f9824ae2f512", "", ResourceType.CONTAINER)

        active_request = await resource_allocation_manager.request_resources(db, request, lambda x: None)

        await resource_allocation_manager.process_requests(db)

        await resource_allocation_manager.release_resources(db, active_request)

        active_request = await resource_allocation_manager.get_active_request(db, active_request.id)
        assert active_request.status == ResourceRequestAllocationStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_process_active_requests(self, db, resource_allocation_manager):
        requests = [
            ResourceAllocationRequest(
                requester=f"test_requester{i}",
                reason="Needed for experiment",
                experiment_id="water_purification_1",
            )
            for i in range(1, 3)
        ]
        for request in requests:
            request.add_resource("magnetic_mixer", LAB_ID, ResourceType.DEVICE)

        active_requests = [
            await resource_allocation_manager.request_resources(db, req, lambda x: None) for req in requests
        ]

        await resource_allocation_manager.process_requests(db)

        active_request = await resource_allocation_manager.get_active_request(db, active_requests[0].id)
        assert active_request.status == ResourceRequestAllocationStatus.ALLOCATED

        active_request = await resource_allocation_manager.get_active_request(db, active_requests[1].id)
        assert active_request.status == ResourceRequestAllocationStatus.PENDING

    @pytest.mark.asyncio
    async def test_abort_active_request(self, db, resource_allocation_manager):
        request = ResourceAllocationRequest(
            requester="test_requester",
            reason="Needed for experiment",
            experiment_id="water_purification_1",
        )
        request.add_resource("magnetic_mixer", LAB_ID, ResourceType.DEVICE)
        request.add_resource("magnetic_mixer_2", LAB_ID, ResourceType.DEVICE)

        active_request = await resource_allocation_manager.request_resources(db, request, lambda x: None)

        await resource_allocation_manager.abort_request(db, active_request.id)

        active_request = await resource_allocation_manager.get_active_request(db, active_request.id)
        assert active_request.status == ResourceRequestAllocationStatus.ABORTED

        assert not await resource_allocation_manager._device_allocation_manager.is_allocated(
            db, LAB_ID, "magnetic_mixer"
        )
        assert not await resource_allocation_manager._device_allocation_manager.is_allocated(
            db, LAB_ID, "magnetic_mixer_2"
        )

    @pytest.mark.asyncio
    async def test_get_all_active_requests(self, db, resource_allocation_manager):
        requests = [
            ResourceAllocationRequest(
                requester=f"test_requester{i}",
                reason="Needed for experiment",
                experiment_id="water_purification_1",
            )
            for i in range(1, 3)
        ]
        requests[0].add_resource("magnetic_mixer", LAB_ID, ResourceType.DEVICE)
        requests[1].add_resource("026749f8f40342b38157f9824ae2f512", "", ResourceType.CONTAINER)

        for request in requests:
            await resource_allocation_manager.request_resources(db, request, lambda x: None)

        all_active_requests = await resource_allocation_manager.get_all_active_requests(db)
        assert len(all_active_requests) == 2
        assert all_active_requests[0].requester == requests[0].requester
        assert all_active_requests[0].experiment_id == requests[0].experiment_id
        assert all_active_requests[0].resources == requests[0].resources

        assert all_active_requests[1].requester == requests[1].requester
        assert all_active_requests[1].experiment_id == requests[1].experiment_id
        assert all_active_requests[1].resources == requests[1].resources

    @pytest.mark.asyncio
    async def test_get_active_request_nonexistent(self, db, resource_allocation_manager):
        nonexistent_id = "nonexistent_id"
        assert await resource_allocation_manager.get_active_request(db, nonexistent_id) is None

    @pytest.mark.asyncio
    async def test_delete_requests(self, db, resource_allocation_manager):
        request = ResourceAllocationRequest(
            requester="test_requester",
            reason="Needed for experiment",
            experiment_id="water_purification_1",
        )
        request.add_resource("magnetic_mixer", LAB_ID, ResourceType.DEVICE)

        active_request = await resource_allocation_manager.request_resources(db, request, lambda x: None)

        await resource_allocation_manager.process_requests(db)
        await resource_allocation_manager.release_resources(db, active_request)

        active_request = await resource_allocation_manager.get_active_request(db, active_request.id)
        assert active_request.status == ResourceRequestAllocationStatus.COMPLETED

        await resource_allocation_manager._delete_completed_and_aborted_requests(db)

        assert len(await resource_allocation_manager.get_all_active_requests(db)) == 0

    @pytest.mark.asyncio
    async def test_all_or_nothing_allocation(self, db, resource_allocation_manager):
        request = ResourceAllocationRequest(
            requester="test_requester",
            reason="Needed for experiment",
            experiment_id="water_purification_1",
        )
        request.add_resource("magnetic_mixer", LAB_ID, ResourceType.DEVICE)
        request.add_resource("nonexistent_device", LAB_ID, ResourceType.DEVICE)

        with pytest.raises(EosResourceRequestError):
            active_request = await resource_allocation_manager.request_resources(db, request, lambda x: None)
            await resource_allocation_manager.process_requests(db)

        assert active_request.status == ResourceRequestAllocationStatus.PENDING

        # Verify that neither resource was allocated
        assert not await resource_allocation_manager._device_allocation_manager.is_allocated(
            db, LAB_ID, "magnetic_mixer"
        )

        with pytest.raises(EosDeviceNotFoundError):
            assert not await resource_allocation_manager._device_allocation_manager.is_allocated(
                db, LAB_ID, "nonexistent_device"
            )
