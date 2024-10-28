import asyncio
from collections.abc import Callable
from datetime import datetime, timezone

from bson import ObjectId

from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log
from eos.persistence.async_mongodb_interface import AsyncMongoDbInterface
from eos.resource_allocation.container_allocator import ContainerAllocator
from eos.resource_allocation.device_allocator import DeviceAllocator
from eos.resource_allocation.entities.resource_request import (
    ResourceAllocationRequest,
    ActiveResourceAllocationRequest,
    ResourceRequestAllocationStatus,
    ResourceType,
)
from eos.resource_allocation.exceptions import EosResourceRequestError
from eos.resource_allocation.repositories.resource_request_repository import (
    ResourceRequestRepository,
)


class ResourceAllocationManager:
    """
    Provides facilities to request allocation of resources.
    """

    def __init__(
        self,
        db_interface: AsyncMongoDbInterface,
    ):
        self._active_requests = ResourceRequestRepository(db_interface)
        self._device_allocator = None
        self._container_allocator = None

        # Callbacks for when resource allocation requests are processed
        self._request_callbacks: dict[ObjectId, Callable[[ActiveResourceAllocationRequest], None]] = {}

        self._lock = asyncio.Lock()

    async def initialize(
        self, configuration_manager: ConfigurationManager, db_interface: AsyncMongoDbInterface
    ) -> None:
        self._device_allocator = DeviceAllocator(configuration_manager, db_interface)
        await self._device_allocator.initialize(db_interface)

        self._container_allocator = ContainerAllocator(configuration_manager, db_interface)
        await self._container_allocator.initialize(db_interface)

        await self._delete_all_requests()
        await self._delete_all_allocations()

        log.debug("Resource allocation manager initialized.")

    async def request_resources(
        self,
        request: ResourceAllocationRequest,
        callback: Callable[[ActiveResourceAllocationRequest], None],
    ) -> ActiveResourceAllocationRequest:
        """
        Request allocation of resources. A callback function is called when the resource allocation requests are
        processed. If a resource allocation request already exists, the existing request is used instead of creating
        a new one.

        :param request: The resource allocation request.
        :param callback: Callback function to be called when the resource allocation request is processed.
        :return: List of active resource allocation requests.
        """
        async with self._lock:
            existing_request = await self._find_existing_request(request)
            if existing_request:
                if existing_request.status in [
                    ResourceRequestAllocationStatus.PENDING,
                    ResourceRequestAllocationStatus.ALLOCATED,
                ]:
                    self._request_callbacks[existing_request.id] = callback
                return existing_request

            active_request = ActiveResourceAllocationRequest(request=request)
            result = await self._active_requests.create(active_request.model_dump(by_alias=True))
            active_request.id = result.inserted_id
            self._request_callbacks[active_request.id] = callback
            return active_request

    async def release_resources(self, active_request: ActiveResourceAllocationRequest) -> None:
        """
        Release the resources allocated for an active resource allocation request.

        :param active_request: The active resource allocation request.
        """
        async with self._lock:
            for resource in active_request.request.resources:
                if resource.resource_type == ResourceType.DEVICE:
                    await self._device_allocator.deallocate(resource.lab_id, resource.id)
                elif resource.resource_type == ResourceType.CONTAINER:
                    await self._container_allocator.deallocate(resource.id)
                else:
                    raise EosResourceRequestError(f"Unknown resource type: {resource.resource_type}")

            await self._update_request_status(active_request.id, ResourceRequestAllocationStatus.COMPLETED)

    async def process_active_requests(self) -> None:
        async with self._lock:
            await self._clean_completed_and_aborted_requests()

            active_requests = await self._get_all_active_requests_prioritized()

            for active_request in active_requests:
                if active_request.status != ResourceRequestAllocationStatus.PENDING:
                    continue

                allocation_success = await self._try_allocate(active_request)

                if allocation_success:
                    self._invoke_request_callback(active_request)

    async def abort_active_request(self, request_id: ObjectId) -> None:
        """
        Abort an active resource allocation request.
        """
        async with self._lock:
            request = await self.get_active_request(request_id)
            for resource in request.request.resources:
                if resource.resource_type == ResourceType.DEVICE:
                    await self._device_allocator.deallocate(resource.lab_id, resource.id)
                elif resource.resource_type == ResourceType.CONTAINER:
                    await self._container_allocator.deallocate(resource.id)
            await self._update_request_status(request_id, ResourceRequestAllocationStatus.ABORTED)
            active_request = await self.get_active_request(request_id)
            self._invoke_request_callback(active_request)

    async def _get_all_active_requests_prioritized(self) -> list[ActiveResourceAllocationRequest]:
        """
        Get all active resource allocation requests prioritized by the request priority in ascending order.
        """
        active_requests = []
        active_requests_count = await self._active_requests.count(status=ResourceRequestAllocationStatus.PENDING.value)

        if active_requests_count > 0:
            active_requests = await self._active_requests.get_requests_prioritized(
                ResourceRequestAllocationStatus.PENDING
            )

        return [ActiveResourceAllocationRequest(**request) for request in active_requests]

    async def get_all_active_requests(
        self,
        requester: str | None = None,
        lab_id: str | None = None,
        experiment_id: str | None = None,
        status: ResourceRequestAllocationStatus | None = None,
    ) -> list[ActiveResourceAllocationRequest]:
        """
        Get all active resource allocation requests.

        :param requester: Filter by the requester.
        :param lab_id: Filter by the lab ID.
        :param experiment_id: Filter by the experiment ID.
        :param status: Filter by the status.
        """
        query = {"requester": requester}
        if lab_id:
            query["request.lab_id"] = lab_id
        if experiment_id:
            query["request.experiment_id"] = experiment_id
        if status:
            query["status"] = status.value
        active_requests = await self._active_requests.get_all(**query)
        return [ActiveResourceAllocationRequest(**request) for request in active_requests]

    async def get_active_request(self, request_id: ObjectId) -> ActiveResourceAllocationRequest | None:
        """
        Get an active resource allocation request by ID. If the request does not exist, returns None.
        """
        request = await self._active_requests.get_one(_id=request_id)
        return ActiveResourceAllocationRequest(**request) if request else None

    async def _update_request_status(self, request_id: ObjectId, status: ResourceRequestAllocationStatus) -> None:
        """
        Update the status of an active resource allocation request.
        """
        update_data = {"status": status.value}
        if status == ResourceRequestAllocationStatus.ALLOCATED:
            update_data["allocated_at"] = datetime.now(tz=timezone.utc)

        await self._active_requests.update_one(update_data, _id=request_id)

    async def _find_existing_request(
        self, request: ResourceAllocationRequest
    ) -> ActiveResourceAllocationRequest | None:
        """
        Find an existing active resource allocation request that matches the given request.
        """
        existing_request = await self._active_requests.get_existing_request(request)
        return ActiveResourceAllocationRequest(**existing_request) if existing_request else None

    def _invoke_request_callback(self, active_request: ActiveResourceAllocationRequest) -> None:
        """
        Invoke the allocation callback for an active resource allocation request.
        """
        callback = self._request_callbacks.pop(active_request.id, None)
        if callback:
            callback(active_request)

    async def _try_allocate(self, active_request: ActiveResourceAllocationRequest) -> bool:
        temp_allocations = []
        all_available = True

        for resource in active_request.request.resources:
            if resource.resource_type == ResourceType.DEVICE:
                if not await self._device_allocator.is_allocated(resource.lab_id, resource.id):
                    temp_allocations.append(("device", resource.lab_id, resource.id))
                else:
                    all_available = False
                    break
            elif resource.resource_type == ResourceType.CONTAINER:
                if not await self._container_allocator.is_allocated(resource.id):
                    temp_allocations.append(("container", resource.id))
                else:
                    all_available = False
                    break
            else:
                raise EosResourceRequestError(f"Unknown resource type: {resource.resource_type}")

        if all_available:
            for allocation in temp_allocations:
                if allocation[0] == "device":
                    await self._device_allocator.allocate(
                        allocation[1],
                        allocation[2],
                        active_request.request.requester,
                        experiment_id=active_request.request.experiment_id,
                    )
                else:  # container
                    await self._container_allocator.allocate(
                        allocation[1],
                        active_request.request.requester,
                        experiment_id=active_request.request.experiment_id,
                    )

            await self._update_request_status(active_request.id, ResourceRequestAllocationStatus.ALLOCATED)
            active_request.status = ResourceRequestAllocationStatus.ALLOCATED
            return True

        return False

    async def _clean_completed_and_aborted_requests(self) -> None:
        """
        Remove completed or aborted active resource allocation requests.
        """
        await self._active_requests.clean_requests()

    async def _delete_all_requests(self) -> None:
        """
        Delete all active resource allocation requests.
        """
        await self._active_requests.delete_all()

    async def _delete_all_allocations(self) -> None:
        """
        Delete all device and container allocations.
        """
        await asyncio.gather(self._device_allocator.deallocate_all(), self._container_allocator.deallocate_all())

    @property
    def device_allocator(self) -> DeviceAllocator:
        return self._device_allocator

    @property
    def container_allocator(self) -> ContainerAllocator:
        return self._container_allocator
