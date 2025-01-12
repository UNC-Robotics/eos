import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final, TypeAlias, Literal

from sqlalchemy import select, update, delete, desc

from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.resource_allocation.container_allocation_manager import ContainerAllocationManager
from eos.resource_allocation.device_allocation_manager import DeviceAllocationManager
from eos.resource_allocation.entities.resource_request import (
    ResourceAllocationRequest,
    ActiveResourceAllocationRequest,
    ResourceRequestAllocationStatus,
    ResourceType,
    ResourceAllocationRequestModel,
)
from eos.resource_allocation.exceptions import EosResourceRequestError
from eos.utils.di.di_container import inject_all

RequestCallback: TypeAlias = Callable[[ActiveResourceAllocationRequest], None]
ResourceTypeStr = Literal["device", "container"]


@dataclass
class TempAllocation:
    """Represents a temporary resource allocation."""

    resource_type: ResourceTypeStr
    lab_id: str | None
    resource_id: str


class ResourceAllocationManager:
    """
    Provides facilities to request allocation of resources.
    """

    _ACTIVE_STATUSES: Final = {ResourceRequestAllocationStatus.PENDING, ResourceRequestAllocationStatus.ALLOCATED}
    _CLEANUP_STATUSES: Final = {ResourceRequestAllocationStatus.COMPLETED, ResourceRequestAllocationStatus.ABORTED}
    _BATCH_SIZE: Final = 10

    @inject_all
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        db_interface: AbstractSqlDbInterface,
        batch_size: int = _BATCH_SIZE,
    ):
        self._device_allocation_manager = DeviceAllocationManager(configuration_manager)
        self._container_allocation_manager = ContainerAllocationManager(configuration_manager)
        self._db_interface = db_interface

        # Callbacks for when resource allocation requests are processed
        self._request_callbacks: dict[int, Callable[[ActiveResourceAllocationRequest], None]] = {}

        self._lock = asyncio.Lock()

        self._batch_size = batch_size

    async def initialize(self, db: AsyncDbSession) -> None:
        await self._delete_all_requests(db)
        await self._delete_all_allocations(db)

        log.debug("Resource allocation manager initialized.")

    async def request_resources(
        self,
        db: AsyncDbSession,
        request: ResourceAllocationRequest,
        callback: RequestCallback,
    ) -> ActiveResourceAllocationRequest:
        """Request resource allocation with duplicate request detection."""
        if existing_request := await self._find_existing_request(db, request):
            if existing_request.status in self._ACTIVE_STATUSES:
                self._request_callbacks[existing_request.id] = callback
            return existing_request

        model = ResourceAllocationRequestModel(
            requester=request.requester,
            experiment_id=request.experiment_id,
            reason=request.reason,
            priority=request.priority,
            timeout=request.timeout,
            resources=[resource.model_dump() for resource in request.resources],
            status=ResourceRequestAllocationStatus.PENDING,
        )

        db.add(model)
        await db.flush()
        await db.refresh(model)

        active_request = ActiveResourceAllocationRequest.model_validate(model)
        self._request_callbacks[active_request.id] = callback
        return active_request

    async def release_resources(self, db: AsyncDbSession, request: ActiveResourceAllocationRequest) -> None:
        """Release all allocated resources for a request."""
        await self._bulk_deallocate_resources(db, request, ResourceRequestAllocationStatus.COMPLETED)

    async def abort_request(self, db: AsyncDbSession, request_id: int) -> None:
        """Abort an active request and release its resources."""
        if request := await self.get_active_request(db, request_id):
            await self._bulk_deallocate_resources(db, request, ResourceRequestAllocationStatus.ABORTED)
            request = await self.get_active_request(db, request_id)
            self._invoke_request_callback(request)

    async def _bulk_deallocate_resources(
        self, db: AsyncDbSession, request: ActiveResourceAllocationRequest, new_status: ResourceRequestAllocationStatus
    ) -> None:
        """Bulk deallocate resources and update request status."""
        devices = []
        containers = []
        for resource in request.resources:
            if resource.resource_type == ResourceType.DEVICE:
                devices.append((resource.lab_id, resource.id))
            elif resource.resource_type == ResourceType.CONTAINER:
                containers.append(resource.id)

        if devices:
            await self._device_allocation_manager.bulk_deallocate(db, devices)

        if containers:
            await self._container_allocation_manager.bulk_deallocate(db, containers)

        await self._update_request_status(db, request.id, new_status)

    async def get_active_request(self, db: AsyncDbSession, request_id: int) -> ActiveResourceAllocationRequest | None:
        """Get an active request."""
        result = await db.execute(
            select(ResourceAllocationRequestModel).where(ResourceAllocationRequestModel.id == request_id)
        )
        if model := result.scalar_one_or_none():
            return ActiveResourceAllocationRequest.model_validate(model)
        return None

    async def process_requests(self, db: AsyncDbSession) -> None:
        """Process pending resource allocation requests in priority-ordered batches."""
        async with self._lock:
            await self._delete_completed_and_aborted_requests(db)

            active_requests = await self._get_all_active_requests_prioritized(db)

            # Group requests by priority for batch processing
            priority_groups = {}
            for request in active_requests:
                priority_groups.setdefault(request.priority, []).append(request)

            # Process groups in descending priority order
            for priority in sorted(priority_groups.keys(), reverse=True):
                requests = priority_groups[priority]

                # Process each priority group in batches
                for i in range(0, len(requests), self._batch_size):
                    batch = requests[i : i + self._batch_size]
                    await self._process_request_batch(db, batch)

    async def _process_request_batch(self, db: AsyncDbSession, requests: list[ActiveResourceAllocationRequest]) -> None:
        """Process a batch of requests of the same priority."""
        for request in requests:
            if request.status != ResourceRequestAllocationStatus.PENDING:
                continue

            if self._is_request_timed_out(request, datetime.now(timezone.utc)):
                await self._handle_timeout(db, request)
                continue

            if await self._try_allocate(db, request):
                self._invoke_request_callback(request)

    async def _handle_timeout(self, db: AsyncDbSession, request: ActiveResourceAllocationRequest) -> None:
        request_time = (
            request.created_at.replace(tzinfo=timezone.utc) if not request.created_at.tzinfo else request.created_at
        )
        log.warning(
            f"Resource allocation request {request.id} for {request.requester} "
            f"timed out after {(datetime.now(timezone.utc) - request_time).total_seconds():.1f}s"
        )
        await self.abort_request(db, request.id)
        self._invoke_request_callback(request)

    async def _try_allocate(self, db: AsyncDbSession, request: ActiveResourceAllocationRequest) -> bool:
        """Attempt to allocate all resources for a request."""
        temp_allocations: list[TempAllocation] = []

        try:
            if not await self._check_and_prepare_allocations(db, request, temp_allocations):
                return False

            await self._perform_allocations(db, request, temp_allocations)
            await self._update_request_status(db, request.id, ResourceRequestAllocationStatus.ALLOCATED)
            request.status = ResourceRequestAllocationStatus.ALLOCATED
            return True

        except Exception as e:
            await self.abort_request(db, request.id)
            raise EosResourceRequestError(f"Failed to allocate resources for request {request.id}: {e!s}") from e

    async def _check_and_prepare_allocations(
        self, db: AsyncDbSession, request: ActiveResourceAllocationRequest, temp_allocations: list[TempAllocation]
    ) -> bool:
        """Check resource availability and prepare temporary allocations with optimized bulk queries."""
        devices = []
        containers = []

        for resource in request.resources:
            if resource.resource_type == ResourceType.DEVICE:
                devices.append((resource.lab_id, resource.id))
                temp_allocations.append(TempAllocation("device", resource.lab_id, resource.id))
            elif resource.resource_type == ResourceType.CONTAINER:
                containers.append(resource.id)
                temp_allocations.append(TempAllocation("container", None, resource.id))

        if devices:
            allocated_devices = await self._device_allocation_manager.bulk_check_allocated(db, devices)
            if allocated_devices:
                return False

        if containers:
            allocated_containers = await self._container_allocation_manager.bulk_check_allocated(db, containers)
            if allocated_containers:
                return False

        return True

    async def _perform_allocations(
        self, db: AsyncDbSession, request: ActiveResourceAllocationRequest, allocations: list[TempAllocation]
    ) -> None:
        """Perform resource allocations."""
        # Group allocations by type
        devices = [(alloc.lab_id, alloc.resource_id) for alloc in allocations if alloc.resource_type == "device"]
        containers = [alloc.resource_id for alloc in allocations if alloc.resource_type == "container"]

        # Bulk allocate devices if any
        if devices:
            await self._device_allocation_manager.bulk_allocate(
                db, devices, request.requester, experiment_id=request.experiment_id
            )

        # Bulk allocate containers if any
        if containers:
            await self._container_allocation_manager.bulk_allocate(
                db, containers, request.requester, experiment_id=request.experiment_id
            )

    def _is_request_timed_out(self, request: ActiveResourceAllocationRequest, current_time: datetime) -> bool:
        """Check if a request has timed out."""
        request_time = (
            request.created_at.replace(tzinfo=timezone.utc) if not request.created_at.tzinfo else request.created_at
        )
        return (current_time - request_time).total_seconds() > request.timeout

    async def _get_all_active_requests_prioritized(self, db: AsyncDbSession) -> list[ActiveResourceAllocationRequest]:
        """Get pending requests ordered by priority."""
        stmt = (
            select(ResourceAllocationRequestModel)
            .where(ResourceAllocationRequestModel.status == ResourceRequestAllocationStatus.PENDING)
            .order_by(desc(ResourceAllocationRequestModel.priority))
        )

        result = await db.execute(stmt)
        return [ActiveResourceAllocationRequest.model_validate(model) for model in result.scalars()]

    async def get_all_active_requests(
        self,
        db: AsyncDbSession,
        requester: str | None = None,
        lab_id: str | None = None,
        experiment_id: str | None = None,
        status: ResourceRequestAllocationStatus | None = None,
    ) -> list[ActiveResourceAllocationRequest]:
        """Get filtered active requests with optimized query building."""
        stmt = select(ResourceAllocationRequestModel)

        filters = []
        if requester:
            filters.append(ResourceAllocationRequestModel.requester == requester)
        if experiment_id:
            filters.append(ResourceAllocationRequestModel.experiment_id == experiment_id)
        if status:
            filters.append(ResourceAllocationRequestModel.status == status)
        if lab_id:
            filters.append(ResourceAllocationRequestModel.resources.contains([{"lab_id": lab_id}]))

        if filters:
            stmt = stmt.where(*filters)

        result = await db.execute(stmt)
        return [ActiveResourceAllocationRequest.model_validate(model) for model in result.scalars()]

    async def _update_request_status(
        self, db: AsyncDbSession, request_id: int, status: ResourceRequestAllocationStatus
    ) -> None:
        """Update request status and allocated_at timestamp if needed."""
        update_values = {"status": status}
        if status == ResourceRequestAllocationStatus.ALLOCATED:
            update_values["allocated_at"] = datetime.now(timezone.utc)

        await db.execute(
            update(ResourceAllocationRequestModel)
            .where(ResourceAllocationRequestModel.id == request_id)
            .values(update_values)
        )

    async def _find_existing_request(
        self, db: AsyncDbSession, request: ResourceAllocationRequest
    ) -> ActiveResourceAllocationRequest | None:
        """Find an existing request matching the given one."""
        # Convert request resources to a sorted, stringified format for comparison
        request_resources = sorted(
            [r.model_dump() for r in request.resources], key=lambda x: (x["id"], x["lab_id"], x["resource_type"])
        )

        # Get all potential matching requests
        stmt = select(ResourceAllocationRequestModel).where(
            ResourceAllocationRequestModel.requester == request.requester,
            ResourceAllocationRequestModel.experiment_id == request.experiment_id,
            ResourceAllocationRequestModel.status.in_(self._ACTIVE_STATUSES),
        )

        result = await db.execute(stmt)
        models = result.scalars().all()

        # Compare resources manually
        for model in models:
            model_resources = sorted(model.resources, key=lambda x: (x["id"], x["lab_id"], x["resource_type"]))
            if model_resources == request_resources:
                return ActiveResourceAllocationRequest.model_validate(model)

        return None

    def _invoke_request_callback(self, active_request: ActiveResourceAllocationRequest) -> None:
        """
        Invoke the allocation callback for an active resource allocation request.
        """
        callback = self._request_callbacks.pop(active_request.id, None)
        if callback:
            callback(active_request)

    async def _delete_completed_and_aborted_requests(self, db: AsyncDbSession) -> None:
        """Remove completed or aborted requests."""
        await db.execute(
            delete(ResourceAllocationRequestModel).where(
                ResourceAllocationRequestModel.status.in_(self._CLEANUP_STATUSES)
            )
        )

    async def _delete_all_requests(self, db: AsyncDbSession) -> None:
        """Delete all requests."""
        await db.execute(delete(ResourceAllocationRequestModel))

    async def _delete_all_allocations(self, db: AsyncDbSession) -> None:
        """Delete all device and container allocations."""
        await self._device_allocation_manager.deallocate_all(db)
        await self._container_allocation_manager.deallocate_all(db)

    @property
    def device_allocation_manager(self) -> DeviceAllocationManager:
        return self._device_allocation_manager

    @property
    def container_allocation_manager(self) -> ContainerAllocationManager:
        return self._container_allocation_manager
