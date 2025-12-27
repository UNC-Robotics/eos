import asyncio
import time
from abc import ABC
from dataclasses import dataclass

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task_def import DeviceAssignmentDef, TaskDef
from eos.configuration.experiment_graph import ExperimentGraph
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.devices.device_manager import DeviceManager
from eos.devices.entities.device import DeviceStatus
from eos.experiments.experiment_manager import ExperimentManager
from eos.logging.logger import log
from eos.allocation.entities.allocation_request import (
    ActiveAllocationRequest,
    AllocationRequest,
    AllocationType,
    AllocationRequestStatus,
)
from eos.allocation.exceptions import EosAllocationRequestError
from eos.allocation.allocation_manager import AllocationManager
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerRegistrationError
from eos.tasks.task_input_resolver import TaskInputResolver
from eos.tasks.task_manager import TaskManager
from eos.utils.async_rlock import AsyncRLock


@dataclass
class AllocationCheckResult:
    """Result of checking an existing allocation request."""

    success: bool
    request: ActiveAllocationRequest | None
    should_continue: bool


class BaseScheduler(AbstractScheduler, ABC):
    """
    This base scheduler contains common logic shared by multiple scheduler implementations.
    """

    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        experiment_manager: ExperimentManager,
        task_manager: TaskManager,
        device_manager: DeviceManager,
        allocation_manager: AllocationManager,
    ):
        self._configuration_manager = configuration_manager
        self._experiment_manager = experiment_manager
        self._task_input_resolver = TaskInputResolver(task_manager, experiment_manager)
        self._device_manager = device_manager
        self._allocation_manager = allocation_manager

        # Mapping: experiment_name -> (experiment_type, experiment_graph)
        self._registered_experiments: dict[str, tuple[str, ExperimentGraph]] = {}

        # Mapping: experiment_name -> {task_name -> ActiveAllocationRequest}
        self._allocated_resources: dict[str, dict[str, ActiveAllocationRequest]] = {}

        # Fast O(1) conflict indices for pending/active allocation requests managed by this scheduler.
        # Keys:
        #   - device: (lab_name, device_name) -> (experiment_name, task_name)
        #   - resource: resource_name -> (experiment_name, task_name)
        self._pending_device_index: dict[tuple[str, str], tuple[str, str]] = {}
        self._pending_resource_index: dict[str, tuple[str, str]] = {}

        # Hot caches (with TTL) to avoid rebuilding pools every request.
        self._active_device_cache: dict[str, list[tuple[str, str]]] = {}
        self._active_device_cache_expiry: float = 0.0
        self._active_device_cache_ttl: float = 0.5  # seconds; tunable via update_parameters

        # Config-derived caches (invalidate on demand)
        self._resources_by_type_cache: dict[str, list[str]] | None = None
        self._resources_by_type_with_labs_cache: dict[str, list[tuple[str, str]]] | None = None

        self._lock = AsyncRLock()

    async def register_experiment(
        self, experiment_name: str, experiment_type: str, experiment_graph: ExperimentGraph
    ) -> None:
        """
        Register an experiment by checking that the experiment type exists and storing its graph.
        """
        async with self._lock:
            if experiment_type not in self._configuration_manager.experiments:
                raise EosSchedulerRegistrationError(f"Experiment type '{experiment_type}' does not exist.")
            self._registered_experiments[experiment_name] = (experiment_type, experiment_graph)

    async def unregister_experiment(self, db: AsyncDbSession, experiment_name: str) -> None:
        """
        Unregister an experiment and release its allocations.
        """
        async with self._lock:
            if experiment_name not in self._registered_experiments:
                raise EosSchedulerRegistrationError(f"Experiment {experiment_name} is not registered.")
            del self._registered_experiments[experiment_name]
            await self._release_experiment_allocations(db, experiment_name)

    async def _release_task_allocations(self, db: AsyncDbSession, experiment_name: str, task_name: str) -> None:
        """
        Release allocations for a given task.
        """
        active_request = self._allocated_resources.get(experiment_name, {}).pop(task_name, None)
        if active_request:
            # Drop from indices first, regardless of DB outcome
            self._unregister_allocation_from_indices(active_request)
            try:
                await self._allocation_manager.release_allocations(db, active_request)
            except EosAllocationRequestError as e:
                log.error(f"Error releasing resources for task {task_name} in experiment {experiment_name}: {e!s}")

    async def _release_experiment_allocations(self, db: AsyncDbSession, experiment_name: str) -> None:
        """
        Release allocations for all tasks belonging to an experiment.
        """
        task_names = list(self._allocated_resources.get(experiment_name, {}).keys())
        for task_name in task_names:
            await self._release_task_allocations(db, experiment_name, task_name)
        self._allocated_resources.pop(experiment_name, None)

    def _invalidate_device_cache(self) -> None:
        """Invalidate the active device pool cache."""
        self._active_device_cache_expiry = 0.0

    def _invalidate_resource_caches(self) -> None:
        """Invalidate the resource type caches."""
        self._resources_by_type_cache = None
        self._resources_by_type_with_labs_cache = None

    def _invalidate_all_caches(self) -> None:
        """Invalidate all scheduler caches (devices and resources)."""
        self._invalidate_device_cache()
        self._invalidate_resource_caches()

    async def _compute_active_devices_by_type(self, db: AsyncDbSession) -> dict[str, list[tuple[str, str]]]:
        """
        Build a map of active (lab_name, device_name) by device type from configuration + device statuses.
        """
        devices_by_type: dict[str, list[tuple[str, str]]] = {}
        labs = getattr(self._configuration_manager, "labs", {})
        for lab_name, lab_cfg in labs.items():
            for device_name, dev_cfg in lab_cfg.devices.items():
                try:
                    device = await self._device_manager.get_device(db, lab_name, device_name)
                    if device.status == DeviceStatus.INACTIVE:
                        continue
                except Exception as e:
                    log.debug(f"Failed to get device {device_name} in lab {lab_name}, skipping: {e}")
                    continue
                devices_by_type.setdefault(dev_cfg.type, []).append((lab_name, device_name))
        return devices_by_type

    async def _active_devices_by_type(self, db: AsyncDbSession) -> dict[str, list[tuple[str, str]]]:
        """
        Cached active device pool by type with a short TTL to avoid excessive DB I/O
        in the spin loop. The TTL is tunable via update_parameters().
        """
        now = time.monotonic()
        if self._active_device_cache and now < self._active_device_cache_expiry:
            return self._active_device_cache
        devices_by_type = await self._compute_active_devices_by_type(db)
        self._active_device_cache = devices_by_type
        self._active_device_cache_expiry = now + self._active_device_cache_ttl
        return devices_by_type

    def _resources_by_type(self) -> dict[str, list[str]]:
        """Cached map of resource_name by resource type (config-derived)."""
        if self._resources_by_type_cache is not None:
            return self._resources_by_type_cache
        resources_by_type: dict[str, list[str]] = {}
        labs = getattr(self._configuration_manager, "labs", {})
        for _lab_name, lab_cfg in labs.items():
            for resource_name, resource_cfg in lab_cfg.resources.items():
                resources_by_type.setdefault(resource_cfg.type, []).append(resource_name)
        self._resources_by_type_cache = resources_by_type
        return resources_by_type

    def _resources_by_type_with_labs(self) -> dict[str, list[tuple[str, str]]]:
        """Build a map from resource type to list of (lab_name, resource_name) pairs.

        Useful for schedulers that need to filter by allowed labs or otherwise use lab context.
        """
        if self._resources_by_type_with_labs_cache is not None:
            return self._resources_by_type_with_labs_cache
        resources_by_type: dict[str, list[tuple[str, str]]] = {}
        labs = getattr(self._configuration_manager, "labs", {})
        for lab_name, lab_cfg in labs.items():
            for resource_name, resource_cfg in lab_cfg.resources.items():
                resources_by_type.setdefault(resource_cfg.type, []).append((lab_name, resource_name))
        self._resources_by_type_with_labs_cache = resources_by_type
        return resources_by_type

    async def _resolve_task(
        self,
        db: AsyncDbSession,
        experiment_name: str,
        experiment_graph: ExperimentGraph,
        task_name: str,
    ) -> TaskDef:
        """Get Task and resolve resource input references."""
        task = experiment_graph.get_task(task_name)
        return await self._task_input_resolver.resolve_input_resource_references(db, experiment_name, task)

    async def _release_completed_allocations(self, db: AsyncDbSession, completed_by_exp: dict[str, set[str]]) -> None:
        """Release allocations for tasks completed across experiments."""
        await asyncio.gather(
            *[
                self._release_task_allocations(db, exp_name, task_name)
                for exp_name, completed in completed_by_exp.items()
                for task_name in completed.intersection(set(self._allocated_resources.get(exp_name, {})))
            ]
        )

    async def _get_experiment_priorities(self, db: AsyncDbSession, experiment_names: list[str]) -> dict[str, int]:
        """Fetch priorities for a set of experiments."""
        if not experiment_names:
            return {}
        experiments = await asyncio.gather(
            *[self._experiment_manager.get_experiment(db, name) for name in experiment_names], return_exceptions=False
        )
        return {name: exp.priority for name, exp in zip(experiment_names, experiments, strict=True)}

    @staticmethod
    def _check_task_dependencies_met(
        task_name: str, completed_tasks: set[str], experiment_graph: ExperimentGraph
    ) -> bool:
        """
        Check whether all dependencies of a task have been completed.
        """
        dependencies = experiment_graph.get_task_dependencies(task_name)
        return all(dep in completed_tasks for dep in dependencies)

    async def _check_device_available(
        self, db: AsyncDbSession, task: TaskDef, experiment_name: str, task_device: DeviceAssignmentDef
    ) -> bool:
        """
        A device is available if it is active and either unallocated or allocated to this task.
        Also checks pending allocation requests to prevent multiple experiments from requesting the same device.
        """
        # Fast path: conflicting pending request owned by another task?
        owner = self._pending_device_index.get((task_device.lab_name, task_device.name))
        if owner and owner != (experiment_name, task.name):
            return False

        device = await self._device_manager.get_device(db, task_device.lab_name, task_device.name)
        if device.status == DeviceStatus.INACTIVE:
            log.warning(
                "Device %s in lab %s is inactive (requested by task %s).",
                task_device.name,
                task_device.lab_name,
                task.name,
            )
            return False

        # Check if device is already allocated
        allocation = await self._allocation_manager.get_device_allocation(db, task_device.lab_name, task_device.name)
        if allocation:
            return allocation.owner == task.name and allocation.experiment_name == experiment_name

        # Pending requests already indexed above; allocated requests are handled by DB check.
        return True

    async def _check_resource_available(
        self, db: AsyncDbSession, task: TaskDef, experiment_name: str, resource_name: str
    ) -> bool:
        """
        A resource is available if it is unallocated or allocated to the requesting task.
        Also checks pending allocation requests to prevent multiple experiments from requesting the same resource.
        """
        # Fast path: conflicting pending request owned by another task?
        owner = self._pending_resource_index.get(resource_name)
        if owner and owner != (experiment_name, task.name):
            return False

        # Check if resource is already allocated
        allocation = await self._allocation_manager.get_resource_allocation(db, resource_name)
        if allocation:
            return allocation.owner == task.name and allocation.experiment_name == experiment_name

        return True

    async def _check_resources_available(
        self,
        db: AsyncDbSession,
        experiment_name: str,
        task: TaskDef,
        assigned_devices: dict[str, DeviceAssignmentDef],
    ) -> bool:
        """
        Check that all assigned devices and required resources are available.
        """
        if assigned_devices:
            checks = [self._check_device_available(db, task, experiment_name, dev) for dev in assigned_devices.values()]
            if not all(await asyncio.gather(*checks)):
                return False

        if task.resources:
            resource_checks = [
                self._check_resource_available(db, task, experiment_name, resource_name)
                for resource_name in task.resources.values()
            ]
            if not all(await asyncio.gather(*resource_checks)):
                return False

        return True

    async def _finalize_scheduling(
        self,
        db: AsyncDbSession,
        experiment_name: str,
        task_name: str,
        task: TaskDef,
        assigned_devices: dict[str, DeviceAssignmentDef],
    ) -> ScheduledTask | None:
        """
        Given a task and its concrete device assignments, verify availability, allocate resources and
        build the ScheduledTask. Returns None if resources are unavailable or allocation not granted.
        """
        if not await self._check_resources_available(db, experiment_name, task, assigned_devices):
            return None

        success, allocated_request = await self._allocate_task_resources(
            db, experiment_name, task_name, task, assigned_devices
        )
        if not success:
            return None

        return ScheduledTask(
            name=task_name,
            experiment_name=experiment_name,
            devices=assigned_devices,
            resources=task.resources,
            allocations=allocated_request,
        )

    async def is_experiment_completed(self, db: AsyncDbSession, experiment_name: str) -> bool:
        """
        Check if every task in the experiment graph has been completed.
        """
        if experiment_name not in self._registered_experiments:
            raise Exception(f"Cannot check completion of unregistered experiment {experiment_name}.")
        _, experiment_graph = self._registered_experiments[experiment_name]
        all_tasks = set(experiment_graph.get_task_graph().nodes)
        completed_tasks = set(await self._experiment_manager.get_completed_tasks(db, experiment_name))
        return all_tasks.issubset(completed_tasks)

    async def _build_resolved_resources(
        self,
        db: AsyncDbSession,
        experiment_name: str,
        task: TaskDef,
    ) -> dict[str, str] | None:
        """
        Default resource resolution: accept only explicit (non-reference) strings.
        Subclasses override to handle dynamic resource selection.
        Return None to defer scheduling if resources cannot be resolved now.
        """
        resolved: dict[str, str] = {}
        for name, value in task.resources.items():
            if isinstance(value, str):
                resolved[name] = value
            else:
                # Base scheduler cannot resolve dynamic resource requests
                return None
        return resolved

    async def _build_assigned_devices(
        self,
        db: AsyncDbSession,
        experiment_name: str,
        task: TaskDef,
    ) -> dict[str, DeviceAssignmentDef] | None:
        """
        Default device resolution: use only explicitly-declared devices.
        Subclasses override to support dynamic devices and references.
        """
        return {
            device_name: DeviceAssignmentDef(lab_name=dev.lab_name, name=dev.name)
            for device_name, dev in task.devices.items()
            if isinstance(dev, DeviceAssignmentDef)
        }

    async def _check_and_allocate_resources(
        self,
        db: AsyncDbSession,
        experiment_name: str,
        task_name: str,
        completed_tasks: set[str],
        experiment_graph: ExperimentGraph,
    ) -> ScheduledTask | None:
        """
        Template method: verify readiness, resolve resources/devices, then finalize scheduling.
        Subclasses customize resolution via _build_resolved_resources/_build_assigned_devices or availability checks.
        """
        if not self._check_task_dependencies_met(task_name, completed_tasks, experiment_graph):
            return None

        task: TaskDef = await self._resolve_task(db, experiment_name, experiment_graph, task_name)

        resolved_resources = await self._build_resolved_resources(db, experiment_name, task)
        if resolved_resources is None:
            return None
        task.resources = resolved_resources

        assigned_devices = await self._build_assigned_devices(db, experiment_name, task)
        if assigned_devices is None:
            return None

        return await self._finalize_scheduling(db, experiment_name, task_name, task, assigned_devices)

    async def update_parameters(self, parameters: dict) -> None:
        """
        Base implementation: support cache tuning and invalidation.
        Subclasses can extend this, but should call super().
        """
        # TTL for active device pool cache
        ttl = parameters.get("device_pool_cache_ttl")
        if isinstance(ttl, int | float) and ttl >= 0:
            self._active_device_cache_ttl = float(ttl)
            self._invalidate_device_cache()
        # Explicit invalidation (e.g., labs reloaded)
        if parameters.get("invalidate_caches"):
            self._invalidate_all_caches()

    def _cleanup_completed_request(
        self, experiment_name: str, task_name: str, request: ActiveAllocationRequest
    ) -> None:
        """Remove tracking and indices for a completed/aborted allocation request."""
        self._unregister_allocation_from_indices(request)
        del self._allocated_resources[experiment_name][task_name]

    async def _handle_existing_allocation_request(
        self, db: AsyncDbSession, experiment_name: str, task_name: str, existing_request: ActiveAllocationRequest
    ) -> AllocationCheckResult:
        """
        Check and update an existing allocation request.

        Returns AllocationCheckResult with:
        - success: True if allocation is ready
        - request: The active allocation request if available
        - should_continue: False means we found a result and should return immediately
        """
        current_request = await self._allocation_manager.get_active_request(db, existing_request.id)
        if current_request:
            self._allocated_resources[experiment_name][task_name] = current_request
            if current_request.status == AllocationRequestStatus.ALLOCATED:
                return AllocationCheckResult(success=True, request=current_request, should_continue=False)
            # Request is still pending, don't create a duplicate
            return AllocationCheckResult(success=False, request=None, should_continue=False)
        # Request was completed/aborted, clean up and continue
        self._cleanup_completed_request(experiment_name, task_name, existing_request)
        return AllocationCheckResult(success=False, request=None, should_continue=True)

    def _register_allocation_in_indices(
        self, experiment_name: str, task_name: str, allocated_request: ActiveAllocationRequest
    ) -> None:
        """Register allocation in fast conflict indices."""
        for alloc in allocated_request.allocations:
            if alloc.allocation_type == AllocationType.DEVICE:
                self._pending_device_index[(alloc.lab_name, alloc.name)] = (experiment_name, task_name)
            elif alloc.allocation_type == AllocationType.RESOURCE:
                self._pending_resource_index[alloc.name] = (experiment_name, task_name)

    def _unregister_allocation_from_indices(self, allocated_request: ActiveAllocationRequest) -> None:
        """Remove allocation from fast conflict indices."""
        for alloc in allocated_request.allocations:
            if alloc.allocation_type == AllocationType.DEVICE:
                self._pending_device_index.pop((alloc.lab_name, alloc.name), None)
            elif alloc.allocation_type == AllocationType.RESOURCE:
                self._pending_resource_index.pop(alloc.name, None)

    def _update_allocation_indices(
        self, experiment_name: str, task_name: str, allocated_request: ActiveAllocationRequest
    ) -> None:
        """
        Register/update fast conflict indices for an allocation request.

        Deprecated: use _register_allocation_in_indices instead.
        """
        self._register_allocation_in_indices(experiment_name, task_name, allocated_request)

    async def _create_allocation_request(
        self,
        db: AsyncDbSession,
        experiment_name: str,
        task_name: str,
        task: TaskDef,
        assigned_devices: dict[str, DeviceAssignmentDef],
    ) -> AllocationRequest:
        """Build an allocation request for the given task configuration."""
        experiment = await self._experiment_manager.get_experiment(db, experiment_name)
        request = AllocationRequest(
            requester=task_name,
            experiment_name=experiment_name,
            priority=experiment.priority,
            reason=f"Allocations required for task '{task_name}'",
        )
        for dev in assigned_devices.values():
            request.add_allocation(dev.name, dev.lab_name, AllocationType.DEVICE)
        for resource_name in task.resources.values():
            request.add_allocation(resource_name, "", AllocationType.RESOURCE)
        return request

    async def _allocate_task_resources(
        self,
        db: AsyncDbSession,
        experiment_name: str,
        task_name: str,
        task: TaskDef,
        assigned_devices: dict[str, DeviceAssignmentDef],
    ) -> tuple[bool, ActiveAllocationRequest | None]:
        """
        Allocate devices and resources for a task using the provided concrete device assignments and resources.

        Returns: (success, allocated_request)
        """
        if not assigned_devices and not task.resources:
            return True, None

        # Check if there's already a pending or allocated request for this task
        existing_request = self._allocated_resources.get(experiment_name, {}).get(task_name)
        if existing_request:
            result = await self._handle_existing_allocation_request(db, experiment_name, task_name, existing_request)
            if not result.should_continue:
                return result.success, result.request

        # Build and submit the allocation request
        request = await self._create_allocation_request(db, experiment_name, task_name, task, assigned_devices)

        try:
            allocated_request = await self._allocation_manager.request_allocations(db, request, lambda _: None)
            self._allocated_resources.setdefault(experiment_name, {})[task_name] = allocated_request
            self._update_allocation_indices(experiment_name, task_name, allocated_request)

            if allocated_request.status == AllocationRequestStatus.ALLOCATED:
                return True, allocated_request
            return False, None
        except Exception as e:
            log.warning(f"Error requesting allocations for task '{task_name}' in experiment '{experiment_name}': {e}")
            return False, None
