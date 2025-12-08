import asyncio
from collections.abc import Callable
from datetime import datetime, UTC
from typing import Final, TypeAlias, Any

from sqlalchemy import select, update, delete, desc, or_

from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.allocation.entities.device_allocation import DeviceAllocation, DeviceAllocationModel
from eos.allocation.entities.resource_allocation import ResourceAllocation, ResourceAllocationModel
from eos.allocation.entities.allocation_request import (
    AllocationRequest,
    ActiveAllocationRequest,
    AllocationRequestStatus,
    AllocationType,
    AllocationRequestModel,
    AllocationRequestItem,
)
from eos.allocation.entities.allocation_request_device import AllocationRequestDeviceModel
from eos.allocation.entities.allocation_request_resource import AllocationRequestResourceModel
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
    """Manages exclusive allocation of devices and resources."""

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
        self._request_callbacks: dict[int, Callable[[ActiveAllocationRequest], None]] = {}
        self._lock = asyncio.Lock()
        self._batch_size = batch_size

        # In-memory allocation cache (write-through to DB)
        self._device_allocations: dict[tuple[str, str], DeviceAllocation] = {}
        self._resource_allocations: dict[str, ResourceAllocation] = {}

    async def initialize(self, db: AsyncDbSession) -> None:
        await self._delete_all_requests(db)
        await self._delete_all_allocations(db)
        self._device_allocations.clear()
        self._resource_allocations.clear()
        log.debug("Allocation manager initialized.")

    async def request_allocations(
        self, db: AsyncDbSession, request: AllocationRequest, callback: RequestCallback
    ) -> ActiveAllocationRequest:
        """Request exclusive allocation of devices and resources."""
        if existing := await self._find_existing_request(db, request):
            if existing.status in self._ACTIVE_STATUSES:
                self._request_callbacks[existing.id] = callback
            return existing

        model = AllocationRequestModel(
            requester=request.requester,
            experiment_name=request.experiment_name,
            reason=request.reason,
            priority=request.priority,
            timeout=request.timeout,
            status=AllocationRequestStatus.PENDING,
        )
        db.add(model)
        await db.flush()
        await db.refresh(model)

        # Insert allocation items into separate tables
        for alloc in request.allocations:
            if alloc.allocation_type == AllocationType.DEVICE:
                db.add(
                    AllocationRequestDeviceModel(
                        request_id=model.id,
                        name=alloc.name,
                        lab_name=alloc.lab_name,
                    )
                )
            elif alloc.allocation_type == AllocationType.RESOURCE:
                db.add(
                    AllocationRequestResourceModel(
                        request_id=model.id,
                        name=alloc.name,
                        lab_name=alloc.lab_name,
                    )
                )

        active = await self._model_to_active_request(db, model)
        self._request_callbacks[active.id] = callback
        return active

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
        result = await db.execute(select(AllocationRequestModel).where(AllocationRequestModel.id == request_id))
        if m := result.scalar_one_or_none():
            return await self._model_to_active_request(db, m)
        return None

    async def get_all_active_requests(
        self,
        db: AsyncDbSession,
        requester: str | None = None,
        lab_name: str | None = None,
        experiment_name: str | None = None,
        status: AllocationRequestStatus | None = None,
    ) -> list[ActiveAllocationRequest]:
        stmt = select(AllocationRequestModel)
        filters = []
        if requester:
            filters.append(AllocationRequestModel.requester == requester)
        if experiment_name:
            filters.append(AllocationRequestModel.experiment_name == experiment_name)
        if status:
            filters.append(AllocationRequestModel.status == status)
        if lab_name:
            # Use subquery to filter by lab_name in related tables
            device_subquery = select(AllocationRequestDeviceModel.request_id).where(
                AllocationRequestDeviceModel.lab_name == lab_name
            )
            resource_subquery = select(AllocationRequestResourceModel.request_id).where(
                AllocationRequestResourceModel.lab_name == lab_name
            )
            filters.append(
                or_(
                    AllocationRequestModel.id.in_(device_subquery),
                    AllocationRequestModel.id.in_(resource_subquery),
                )
            )
        if filters:
            stmt = stmt.where(*filters)
        result = await db.execute(stmt)
        return [await self._model_to_active_request(db, m) for m in result.scalars()]

    async def process_requests(self, db: AsyncDbSession) -> None:
        """Process pending allocation requests in priority order."""
        async with self._lock:
            await self._delete_completed_and_aborted_requests(db)
            active_requests = await self._get_all_active_requests_prioritized(db)

            priority_groups: dict[int, list[ActiveAllocationRequest]] = {}
            for req in active_requests:
                priority_groups.setdefault(req.priority, []).append(req)

            for priority in sorted(priority_groups.keys(), reverse=True):
                for i in range(0, len(priority_groups[priority]), self._batch_size):
                    batch = priority_groups[priority][i : i + self._batch_size]
                    await self._process_request_batch(db, batch)

    async def allocate_device(
        self, db: AsyncDbSession, lab_name: str, device_name: str, owner: str, experiment_name: str | None = None
    ) -> None:
        if await self.is_device_allocated(db, lab_name, device_name):
            raise EosDeviceAllocatedError(f"Device '{device_name}' in lab '{lab_name}' is already allocated.")
        await self.bulk_allocate_devices(db, [(lab_name, device_name)], owner, experiment_name)

    async def bulk_allocate_devices(
        self, db: AsyncDbSession, devices: list[tuple[str, str]], owner: str, experiment_name: str | None = None
    ) -> None:
        if not devices:
            return

        allocations = []
        for lab_name, device_name in devices:
            self._validate_device_exists(lab_name, device_name)
            allocations.append(
                DeviceAllocation(
                    name=device_name,
                    lab_name=lab_name,
                    owner=owner,
                    experiment_name=experiment_name,
                )
            )

        # Delete any existing allocations first to handle cache/db sync issues
        # and ensure idempotency with the unique constraint
        if len(devices) == 1:
            lab_name, device_name = devices[0]
            await db.execute(
                delete(DeviceAllocationModel).where(
                    DeviceAllocationModel.lab_name == lab_name,
                    DeviceAllocationModel.name == device_name,
                )
            )
        else:
            conditions = [
                (DeviceAllocationModel.lab_name == lab) & (DeviceAllocationModel.name == dev) for lab, dev in devices
            ]
            await db.execute(delete(DeviceAllocationModel).where(or_(*conditions)))
        await db.flush()

        db.add_all([DeviceAllocationModel(**a.model_dump(exclude={"created_at"})) for a in allocations])
        await db.flush()
        for alloc in allocations:
            self._device_allocations[(alloc.lab_name, alloc.name)] = alloc

    async def deallocate_device(self, db: AsyncDbSession, lab_name: str, device_name: str) -> bool:
        self._device_allocations.pop((lab_name, device_name), None)
        result = await db.execute(
            delete(DeviceAllocationModel).where(
                DeviceAllocationModel.lab_name == lab_name,
                DeviceAllocationModel.name == device_name,
            )
        )
        if result.rowcount == 0:
            log.warning(f"Device '{device_name}' in lab '{lab_name}' is not allocated.")
            return False
        return True

    async def bulk_deallocate_devices(self, db: AsyncDbSession, devices: list[tuple[str, str]]) -> None:
        if not devices:
            return
        for lab_name, device_name in devices:
            self._device_allocations.pop((lab_name, device_name), None)

        if len(devices) == 1:
            lab_name, device_name = devices[0]
            await db.execute(
                delete(DeviceAllocationModel).where(
                    DeviceAllocationModel.lab_name == lab_name,
                    DeviceAllocationModel.name == device_name,
                )
            )
        else:
            conditions = [
                (DeviceAllocationModel.lab_name == lab) & (DeviceAllocationModel.name == dev) for lab, dev in devices
            ]
            await db.execute(delete(DeviceAllocationModel).where(or_(*conditions)))

    async def is_device_allocated(self, db: AsyncDbSession, lab_name: str, device_name: str) -> bool:
        self._validate_device_exists(lab_name, device_name)
        return (lab_name, device_name) in self._device_allocations

    async def bulk_check_devices_allocated(
        self, db: AsyncDbSession, devices: list[tuple[str, str]]
    ) -> set[tuple[str, str]]:
        return {d for d in devices if d in self._device_allocations} if devices else set()

    async def get_device_allocation(
        self, db: AsyncDbSession, lab_name: str, device_name: str
    ) -> DeviceAllocation | None:
        self._validate_device_exists(lab_name, device_name)
        return self._device_allocations.get((lab_name, device_name))

    async def get_device_allocations(self, db: AsyncDbSession, **filters: Any) -> list[DeviceAllocation]:
        stmt = select(DeviceAllocationModel)
        for key, value in filters.items():
            stmt = stmt.where(getattr(DeviceAllocationModel, key) == value)
        result = await db.execute(stmt)
        return [DeviceAllocation.model_validate(m) for m in result.scalars()]

    async def allocate_resource(
        self, db: AsyncDbSession, resource_name: str, owner: str, experiment_name: str | None = None
    ) -> None:
        if await self.is_resource_allocated(db, resource_name):
            raise EosResourceAllocatedError(f"Resource '{resource_name}' is already allocated.")
        await self.bulk_allocate_resources(db, [resource_name], owner, experiment_name)

    async def bulk_allocate_resources(
        self, db: AsyncDbSession, resource_names: list[str], owner: str, experiment_name: str | None = None
    ) -> None:
        if not resource_names:
            return

        allocations = []
        for name in resource_names:
            self._validate_resource_exists(name)
            allocations.append(
                ResourceAllocation(
                    name=name,
                    owner=owner,
                    experiment_name=experiment_name,
                )
            )

        # Delete any existing allocations first to handle cache/db sync issues
        # and ensure idempotency with the unique constraint
        await db.execute(delete(ResourceAllocationModel).where(ResourceAllocationModel.name.in_(resource_names)))

        db.add_all([ResourceAllocationModel(**a.model_dump(exclude={"created_at"})) for a in allocations])
        await db.flush()

        for alloc in allocations:
            self._resource_allocations[alloc.name] = alloc

    async def deallocate_resource(self, db: AsyncDbSession, resource_name: str) -> bool:
        self._resource_allocations.pop(resource_name, None)
        result = await db.execute(delete(ResourceAllocationModel).where(ResourceAllocationModel.name == resource_name))
        if result.rowcount == 0:
            log.warning(f"Resource '{resource_name}' is not allocated.")
            return False
        return True

    async def bulk_deallocate_resources(self, db: AsyncDbSession, resource_names: list[str]) -> None:
        if not resource_names:
            return
        for name in resource_names:
            self._resource_allocations.pop(name, None)
        await db.execute(delete(ResourceAllocationModel).where(ResourceAllocationModel.name.in_(resource_names)))

    async def is_resource_allocated(self, db: AsyncDbSession, resource_name: str) -> bool:
        self._validate_resource_exists(resource_name)
        return resource_name in self._resource_allocations

    async def bulk_check_resources_allocated(self, db: AsyncDbSession, resource_names: list[str]) -> set[str]:
        return {r for r in resource_names if r in self._resource_allocations} if resource_names else set()

    async def get_resource_allocation(self, db: AsyncDbSession, resource_name: str) -> ResourceAllocation | None:
        self._validate_resource_exists(resource_name)
        return self._resource_allocations.get(resource_name)

    async def get_resource_allocations(self, db: AsyncDbSession, **filters: Any) -> list[ResourceAllocation]:
        stmt = select(ResourceAllocationModel)
        for key, value in filters.items():
            stmt = stmt.where(getattr(ResourceAllocationModel, key) == value)
        result = await db.execute(stmt)
        return [ResourceAllocation.model_validate(m) for m in result.scalars()]

    async def deallocate_all_by_owner(self, db: AsyncDbSession, owner: str) -> None:
        self._device_allocations = {k: v for k, v in self._device_allocations.items() if v.owner != owner}
        self._resource_allocations = {k: v for k, v in self._resource_allocations.items() if v.owner != owner}
        device_result = await db.execute(delete(DeviceAllocationModel).where(DeviceAllocationModel.owner == owner))
        resource_result = await db.execute(
            delete(ResourceAllocationModel).where(ResourceAllocationModel.owner == owner)
        )
        if device_result.rowcount == 0 and resource_result.rowcount == 0:
            log.warning(f"Owner '{owner}' has no allocations.")

    async def get_all_unallocated_devices(self, db: AsyncDbSession) -> list[tuple[str, str]]:
        all_devices = {
            (lab_name, device_name)
            for lab_name, lab in self._configuration_manager.labs.items()
            for device_name in lab.devices
        }
        return list(all_devices - set(self._device_allocations.keys()))

    async def get_all_unallocated_resources(self, db: AsyncDbSession) -> list[str]:
        all_resources = {
            resource_name for lab in self._configuration_manager.labs.values() for resource_name in lab.resources
        }
        return list(all_resources - set(self._resource_allocations.keys()))

    async def _process_request_batch(self, db: AsyncDbSession, requests: list[ActiveAllocationRequest]) -> None:
        now = datetime.now(UTC)
        for request in requests:
            if request.status != AllocationRequestStatus.PENDING:
                continue
            if self._is_request_timed_out(request, now):
                await self._handle_timeout(db, request)
                continue
            if await self._try_allocate(db, request):
                self._invoke_request_callback(request)

    async def _handle_timeout(self, db: AsyncDbSession, request: ActiveAllocationRequest) -> None:
        created = request.created_at.replace(tzinfo=UTC) if not request.created_at.tzinfo else request.created_at
        elapsed = (datetime.now(UTC) - created).total_seconds()
        log.warning(f"Allocation request {request.id} for {request.requester} timed out after {elapsed:.1f}s")
        await self.abort_request(db, request.id)
        self._invoke_request_callback(request)

    async def _try_allocate(self, db: AsyncDbSession, request: ActiveAllocationRequest) -> bool:
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
        devices, resources = [], []
        for alloc in request.allocations:
            if alloc.allocation_type == AllocationType.DEVICE:
                devices.append((alloc.lab_name, alloc.name))
            elif alloc.allocation_type == AllocationType.RESOURCE:
                resources.append(alloc.name)

        if devices and await self.bulk_check_devices_allocated(db, devices):
            return False
        return not (resources and await self.bulk_check_resources_allocated(db, resources))

    async def _perform_request_allocations(self, db: AsyncDbSession, request: ActiveAllocationRequest) -> None:
        devices, resources = [], []
        for alloc in request.allocations:
            if alloc.allocation_type == AllocationType.DEVICE:
                devices.append((alloc.lab_name, alloc.name))
            elif alloc.allocation_type == AllocationType.RESOURCE:
                resources.append(alloc.name)

        if devices:
            await self.bulk_allocate_devices(db, devices, request.requester, request.experiment_name)
        if resources:
            await self.bulk_allocate_resources(db, resources, request.requester, request.experiment_name)

    async def _bulk_deallocate_by_request(
        self, db: AsyncDbSession, request: ActiveAllocationRequest, new_status: AllocationRequestStatus
    ) -> None:
        devices, resources = [], []
        for alloc in request.allocations:
            if alloc.allocation_type == AllocationType.DEVICE:
                devices.append((alloc.lab_name, alloc.name))
            elif alloc.allocation_type == AllocationType.RESOURCE:
                resources.append(alloc.name)

        if devices:
            await self.bulk_deallocate_devices(db, devices)
        if resources:
            await self.bulk_deallocate_resources(db, resources)
        await self._update_request_status(db, request.id, new_status)

    def _is_request_timed_out(self, request: ActiveAllocationRequest, now: datetime) -> bool:
        created = request.created_at.replace(tzinfo=UTC) if not request.created_at.tzinfo else request.created_at
        return (now - created).total_seconds() > request.timeout

    async def _get_all_active_requests_prioritized(self, db: AsyncDbSession) -> list[ActiveAllocationRequest]:
        stmt = (
            select(AllocationRequestModel)
            .where(AllocationRequestModel.status == AllocationRequestStatus.PENDING)
            .order_by(desc(AllocationRequestModel.priority))
        )
        result = await db.execute(stmt)
        return [await self._model_to_active_request(db, m) for m in result.scalars()]

    async def _update_request_status(
        self, db: AsyncDbSession, request_id: int, status: AllocationRequestStatus
    ) -> None:
        values: dict[str, Any] = {"status": status}
        if status == AllocationRequestStatus.ALLOCATED:
            values["allocated_at"] = datetime.now(UTC)
        await db.execute(update(AllocationRequestModel).where(AllocationRequestModel.id == request_id).values(values))

    async def _find_existing_request(
        self, db: AsyncDbSession, request: AllocationRequest
    ) -> ActiveAllocationRequest | None:
        request_allocs = sorted(
            [(a.name, a.lab_name, a.allocation_type.value) for a in request.allocations],
        )
        stmt = select(AllocationRequestModel).where(
            AllocationRequestModel.requester == request.requester,
            AllocationRequestModel.experiment_name == request.experiment_name,
            AllocationRequestModel.status.in_(self._ACTIVE_STATUSES),
        )
        result = await db.execute(stmt)
        for model in result.scalars():
            active = await self._model_to_active_request(db, model)
            model_allocs = sorted(
                [(a.name, a.lab_name, a.allocation_type.value) for a in active.allocations],
            )
            if model_allocs == request_allocs:
                return active
        return None

    async def _model_to_active_request(
        self, db: AsyncDbSession, model: AllocationRequestModel
    ) -> ActiveAllocationRequest:
        """Convert a database model to ActiveAllocationRequest by loading allocations from related tables."""
        # Load device allocations
        device_result = await db.execute(
            select(AllocationRequestDeviceModel).where(AllocationRequestDeviceModel.request_id == model.id)
        )
        # Load resource allocations
        resource_result = await db.execute(
            select(AllocationRequestResourceModel).where(AllocationRequestResourceModel.request_id == model.id)
        )

        allocations: list[AllocationRequestItem] = []
        for device in device_result.scalars():
            allocations.append(
                AllocationRequestItem(
                    name=device.name,
                    lab_name=device.lab_name,
                    allocation_type=AllocationType.DEVICE,
                )
            )
        for resource in resource_result.scalars():
            allocations.append(
                AllocationRequestItem(
                    name=resource.name,
                    lab_name=resource.lab_name,
                    allocation_type=AllocationType.RESOURCE,
                )
            )

        return ActiveAllocationRequest(
            id=model.id,
            requester=model.requester,
            allocations=allocations,
            experiment_name=model.experiment_name,
            reason=model.reason,
            priority=model.priority,
            timeout=model.timeout,
            status=model.status,
            created_at=model.created_at,
        )

    def _invoke_request_callback(self, request: ActiveAllocationRequest) -> None:
        if callback := self._request_callbacks.pop(request.id, None):
            callback(request)

    async def _delete_completed_and_aborted_requests(self, db: AsyncDbSession) -> None:
        await db.execute(
            delete(AllocationRequestModel).where(AllocationRequestModel.status.in_(self._CLEANUP_STATUSES))
        )

    async def _delete_all_requests(self, db: AsyncDbSession) -> None:
        await db.execute(delete(AllocationRequestModel))

    async def _delete_all_allocations(self, db: AsyncDbSession) -> None:
        await db.execute(delete(DeviceAllocationModel))
        await db.execute(delete(ResourceAllocationModel))

    def _validate_device_exists(self, lab_name: str, device_name: str) -> None:
        if not (lab := self._configuration_manager.labs.get(lab_name)):
            raise EosDeviceNotFoundError(f"Lab '{lab_name}' not found.")
        if device_name not in lab.devices:
            raise EosDeviceNotFoundError(f"Device '{device_name}' in lab '{lab_name}' not found.")

    def _validate_resource_exists(self, resource_name: str) -> None:
        for lab in self._configuration_manager.labs.values():
            if resource_name in lab.resources:
                return
        raise EosResourceNotFoundError(f"Resource '{resource_name}' not found.")
