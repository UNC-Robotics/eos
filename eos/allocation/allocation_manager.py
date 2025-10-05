import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Final, TypeAlias, Any

from sqlalchemy import select, update, delete, desc, tuple_, or_

from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.allocation.entities.allocation import Allocation, AllocationModel
from eos.allocation.entities.allocation_request import (
    AllocationRequest,
    ActiveAllocationRequest,
    AllocationRequestStatus,
    AllocationType,
    AllocationRequestModel,
)
from eos.allocation.exceptions import (
    EosAllocationRequestError,
    EosDeviceAllocatedError,
    EosDeviceNotFoundError,
    EosResourceAllocatedError,
    EosResourceNotFoundError,
)
from eos.utils.di.di_container import inject

RequestCallback: TypeAlias = Callable[[ActiveAllocationRequest], None]


class AllocationManager:
    """
    Manages exclusive allocation of devices and resources.
    Handles allocation requests with priority queuing and provides direct allocation methods.
    """

    _ACTIVE_STATUSES: Final = {AllocationRequestStatus.PENDING, AllocationRequestStatus.ALLOCATED}
    _CLEANUP_STATUSES: Final = {AllocationRequestStatus.COMPLETED, AllocationRequestStatus.ABORTED}
    _BATCH_SIZE: Final = 10

    @inject
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        db_interface: AbstractSqlDbInterface,
        batch_size: int = _BATCH_SIZE,
    ):
        self._configuration_manager = configuration_manager
        self._db_interface = db_interface

        # Callbacks for when exclusive allocation requests are processed
        self._request_callbacks: dict[int, Callable[[ActiveAllocationRequest], None]] = {}

        self._lock = asyncio.Lock()
        self._batch_size = batch_size

    async def initialize(self, db: AsyncDbSession) -> None:
        await self._delete_all_requests(db)
        await self._delete_all_allocations(db)
        log.debug("Allocation manager initialized.")

    # ============================================================================
    # Request-based allocation methods
    # ============================================================================

    async def request_allocations(
        self,
        db: AsyncDbSession,
        request: AllocationRequest,
        callback: RequestCallback,
    ) -> ActiveAllocationRequest:
        """Request exclusive allocation of devices and resources."""
        if existing_request := await self._find_existing_request(db, request):
            if existing_request.status in self._ACTIVE_STATUSES:
                self._request_callbacks[existing_request.id] = callback
            return existing_request

        model = AllocationRequestModel(
            requester=request.requester,
            experiment_name=request.experiment_name,
            reason=request.reason,
            priority=request.priority,
            timeout=request.timeout,
            allocations=[allocation.model_dump() for allocation in request.allocations],
            status=AllocationRequestStatus.PENDING,
        )

        db.add(model)
        await db.flush()
        await db.refresh(model)

        active_request = ActiveAllocationRequest.model_validate(model)
        self._request_callbacks[active_request.id] = callback
        return active_request

    async def release_allocations(self, db: AsyncDbSession, request: ActiveAllocationRequest) -> None:
        """Release all allocations for a request."""
        await self._bulk_deallocate_by_request(db, request, AllocationRequestStatus.COMPLETED)

    async def abort_request(self, db: AsyncDbSession, request_id: int) -> None:
        """Abort an active request and release its allocations."""
        if request := await self.get_active_request(db, request_id):
            await self._bulk_deallocate_by_request(db, request, AllocationRequestStatus.ABORTED)
            request = await self.get_active_request(db, request_id)
            self._invoke_request_callback(request)

    async def get_active_request(self, db: AsyncDbSession, request_id: int) -> ActiveAllocationRequest | None:
        """Get an active request."""
        result = await db.execute(select(AllocationRequestModel).where(AllocationRequestModel.id == request_id))
        if model := result.scalar_one_or_none():
            return ActiveAllocationRequest.model_validate(model)
        return None

    async def get_all_active_requests(
        self,
        db: AsyncDbSession,
        requester: str | None = None,
        lab_name: str | None = None,
        experiment_name: str | None = None,
        status: AllocationRequestStatus | None = None,
    ) -> list[ActiveAllocationRequest]:
        """Get filtered active requests with optimized query building."""
        stmt = select(AllocationRequestModel)

        filters = []
        if requester:
            filters.append(AllocationRequestModel.requester == requester)
        if experiment_name:
            filters.append(AllocationRequestModel.experiment_name == experiment_name)
        if status:
            filters.append(AllocationRequestModel.status == status)
        if lab_name:
            filters.append(AllocationRequestModel.allocations.contains([{"lab_name": lab_name}]))

        if filters:
            stmt = stmt.where(*filters)

        result = await db.execute(stmt)
        return [ActiveAllocationRequest.model_validate(model) for model in result.scalars()]

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

    # ============================================================================
    # Direct allocation methods (device)
    # ============================================================================

    async def allocate_device(
        self, db: AsyncDbSession, lab_name: str, device_name: str, owner: str, experiment_name: str | None = None
    ) -> None:
        """Allocate a device to an owner."""
        if await self.is_device_allocated(db, lab_name, device_name):
            raise EosDeviceAllocatedError(f"Device '{device_name}' in lab '{lab_name}' is already allocated.")

        device_config = self._get_device_config(lab_name, device_name)
        allocation_model = AllocationModel(
            allocation_type=AllocationType.DEVICE,
            name=device_name,
            lab_name=lab_name,
            owner=owner,
            item_type=device_config["type"],
            experiment_name=experiment_name,
        )

        db.add(allocation_model)

    async def bulk_allocate_devices(
        self, db: AsyncDbSession, devices: list[tuple[str, str]], owner: str, experiment_name: str | None = None
    ) -> None:
        """Bulk allocate devices in a single operation."""
        if not devices:
            return

        device_configs = []
        for lab_name, device_name in devices:
            device_configs.append(
                {
                    "name": device_name,
                    "lab_name": lab_name,
                    "item_type": self._get_device_config(lab_name, device_name)["type"],
                }
            )

        db.add_all(
            [
                AllocationModel(
                    allocation_type=AllocationType.DEVICE,
                    name=config["name"],
                    lab_name=config["lab_name"],
                    owner=owner,
                    item_type=config["item_type"],
                    experiment_name=experiment_name,
                )
                for config in device_configs
            ]
        )

    async def deallocate_device(self, db: AsyncDbSession, lab_name: str, device_name: str) -> bool:
        """Deallocate a device."""
        result = await db.execute(
            delete(AllocationModel).where(
                AllocationModel.allocation_type == AllocationType.DEVICE,
                AllocationModel.lab_name == lab_name,
                AllocationModel.name == device_name,
            )
        )

        if result.rowcount == 0:
            log.warning(f"Device '{device_name}' in lab '{lab_name}' is not allocated. No action taken.")
            return False

        log.debug(f"Deallocated device '{device_name}' in lab '{lab_name}'.")
        return True

    async def is_device_allocated(self, db: AsyncDbSession, lab_name: str, device_name: str) -> bool:
        """Check if a device is allocated."""
        self._get_device_config(lab_name, device_name)  # Validate device exists
        result = await db.execute(
            select(AllocationModel.name).where(
                AllocationModel.allocation_type == AllocationType.DEVICE,
                AllocationModel.lab_name == lab_name,
                AllocationModel.name == device_name,
            )
        )
        return result.scalar_one_or_none() is not None

    async def bulk_check_devices_allocated(
        self, db: AsyncDbSession, devices: list[tuple[str, str]]
    ) -> set[tuple[str, str]]:
        """Check which devices are already allocated."""
        if not devices:
            return set()

        result = await db.execute(
            select(AllocationModel.lab_name, AllocationModel.name).where(
                AllocationModel.allocation_type == AllocationType.DEVICE,
                tuple_(AllocationModel.lab_name, AllocationModel.name).in_(devices),
            )
        )
        return {(lab, name) for lab, name in result.fetchall()}

    async def get_device_allocation(self, db: AsyncDbSession, lab_name: str, device_name: str) -> Allocation | None:
        """Get the allocation details of a device."""
        self._get_device_config(lab_name, device_name)  # Validate device exists
        result = await db.execute(
            select(AllocationModel).where(
                AllocationModel.allocation_type == AllocationType.DEVICE,
                AllocationModel.lab_name == lab_name,
                AllocationModel.name == device_name,
            )
        )
        if model := result.scalar_one_or_none():
            return Allocation.model_validate(model)
        return None

    async def get_device_allocations(self, db: AsyncDbSession, **filters: Any) -> list[Allocation]:
        """Query device allocations with arbitrary parameters."""
        stmt = select(AllocationModel).where(AllocationModel.allocation_type == AllocationType.DEVICE)
        for key, value in filters.items():
            stmt = stmt.where(getattr(AllocationModel, key) == value)

        result = await db.execute(stmt)
        return [Allocation.model_validate(model) for model in result.scalars()]

    async def bulk_deallocate_devices(self, db: AsyncDbSession, devices: list[tuple[str, str]]) -> None:
        """Bulk deallocate devices with a single query."""
        if not devices:
            return

        if len(devices) == 1:
            lab_name, device_name = devices[0]
            await db.execute(
                delete(AllocationModel).where(
                    AllocationModel.allocation_type == AllocationType.DEVICE,
                    AllocationModel.lab_name == lab_name,
                    AllocationModel.name == device_name,
                )
            )
        else:
            conditions = [
                (AllocationModel.lab_name == lab_name) & (AllocationModel.name == device_name)
                for lab_name, device_name in devices
            ]
            await db.execute(
                delete(AllocationModel).where(
                    AllocationModel.allocation_type == AllocationType.DEVICE, or_(*conditions)
                )
            )

    # ============================================================================
    # Direct allocation methods (resource)
    # ============================================================================

    async def allocate_resource(
        self, db: AsyncDbSession, resource_name: str, owner: str, experiment_name: str | None = None
    ) -> None:
        """Allocate a resource to an owner."""
        if await self.is_resource_allocated(db, resource_name):
            raise EosResourceAllocatedError(f"Resource '{resource_name}' is already allocated.")

        resource_config = self._get_resource_config(resource_name)
        allocation_model = AllocationModel(
            allocation_type=AllocationType.RESOURCE,
            name=resource_name,
            lab_name=None,
            owner=owner,
            item_type=resource_config["type"],
            experiment_name=experiment_name,
        )

        db.add(allocation_model)
        log.debug(f"Allocated resource '{resource_name}' to owner '{owner}'.")

    async def bulk_allocate_resources(
        self, db: AsyncDbSession, resource_names: list[str], owner: str, experiment_name: str | None = None
    ) -> None:
        """Bulk allocate resources in a single operation."""
        if not resource_names:
            return

        resource_configs = []
        for resource_name in resource_names:
            resource_configs.append({"name": resource_name, "type": self._get_resource_config(resource_name)["type"]})

        db.add_all(
            [
                AllocationModel(
                    allocation_type=AllocationType.RESOURCE,
                    name=config["name"],
                    lab_name=None,
                    owner=owner,
                    item_type=config["type"],
                    experiment_name=experiment_name,
                )
                for config in resource_configs
            ]
        )

    async def deallocate_resource(self, db: AsyncDbSession, resource_name: str) -> bool:
        """Deallocate a resource."""
        result = await db.execute(
            delete(AllocationModel).where(
                AllocationModel.allocation_type == AllocationType.RESOURCE,
                AllocationModel.name == resource_name,
            )
        )

        if result.rowcount == 0:
            log.warning(f"Resource '{resource_name}' is not allocated. No action taken.")
            return False

        log.debug(f"Deallocated resource '{resource_name}'.")
        return True

    async def is_resource_allocated(self, db: AsyncDbSession, resource_name: str) -> bool:
        """Check if a resource is allocated."""
        self._get_resource_config(resource_name)  # Validate resource exists
        result = await db.execute(
            select(AllocationModel.name).where(
                AllocationModel.allocation_type == AllocationType.RESOURCE,
                AllocationModel.name == resource_name,
            )
        )
        return result.scalar_one_or_none() is not None

    async def bulk_check_resources_allocated(self, db: AsyncDbSession, resource_names: list[str]) -> set[str]:
        """Check which resources are already allocated."""
        if not resource_names:
            return set()

        result = await db.execute(
            select(AllocationModel.name).where(
                AllocationModel.allocation_type == AllocationType.RESOURCE,
                AllocationModel.name.in_(resource_names),
            )
        )
        return {str(name_) for name_ in result.scalars()}

    async def get_resource_allocation(self, db: AsyncDbSession, resource_name: str) -> Allocation | None:
        """Get the allocation details of a resource."""
        self._get_resource_config(resource_name)  # Validate resource exists
        result = await db.execute(
            select(AllocationModel).where(
                AllocationModel.allocation_type == AllocationType.RESOURCE,
                AllocationModel.name == resource_name,
            )
        )
        if model := result.scalar_one_or_none():
            return Allocation.model_validate(model)
        return None

    async def get_resource_allocations(self, db: AsyncDbSession, **filters: Any) -> list[Allocation]:
        """Query resource allocations with arbitrary parameters."""
        stmt = select(AllocationModel).where(AllocationModel.allocation_type == AllocationType.RESOURCE)
        for key, value in filters.items():
            stmt = stmt.where(getattr(AllocationModel, key) == value)

        result = await db.execute(stmt)
        return [Allocation.model_validate(model) for model in result.scalars()]

    async def bulk_deallocate_resources(self, db: AsyncDbSession, resource_names: list[str]) -> None:
        """Bulk deallocate resources with a single query."""
        if not resource_names:
            return

        await db.execute(
            delete(AllocationModel).where(
                AllocationModel.allocation_type == AllocationType.RESOURCE,
                AllocationModel.name.in_(resource_names),
            )
        )

    # ============================================================================
    # General allocation methods
    # ============================================================================

    async def get_all_allocations(
        self,
        db: AsyncDbSession,
        allocation_type: AllocationType | None = None,
        **filters: Any,
    ) -> list[Allocation]:
        """Get all allocations, optionally filtered by type and other parameters."""
        stmt = select(AllocationModel)

        if allocation_type:
            stmt = stmt.where(AllocationModel.allocation_type == allocation_type)

        for key, value in filters.items():
            stmt = stmt.where(getattr(AllocationModel, key) == value)

        result = await db.execute(stmt)
        return [Allocation.model_validate(model) for model in result.scalars()]

    async def deallocate_all_by_owner(self, db: AsyncDbSession, owner: str) -> None:
        """Deallocate all devices and resources allocated to an owner."""
        result = await db.execute(delete(AllocationModel).where(AllocationModel.owner == owner))

        if result.rowcount == 0:
            log.warning(f"Owner '{owner}' has no allocations. No action taken.")
        else:
            log.debug(f"Deallocated {result.rowcount} allocations for owner '{owner}'.")

    async def get_all_unallocated_devices(self, db: AsyncDbSession) -> list[tuple[str, str]]:
        """Get all unallocated devices as (lab_name, device_name) tuples."""
        result = await db.execute(
            select(AllocationModel.lab_name, AllocationModel.name).where(
                AllocationModel.allocation_type == AllocationType.DEVICE
            )
        )
        allocated_devices = {(lab, name) for lab, name in result.fetchall()}

        all_devices = {
            (lab_name, device_name)
            for lab_name, lab_config in self._configuration_manager.labs.items()
            for device_name in lab_config.devices
        }

        return list(all_devices - allocated_devices)

    async def get_all_unallocated_resources(self, db: AsyncDbSession) -> list[str]:
        """Get all unallocated resources."""
        result = await db.execute(
            select(AllocationModel.name).where(AllocationModel.allocation_type == AllocationType.RESOURCE)
        )
        allocated_resources = {str(name_) for name_ in result.scalars().all()}

        all_resources = {
            resource_name
            for lab_config in self._configuration_manager.labs.values()
            for resource_name in lab_config.resources
        }

        return list(all_resources - allocated_resources)

    # ============================================================================
    # Private helper methods
    # ============================================================================

    async def _process_request_batch(self, db: AsyncDbSession, requests: list[ActiveAllocationRequest]) -> None:
        """Process a batch of requests of the same priority."""
        for request in requests:
            if request.status != AllocationRequestStatus.PENDING:
                continue

            if self._is_request_timed_out(request, datetime.now(timezone.utc)):
                await self._handle_timeout(db, request)
                continue

            if await self._try_allocate(db, request):
                self._invoke_request_callback(request)

    async def _handle_timeout(self, db: AsyncDbSession, request: ActiveAllocationRequest) -> None:
        request_time = (
            request.created_at.replace(tzinfo=timezone.utc) if not request.created_at.tzinfo else request.created_at
        )
        log.warning(
            f"Exclusive allocation request {request.id} for {request.requester} "
            f"timed out after {(datetime.now(timezone.utc) - request_time).total_seconds():.1f}s"
        )
        await self.abort_request(db, request.id)
        self._invoke_request_callback(request)

    async def _try_allocate(self, db: AsyncDbSession, request: ActiveAllocationRequest) -> bool:
        """Attempt to allocate all devices and resources for a request."""
        try:
            if not await self._check_request_allocations_available(db, request):
                return False

            await self._perform_request_allocations(db, request)
            await self._update_request_status(db, request.id, AllocationRequestStatus.ALLOCATED)
            request.status = AllocationRequestStatus.ALLOCATED
            return True

        except Exception as e:
            await self.abort_request(db, request.id)
            raise EosAllocationRequestError(f"Failed to allocate for request {request.id}: {e!s}") from e

    async def _check_request_allocations_available(self, db: AsyncDbSession, request: ActiveAllocationRequest) -> bool:
        """Check if all allocations in the request are available."""
        devices = []
        resources = []

        for allocation in request.allocations:
            if allocation.allocation_type == AllocationType.DEVICE:
                devices.append((allocation.lab_name, allocation.name))
            elif allocation.allocation_type == AllocationType.RESOURCE:
                resources.append(allocation.name)

        if devices:
            allocated_devices = await self.bulk_check_devices_allocated(db, devices)
            if allocated_devices:
                return False

        if resources:
            allocated_resources = await self.bulk_check_resources_allocated(db, resources)
            if allocated_resources:
                return False

        return True

    async def _perform_request_allocations(self, db: AsyncDbSession, request: ActiveAllocationRequest) -> None:
        """Perform all allocations for a request."""
        devices = []
        resources = []

        for allocation in request.allocations:
            if allocation.allocation_type == AllocationType.DEVICE:
                devices.append((allocation.lab_name, allocation.name))
            elif allocation.allocation_type == AllocationType.RESOURCE:
                resources.append(allocation.name)

        if devices:
            await self.bulk_allocate_devices(db, devices, request.requester, experiment_name=request.experiment_name)

        if resources:
            await self.bulk_allocate_resources(
                db, resources, request.requester, experiment_name=request.experiment_name
            )

    async def _bulk_deallocate_by_request(
        self,
        db: AsyncDbSession,
        request: ActiveAllocationRequest,
        new_status: AllocationRequestStatus,
    ) -> None:
        """Bulk deallocate and update request status."""
        devices = []
        resources = []

        for allocation in request.allocations:
            if allocation.allocation_type == AllocationType.DEVICE:
                devices.append((allocation.lab_name, allocation.name))
            elif allocation.allocation_type == AllocationType.RESOURCE:
                resources.append(allocation.name)

        if devices:
            await self.bulk_deallocate_devices(db, devices)

        if resources:
            await self.bulk_deallocate_resources(db, resources)

        await self._update_request_status(db, request.id, new_status)

    def _is_request_timed_out(self, request: ActiveAllocationRequest, current_time: datetime) -> bool:
        """Check if a request has timed out."""
        request_time = (
            request.created_at.replace(tzinfo=timezone.utc) if not request.created_at.tzinfo else request.created_at
        )
        return (current_time - request_time).total_seconds() > request.timeout

    async def _get_all_active_requests_prioritized(self, db: AsyncDbSession) -> list[ActiveAllocationRequest]:
        """Get pending requests ordered by priority."""
        stmt = (
            select(AllocationRequestModel)
            .where(AllocationRequestModel.status == AllocationRequestStatus.PENDING)
            .order_by(desc(AllocationRequestModel.priority))
        )

        result = await db.execute(stmt)
        return [ActiveAllocationRequest.model_validate(model) for model in result.scalars()]

    async def _update_request_status(
        self, db: AsyncDbSession, request_id: int, status: AllocationRequestStatus
    ) -> None:
        """Update request status and allocated_at timestamp if needed."""
        update_values = {"status": status}
        if status == AllocationRequestStatus.ALLOCATED:
            update_values["allocated_at"] = datetime.now(timezone.utc)

        await db.execute(
            update(AllocationRequestModel).where(AllocationRequestModel.id == request_id).values(update_values)
        )

    async def _find_existing_request(
        self, db: AsyncDbSession, request: AllocationRequest
    ) -> ActiveAllocationRequest | None:
        """Find an existing request matching the given one."""
        request_allocations = sorted(
            [a.model_dump() for a in request.allocations],
            key=lambda x: (x["name"], x["lab_name"], x["allocation_type"]),
        )

        stmt = select(AllocationRequestModel).where(
            AllocationRequestModel.requester == request.requester,
            AllocationRequestModel.experiment_name == request.experiment_name,
            AllocationRequestModel.status.in_(self._ACTIVE_STATUSES),
        )

        result = await db.execute(stmt)
        models = result.scalars().all()

        for model in models:
            model_allocations = sorted(
                model.allocations, key=lambda x: (x["name"], x["lab_name"], x["allocation_type"])
            )
            if model_allocations == request_allocations:
                return ActiveAllocationRequest.model_validate(model)

        return None

    def _invoke_request_callback(self, active_request: ActiveAllocationRequest) -> None:
        """Invoke the allocation callback for an active exclusive allocation request."""
        callback = self._request_callbacks.pop(active_request.id, None)
        if callback:
            callback(active_request)

    async def _delete_completed_and_aborted_requests(self, db: AsyncDbSession) -> None:
        """Remove completed or aborted requests."""
        await db.execute(
            delete(AllocationRequestModel).where(AllocationRequestModel.status.in_(self._CLEANUP_STATUSES))
        )

    async def _delete_all_requests(self, db: AsyncDbSession) -> None:
        """Delete all requests."""
        await db.execute(delete(AllocationRequestModel))

    async def _delete_all_allocations(self, db: AsyncDbSession) -> None:
        """Delete all device and resource allocations."""
        await db.execute(delete(AllocationModel))

    def _get_device_config(self, lab_name: str, device_name: str) -> dict[str, Any]:
        """Get device configuration from the configuration manager."""
        lab = self._configuration_manager.labs.get(lab_name)
        if not lab:
            raise EosDeviceNotFoundError(f"Lab '{lab_name}' not found in the configuration.")

        if device_config := lab.devices.get(device_name):
            return {
                "lab_name": lab.name,
                "type": device_config.type,
            }

        raise EosDeviceNotFoundError(f"Device '{device_name}' in lab '{lab_name}' not found in the configuration.")

    def _get_resource_config(self, resource_name: str) -> dict:
        """Get the configuration for a resource."""
        for lab_name, lab_config in self._configuration_manager.labs.items():
            if resource_name in lab_config.resources:
                resource_config = lab_config.resources[resource_name]
                return {
                    "type": resource_config.type,
                    "lab": lab_name,
                }

        raise EosResourceNotFoundError(f"Resource '{resource_name}' not found in the configuration.")
