from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime, UTC

import networkx as nx

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task_def import DeviceAssignmentDef, TaskDef
from eos.configuration.protocol_graph import ProtocolGraph
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.devices.device_manager import DeviceManager
from eos.devices.entities.device import DeviceStatus
from eos.logging.logger import log
from eos.allocation.allocation_manager import AllocationManager
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerRegistrationError
from eos.protocols.protocol_run_manager import ProtocolRunManager
from eos.tasks.entities.task import TaskSubmission
from eos.tasks.task_input_resolver import TaskInputResolver
from eos.tasks.task_manager import TaskManager
from eos.utils.async_rlock import AsyncRLock


@dataclass
class AllocationEntry:
    """A single device or resource allocation tracked by the scheduler."""

    owner: str
    protocol_run_name: str | None
    hold_on_complete: bool = False
    held: bool = False


@dataclass
class PendingOnDemandTask:
    """An on-demand task queued for scheduling."""

    submission: TaskSubmission
    submitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class BaseScheduler(AbstractScheduler, ABC):
    """Base scheduler with unified allocation index, first-class holds, and on-demand task support."""

    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        protocol_run_manager: ProtocolRunManager,
        task_manager: TaskManager,
        device_manager: DeviceManager,
        allocation_manager: AllocationManager,
    ):
        self._configuration_manager = configuration_manager
        self._protocol_run_manager = protocol_run_manager
        self._task_input_resolver = TaskInputResolver(task_manager, protocol_run_manager)
        self._device_manager = device_manager
        self._allocation_manager = allocation_manager

        self._registered_protocol_runs: dict[str, tuple[str, ProtocolGraph]] = {}

        # Allocation index — single source of truth for what's locked
        self._device_index: dict[tuple[str, str], AllocationEntry] = {}
        self._resource_index: dict[str, AllocationEntry] = {}

        self._on_demand_queue: list[PendingOnDemandTask] = []

        # Per-cycle caches (cleared each cycle)
        self._active_devices_cache: dict[str, list[tuple[str, str]]] | None = None
        self._active_device_set_cache: set[tuple[str, str]] | None = None
        self._completed_tasks_cache: dict[str, set[str]] = {}
        self._current_completed_tasks: set[str] | None = None

        # Permanent caches (cleared on unregister)
        self._topo_sorted_cache: dict[str, list[str]] = {}
        self._all_tasks_cache: dict[str, set[str]] = {}
        self._ancestors_cache: dict[str, dict[str, set[str]]] = {}

        # Lab-derived caches (invalidated when loaded labs change)
        self._resources_cache: dict[str, list[str]] | None = None
        self._resources_with_labs_cache: dict[str, list[tuple[str, str]]] | None = None
        self._cached_lab_names: frozenset[str] | None = None

        self._lock = AsyncRLock()

    async def register_protocol_run(self, protocol_run_name: str, protocol: str, protocol_graph: ProtocolGraph) -> None:
        async with self._lock:
            if protocol not in self._configuration_manager.protocols:
                raise EosSchedulerRegistrationError(f"Protocol type '{protocol}' does not exist.")
            self._registered_protocol_runs[protocol_run_name] = (protocol, protocol_graph)
            self._topo_sorted_cache[protocol_run_name] = protocol_graph.get_topologically_sorted_tasks()
            task_graph = protocol_graph.get_task_graph()
            self._all_tasks_cache[protocol_run_name] = set(task_graph.nodes)
            self._ancestors_cache[protocol_run_name] = {t: nx.ancestors(task_graph, t) for t in task_graph.nodes}

    async def unregister_protocol_run(self, db: AsyncDbSession, protocol_run_name: str) -> None:
        async with self._lock:
            if protocol_run_name not in self._registered_protocol_runs:
                raise EosSchedulerRegistrationError(f"ProtocolRun {protocol_run_name} is not registered.")
            del self._registered_protocol_runs[protocol_run_name]
            self._topo_sorted_cache.pop(protocol_run_name, None)
            self._all_tasks_cache.pop(protocol_run_name, None)
            self._ancestors_cache.pop(protocol_run_name, None)
            self._completed_tasks_cache.pop(protocol_run_name, None)
            await self._release_protocol_run_allocations(db, protocol_run_name)

    async def is_protocol_run_completed(self, db: AsyncDbSession, protocol_run_name: str) -> bool:
        if protocol_run_name not in self._registered_protocol_runs:
            raise Exception(f"Cannot check completion of unregistered protocol run {protocol_run_name}.")
        all_tasks = self._all_tasks_cache[protocol_run_name]
        completed_tasks = await self._protocol_run_manager.get_completed_tasks(db, protocol_run_name)
        self._completed_tasks_cache[protocol_run_name] = completed_tasks
        return all_tasks.issubset(completed_tasks)

    async def update_parameters(self, parameters: dict) -> None:
        pass

    async def release_task(self, db: AsyncDbSession, task_name: str, protocol_run_name: str | None = None) -> None:
        async with self._lock:
            if protocol_run_name is None:
                await self._release_on_demand_task(db, task_name)
            elif protocol_run_name not in self._registered_protocol_runs:
                self._remove_task_from_indices(task_name, protocol_run_name)
            else:
                await self._release_protocol_run_task(db, task_name, protocol_run_name)

    async def _release_protocol_run_task(self, db: AsyncDbSession, task_name: str, protocol_run_name: str) -> None:
        """Release allocations for a completed protocol run task, applying holds where configured."""
        _, protocol_graph = self._registered_protocol_runs[protocol_run_name]

        completed = self._current_completed_tasks
        if completed is None:
            completed = await self._protocol_run_manager.get_completed_tasks(db, protocol_run_name)

        graph = protocol_graph.get_graph()
        has_pending_successors = any(
            graph.nodes[s].get("node_type") == "task" and s not in completed for s in graph.successors(task_name)
        )

        devices_to_release = []
        devices_to_hold = []
        resources_to_release = []
        resources_to_hold = []

        self._partition_allocations(
            self._device_index,
            task_name,
            protocol_run_name,
            has_pending_successors,
            devices_to_hold,
            devices_to_release,
            "device",
        )
        self._partition_allocations(
            self._resource_index,
            task_name,
            protocol_run_name,
            has_pending_successors,
            resources_to_hold,
            resources_to_release,
            "resource",
        )

        if devices_to_hold:
            await self._allocation_manager.mark_devices_held(db, devices_to_hold)
        if resources_to_hold:
            await self._allocation_manager.mark_resources_held(db, resources_to_hold)
        if devices_to_release:
            await self._allocation_manager.deallocate_devices(db, devices_to_release)
        if resources_to_release:
            await self._allocation_manager.deallocate_resources(db, resources_to_release)

    def _partition_allocations(
        self,
        index: dict,
        task_name: str,
        protocol_run_name: str,
        has_pending_successors: bool,
        hold_list: list,
        release_list: list,
        kind: str,
    ) -> None:
        """Partition allocations for a task into hold vs release lists."""
        for key, entry in list(index.items()):
            if entry.owner != task_name or entry.protocol_run_name != protocol_run_name:
                continue
            if entry.hold_on_complete and has_pending_successors:
                entry.held = True
                hold_list.append(key)
                log.debug(
                    "Holding %s %s for completed task '%s' in protocol run '%s'.",
                    kind,
                    key,
                    task_name,
                    protocol_run_name,
                )
            else:
                del index[key]
                release_list.append(key)

    async def submit_on_demand_task(self, db: AsyncDbSession, task_submission: TaskSubmission) -> ScheduledTask | None:
        async with self._lock:
            scheduled = await self._try_schedule_on_demand(db, task_submission)
            if scheduled:
                return scheduled

            self._on_demand_queue.append(PendingOnDemandTask(submission=task_submission))
            log.debug("On-demand task '%s' queued (resources unavailable).", task_submission.name)
            return None

    async def process_pending_on_demand(self, db: AsyncDbSession) -> list[tuple[TaskSubmission, ScheduledTask]]:
        async with self._lock:
            if not self._on_demand_queue:
                return []

            scheduled: list[tuple[TaskSubmission, ScheduledTask]] = []
            remaining = []
            now = datetime.now(UTC)

            for pending in self._on_demand_queue:
                elapsed = (now - pending.submitted_at).total_seconds()
                if elapsed > pending.submission.allocation_timeout:
                    log.warning(
                        "On-demand task '%s' timed out after %.1fs.",
                        pending.submission.name,
                        elapsed,
                    )
                    continue

                result = await self._try_schedule_on_demand(db, pending.submission)
                if result:
                    scheduled.append((pending.submission, result))
                else:
                    remaining.append(pending)

            self._on_demand_queue = remaining
            return scheduled

    async def _try_schedule_on_demand(self, db: AsyncDbSession, submission: TaskSubmission) -> ScheduledTask | None:
        devices = submission.devices
        resources = submission.input_resources or {}

        for dev in devices.values():
            if not self._is_device_available(dev.lab_name, dev.name, submission.name, None):
                return None

        for resource in resources.values():
            if not self._is_resource_available(resource.name, submission.name, None):
                return None

        device_pairs = [(dev.lab_name, dev.name) for dev in devices.values()]
        resource_names = [r.name for r in resources.values()]

        if device_pairs:
            await self._allocation_manager.allocate_devices(db, device_pairs, submission.name)
            for dev in devices.values():
                self._device_index[(dev.lab_name, dev.name)] = AllocationEntry(
                    owner=submission.name, protocol_run_name=None
                )

        if resource_names:
            await self._allocation_manager.allocate_resources(db, resource_names, submission.name)
            for resource in resources.values():
                self._resource_index[resource.name] = AllocationEntry(owner=submission.name, protocol_run_name=None)

        return ScheduledTask(
            name=submission.name,
            protocol_run_name=None,
            devices=devices,
            resources={k: r.name for k, r in resources.items()},
        )

    def _is_device_available(
        self,
        lab_name: str,
        device_name: str,
        task_name: str,
        protocol_run_name: str | None,
        completed_tasks: set[str] | None = None,
    ) -> bool:
        """Check if a device is available for a task. Held devices are transparent to same-protocol-run successors."""
        entry = self._device_index.get((lab_name, device_name))
        if not entry:
            return True
        if entry.owner == task_name and entry.protocol_run_name == protocol_run_name:
            return True

        return self._is_hold_transparent(entry, task_name, protocol_run_name, completed_tasks)

    def _is_resource_available(
        self,
        resource_name: str,
        task_name: str,
        protocol_run_name: str | None,
        completed_tasks: set[str] | None = None,
    ) -> bool:
        """Check if a resource is available. Held resources are transparent to same-run successors."""
        entry = self._resource_index.get(resource_name)
        if not entry:
            return True
        if entry.owner == task_name and entry.protocol_run_name == protocol_run_name:
            return True

        return self._is_hold_transparent(entry, task_name, protocol_run_name, completed_tasks)

    def _is_hold_transparent(
        self,
        entry: AllocationEntry,
        task_name: str,
        protocol_run_name: str | None,
        completed_tasks: set[str] | None = None,
    ) -> bool:
        """Check if a held allocation is transparent (available) to a successor task."""
        effective_completed = completed_tasks if completed_tasks is not None else self._current_completed_tasks
        return bool(
            entry.held
            and effective_completed
            and entry.protocol_run_name == protocol_run_name
            and protocol_run_name is not None
            and entry.owner in effective_completed
            and entry.owner in self._ancestors_cache.get(protocol_run_name, {}).get(task_name, set())
        )

    async def _check_device_active(self, db: AsyncDbSession, lab_name: str, device_name: str, task_name: str) -> bool:
        """Check if device is active (not inactive)."""
        if self._active_device_set_cache is not None:
            if (lab_name, device_name) not in self._active_device_set_cache:
                log.warning("Device %s in lab %s is inactive (requested by task %s).", device_name, lab_name, task_name)
                return False
            return True

        device = await self._device_manager.get_device(db, lab_name, device_name)
        if device.status == DeviceStatus.INACTIVE:
            log.warning("Device %s in lab %s is inactive (requested by task %s).", device_name, lab_name, task_name)
            return False
        return True

    async def _resolve_task(
        self, db: AsyncDbSession, protocol_run_name: str, protocol_graph: ProtocolGraph, task_name: str
    ) -> TaskDef:
        task = protocol_graph.get_task(task_name)
        return await self._task_input_resolver.resolve_input_resource_references(db, protocol_run_name, task)

    async def _build_resolved_resources(
        self, db: AsyncDbSession, protocol_run_name: str, task: TaskDef
    ) -> dict[str, str] | None:
        """Default: accept only explicit string resources. Subclasses override for dynamic."""
        resolved: dict[str, str] = {}
        for name, value in task.resources.items():
            if isinstance(value, str):
                resolved[name] = value
            else:
                return None
        return resolved

    async def _build_assigned_devices(
        self, db: AsyncDbSession, protocol_run_name: str, task: TaskDef
    ) -> dict[str, DeviceAssignmentDef] | None:
        """Default: use only explicitly-declared devices. Subclasses override for dynamic/reference."""
        return {
            device_name: DeviceAssignmentDef(lab_name=dev.lab_name, name=dev.name)
            for device_name, dev in task.devices.items()
            if isinstance(dev, DeviceAssignmentDef)
        }

    @staticmethod
    def _check_task_dependencies_met(task_name: str, completed_tasks: set[str], protocol_graph: ProtocolGraph) -> bool:
        dependencies = protocol_graph.get_task_dependencies(task_name)
        return all(dep in completed_tasks for dep in dependencies)

    async def _check_and_allocate_resources(
        self,
        db: AsyncDbSession,
        protocol_run_name: str,
        task_name: str,
        completed_tasks: set[str],
        protocol_graph: ProtocolGraph,
    ) -> ScheduledTask | None:
        """Verify readiness, resolve resources/devices, allocate, and return ScheduledTask."""
        if not self._check_task_dependencies_met(task_name, completed_tasks, protocol_graph):
            return None

        task = await self._resolve_task(db, protocol_run_name, protocol_graph, task_name)

        resolved_resources = await self._build_resolved_resources(db, protocol_run_name, task)
        if resolved_resources is None:
            log.warning(
                "RUN '%s' - Cannot resolve resources for task '%s'. Check that required labs are loaded.",
                protocol_run_name,
                task_name,
            )
            return None
        task.resources = resolved_resources

        assigned_devices = await self._build_assigned_devices(db, protocol_run_name, task)
        if assigned_devices is None:
            log.warning(
                "RUN '%s' - Cannot resolve devices for task '%s'. Check that required labs are loaded.",
                protocol_run_name,
                task_name,
            )
            return None

        return await self._finalize_scheduling(
            db, protocol_run_name, task_name, task, assigned_devices, completed_tasks
        )

    async def _finalize_scheduling(
        self,
        db: AsyncDbSession,
        protocol_run_name: str,
        task_name: str,
        task: TaskDef,
        assigned_devices: dict[str, DeviceAssignmentDef],
        completed_tasks: set[str] | None = None,
    ) -> ScheduledTask | None:
        for dev in assigned_devices.values():
            if not self._is_device_available(dev.lab_name, dev.name, task_name, protocol_run_name, completed_tasks):
                return None
            if not await self._check_device_active(db, dev.lab_name, dev.name, task_name):
                return None

        for resource_name in task.resources.values():
            if not self._is_resource_available(resource_name, task_name, protocol_run_name, completed_tasks):
                return None

        device_pairs = [(dev.lab_name, dev.name) for dev in assigned_devices.values()]
        if device_pairs:
            await self._allocation_manager.allocate_devices(db, device_pairs, task_name, protocol_run_name)
            for slot, dev in assigned_devices.items():
                self._device_index[(dev.lab_name, dev.name)] = AllocationEntry(
                    owner=task_name,
                    protocol_run_name=protocol_run_name,
                    hold_on_complete=task.device_holds.get(slot, False),
                )

        resource_names = list(task.resources.values())
        if resource_names:
            await self._allocation_manager.allocate_resources(db, resource_names, task_name, protocol_run_name)
            for slot, res_name in task.resources.items():
                self._resource_index[res_name] = AllocationEntry(
                    owner=task_name,
                    protocol_run_name=protocol_run_name,
                    hold_on_complete=task.resource_holds.get(slot, False),
                )

        return ScheduledTask(
            name=task_name,
            protocol_run_name=protocol_run_name,
            devices=assigned_devices,
            resources=task.resources,
        )

    async def _release_on_demand_task(self, db: AsyncDbSession, task_name: str) -> None:
        """Release all allocations for an on-demand task (no holds)."""
        devices_to_release = [
            key
            for key, entry in self._device_index.items()
            if entry.owner == task_name and entry.protocol_run_name is None
        ]
        resources_to_release = [
            name
            for name, entry in self._resource_index.items()
            if entry.owner == task_name and entry.protocol_run_name is None
        ]

        for key in devices_to_release:
            del self._device_index[key]
        for name in resources_to_release:
            del self._resource_index[name]

        if devices_to_release:
            await self._allocation_manager.deallocate_devices(db, devices_to_release)
        if resources_to_release:
            await self._allocation_manager.deallocate_resources(db, resources_to_release)

    async def _release_protocol_run_allocations(self, db: AsyncDbSession, protocol_run_name: str) -> None:
        """Release all allocations (including holds) for a protocol run."""
        devices_to_release = [
            key for key, entry in self._device_index.items() if entry.protocol_run_name == protocol_run_name
        ]
        resources_to_release = [
            name for name, entry in self._resource_index.items() if entry.protocol_run_name == protocol_run_name
        ]

        for key in devices_to_release:
            del self._device_index[key]
        for name in resources_to_release:
            del self._resource_index[name]

        if devices_to_release:
            await self._allocation_manager.deallocate_devices(db, devices_to_release)
        if resources_to_release:
            await self._allocation_manager.deallocate_resources(db, resources_to_release)

    def _remove_task_from_indices(self, task_name: str, protocol_run_name: str | None) -> None:
        """Remove a task's entries from indices without DB cleanup."""
        self._device_index = {
            k: v
            for k, v in self._device_index.items()
            if not (v.owner == task_name and v.protocol_run_name == protocol_run_name)
        }
        self._resource_index = {
            k: v
            for k, v in self._resource_index.items()
            if not (v.owner == task_name and v.protocol_run_name == protocol_run_name)
        }

    async def _release_completed_allocations(self, db: AsyncDbSession, completed_by_exp: dict[str, set[str]]) -> None:
        tasks_to_release: set[tuple[str, str]] = set()
        for entry in self._device_index.values():
            if (
                not entry.held
                and entry.protocol_run_name in completed_by_exp
                and entry.owner in completed_by_exp[entry.protocol_run_name]
            ):
                tasks_to_release.add((entry.protocol_run_name, entry.owner))
        for entry in self._resource_index.values():
            if (
                not entry.held
                and entry.protocol_run_name in completed_by_exp
                and entry.owner in completed_by_exp[entry.protocol_run_name]
            ):
                tasks_to_release.add((entry.protocol_run_name, entry.owner))

        for run_name, task_name in tasks_to_release:
            await self.release_task(db, task_name, run_name)

    async def _active_devices_by_type(self, db: AsyncDbSession) -> dict[str, list[tuple[str, str]]]:
        if self._active_devices_cache is not None:
            return self._active_devices_cache

        all_devices = await self._device_manager.get_devices(db)
        inactive = {(d.lab_name, d.name) for d in all_devices if d.status == DeviceStatus.INACTIVE}

        devices_by_type: dict[str, list[tuple[str, str]]] = {}
        active_device_set: set[tuple[str, str]] = set()
        labs = getattr(self._configuration_manager, "labs", {})
        for lab_name, lab_cfg in labs.items():
            for device_name, dev_cfg in lab_cfg.devices.items():
                if (lab_name, device_name) in inactive:
                    continue
                devices_by_type.setdefault(dev_cfg.type, []).append((lab_name, device_name))
                active_device_set.add((lab_name, device_name))

        self._active_devices_cache = devices_by_type
        self._active_device_set_cache = active_device_set
        return devices_by_type

    def _check_lab_cache_validity(self) -> None:
        current_labs = frozenset(getattr(self._configuration_manager, "labs", {}).keys())
        if current_labs != self._cached_lab_names:
            self._resources_cache = None
            self._resources_with_labs_cache = None
            self._cached_lab_names = current_labs

    def _resources_by_type(self) -> dict[str, list[str]]:
        self._check_lab_cache_validity()
        if self._resources_cache is not None:
            return self._resources_cache

        resources_by_type: dict[str, list[str]] = {}
        labs = getattr(self._configuration_manager, "labs", {})
        for _lab_name, lab_cfg in labs.items():
            for resource_name, resource_cfg in lab_cfg.resources.items():
                resources_by_type.setdefault(resource_cfg.type, []).append(resource_name)
        self._resources_cache = resources_by_type
        return resources_by_type

    def _resources_by_type_with_labs(self) -> dict[str, list[tuple[str, str]]]:
        self._check_lab_cache_validity()
        if self._resources_with_labs_cache is not None:
            return self._resources_with_labs_cache

        resources_by_type: dict[str, list[tuple[str, str]]] = {}
        labs = getattr(self._configuration_manager, "labs", {})
        for lab_name, lab_cfg in labs.items():
            for resource_name, resource_cfg in lab_cfg.resources.items():
                resources_by_type.setdefault(resource_cfg.type, []).append((lab_name, resource_name))
        self._resources_with_labs_cache = resources_by_type
        return resources_by_type

    async def _get_protocol_run_priorities(self, db: AsyncDbSession, protocol_run_names: list[str]) -> dict[str, int]:
        return await self._protocol_run_manager.get_protocol_run_priorities(db, protocol_run_names)

    def _clear_per_cycle_caches(self) -> None:
        self._active_devices_cache = None
        self._active_device_set_cache = None
