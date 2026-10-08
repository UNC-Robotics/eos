from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, UTC

import networkx as nx

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.lab_def import LabDef
from eos.configuration.entities.task_def import DeviceAssignmentDef, TaskDef
from eos.configuration.protocol_graph import ProtocolGraph
from eos.configuration.utils import is_resource_reference
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.devices.device_manager import DeviceManager
from eos.devices.entities.device import DeviceStatus
from eos.logging.logger import log
from eos.allocation.allocation_manager import AllocationManager
from eos.scheduling.abstract_scheduler import AbstractScheduler, OnDemandProgress
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerRegistrationError
from eos.scheduling.simulation import LockManager, ProtocolRunInstance, RunningTask
from eos.scheduling.utils import compute_hold_needs, compute_hold_users
from eos.protocols.protocol_run_manager import ProtocolRunManager
from eos.tasks.entities.task import TaskStatus, TaskSubmission
from eos.tasks.task_input_resolver import TaskInputResolver
from eos.tasks.task_manager import TaskManager
from eos.utils.async_rlock import AsyncRLock


@dataclass
class AllocationEntry:
    """A single device or resource allocation tracked by the scheduler."""

    owner: str
    protocol_run_name: str | None
    hold_for: frozenset[str] = frozenset()
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
        self._task_manager = task_manager
        self._task_input_resolver = TaskInputResolver(task_manager, protocol_run_manager)
        self._device_manager = device_manager
        self._allocation_manager = allocation_manager

        self._registered_protocol_runs: dict[str, tuple[str, ProtocolGraph]] = {}

        # Allocation index — single source of truth for what's locked
        self._device_index: dict[tuple[str, str], AllocationEntry] = {}
        self._resource_index: dict[str, AllocationEntry] = {}

        self._on_demand_queue: list[PendingOnDemandTask] = []

        # Bumped on every allocation, release, registration and settled-task change
        self._state_version = 0
        self._settled_tasks: dict[str, set[str]] = {}

        # Protocol run tasks that were allocated and handed out, until released or settled
        self._dispatched_tasks: dict[str, set[str]] = {}
        self._restored_runs: set[str] = set()

        # Devices and resources each dispatched (or restored) task actually got, for resolving references
        self._assigned_devices: dict[str, dict[str, dict[str, DeviceAssignmentDef]]] = {}
        self._assigned_resources: dict[str, dict[str, dict[str, str]]] = {}

        # Runs that got nothing at the current state version, for deadlock detection
        self._idle_runs: set[str] = set()
        self._idle_version = -1
        self._deadlock_reported_version = -1

        # Per-cycle caches (cleared each cycle)
        self._active_devices_cache: dict[str, list[tuple[str, str]]] | None = None
        self._active_device_set_cache: set[tuple[str, str]] | None = None
        self._completed_tasks_cache: dict[str, set[str]] = {}

        # Permanent caches (cleared on unregister)
        self._topo_sorted_cache: dict[str, list[str]] = {}
        self._all_tasks_cache: dict[str, set[str]] = {}
        self._ancestors_cache: dict[str, dict[str, set[str]]] = {}
        self._task_defs: dict[str, dict[str, TaskDef]] = {}
        self._device_hold_users: dict[str, dict[tuple[str, str], frozenset[str]]] = {}
        self._resource_hold_users: dict[str, dict[tuple[str, str], frozenset[str]]] = {}
        self._device_hold_needs: dict[str, dict[tuple[str, str], frozenset]] = {}
        self._resource_hold_needs: dict[str, dict[tuple[str, str], frozenset]] = {}

        # Lab-derived caches (invalidated when loaded labs change)
        self._resources_cache: dict[str, list[str]] | None = None
        self._resources_with_labs_cache: dict[str, list[tuple[str, str]]] | None = None
        self._cached_lab_names: frozenset[tuple[str, int]] | None = None

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
            self._task_defs[protocol_run_name] = {t: protocol_graph.get_task(t) for t in task_graph.nodes}
            device_users, resource_users = compute_hold_users(protocol_graph)
            self._device_hold_users[protocol_run_name] = device_users
            self._resource_hold_users[protocol_run_name] = resource_users
            device_needs, resource_needs = compute_hold_needs(protocol_graph, device_users, resource_users)
            self._device_hold_needs[protocol_run_name] = device_needs
            self._resource_hold_needs[protocol_run_name] = resource_needs
            self._state_version += 1

    async def unregister_protocol_run(self, db: AsyncDbSession, protocol_run_name: str) -> None:
        async with self._lock:
            if protocol_run_name not in self._registered_protocol_runs:
                raise EosSchedulerRegistrationError(f"ProtocolRun {protocol_run_name} is not registered.")
            del self._registered_protocol_runs[protocol_run_name]
            self._topo_sorted_cache.pop(protocol_run_name, None)
            self._all_tasks_cache.pop(protocol_run_name, None)
            self._ancestors_cache.pop(protocol_run_name, None)
            self._task_defs.pop(protocol_run_name, None)
            self._device_hold_users.pop(protocol_run_name, None)
            self._resource_hold_users.pop(protocol_run_name, None)
            self._device_hold_needs.pop(protocol_run_name, None)
            self._resource_hold_needs.pop(protocol_run_name, None)
            self._completed_tasks_cache.pop(protocol_run_name, None)
            self._settled_tasks.pop(protocol_run_name, None)
            self._dispatched_tasks.pop(protocol_run_name, None)
            self._assigned_devices.pop(protocol_run_name, None)
            self._assigned_resources.pop(protocol_run_name, None)
            self._restored_runs.discard(protocol_run_name)
            self._state_version += 1
            await self._release_allocations(db, lambda entry: entry.protocol_run_name == protocol_run_name)

    async def is_protocol_run_completed(self, db: AsyncDbSession, protocol_run_name: str) -> bool:
        if protocol_run_name not in self._registered_protocol_runs:
            raise Exception(f"Cannot check completion of unregistered protocol run {protocol_run_name}.")
        all_tasks = self._all_tasks_cache[protocol_run_name]
        completed_tasks = await self._protocol_run_manager.get_completed_and_skipped_tasks(db, protocol_run_name)
        self._completed_tasks_cache[protocol_run_name] = completed_tasks
        if self._settled_tasks.get(protocol_run_name) != completed_tasks:
            self._settled_tasks[protocol_run_name] = completed_tasks
            self._state_version += 1
        return all_tasks.issubset(completed_tasks)

    @property
    def state_version(self) -> int:
        return self._state_version

    async def update_parameters(self, parameters: dict) -> None:
        self._state_version += 1

    async def release_task(self, db: AsyncDbSession, task_name: str, protocol_run_name: str | None = None) -> None:
        async with self._lock:
            self._state_version += 1
            self._dispatched_tasks.get(protocol_run_name, set()).discard(task_name)
            if protocol_run_name in self._registered_protocol_runs:
                await self._release_protocol_run_task(db, task_name, protocol_run_name)
            else:
                # On-demand tasks and tasks of unregistered runs have no holds
                await self._release_task_allocations(db, task_name, protocol_run_name)

    async def _release_protocol_run_task(
        self, db: AsyncDbSession, task_name: str, protocol_run_name: str, completed: set[str] | None = None
    ) -> None:
        """Release allocations for a completed protocol run task, holding those a pending task still needs."""
        if completed is None:
            completed = await self._protocol_run_manager.get_completed_and_skipped_tasks(db, protocol_run_name)

        devices_to_release = []
        devices_to_hold = []
        resources_to_release = []
        resources_to_hold = []

        self._partition_allocations(
            self._device_index,
            task_name,
            protocol_run_name,
            completed,
            devices_to_hold,
            devices_to_release,
            "device",
        )
        self._partition_allocations(
            self._resource_index,
            task_name,
            protocol_run_name,
            completed,
            resources_to_hold,
            resources_to_release,
            "resource",
        )

        if devices_to_hold or devices_to_release or resources_to_hold or resources_to_release:
            self._state_version += 1
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
        completed: set[str],
        hold_list: list,
        release_list: list,
        kind: str,
    ) -> None:
        """Partition allocations for a task into hold vs release lists."""
        for key, entry in list(index.items()):
            if entry.owner != task_name or entry.protocol_run_name != protocol_run_name:
                continue
            if not entry.hold_for <= completed:
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

    async def process_pending_on_demand(self, db: AsyncDbSession) -> OnDemandProgress:
        async with self._lock:
            progress = OnDemandProgress(scheduled=[], timed_out=[])
            if not self._on_demand_queue:
                return progress

            remaining = []
            now = datetime.now(UTC)
            # Devices and resources wanted by a waiting task, so later tasks cannot keep taking them first
            blocked_devices: set[tuple[str, str]] = set()
            blocked_resources: set[str] = set()

            queue = sorted(self._on_demand_queue, key=lambda p: (-p.submission.priority, p.submitted_at))
            for pending in queue:
                submission = pending.submission
                elapsed = (now - pending.submitted_at).total_seconds()
                if elapsed > submission.allocation_timeout:
                    log.warning("On-demand task '%s' timed out after %.1fs.", submission.name, elapsed)
                    progress.timed_out.append(submission)
                    continue

                devices = {(dev.lab_name, dev.name) for dev in submission.devices.values()}
                resources = {resource.name for resource in (submission.input_resources or {}).values()}
                if devices & blocked_devices or resources & blocked_resources:
                    remaining.append(pending)
                    continue

                result = await self._try_schedule_on_demand(db, submission)
                if result:
                    progress.scheduled.append((submission, result))
                else:
                    remaining.append(pending)
                    blocked_devices |= devices
                    blocked_resources |= resources

            self._on_demand_queue = remaining
            return progress

    async def cancel_on_demand_task(self, task_name: str) -> bool:
        async with self._lock:
            queue = self._on_demand_queue
            self._on_demand_queue = [pending for pending in queue if pending.submission.name != task_name]
            return len(self._on_demand_queue) != len(queue)

    async def _try_schedule_on_demand(self, db: AsyncDbSession, submission: TaskSubmission) -> ScheduledTask | None:
        devices = submission.devices
        resources = submission.input_resources or {}

        for dev in devices.values():
            if not self._is_device_available(dev.lab_name, dev.name, submission.name, None):
                return None
            if not await self._check_device_active(db, dev.lab_name, dev.name, submission.name):
                return None

        for resource in resources.values():
            if not self._is_resource_available(resource.name, submission.name, None):
                return None

        device_pairs = [(dev.lab_name, dev.name) for dev in devices.values()]
        resource_names = [r.name for r in resources.values()]
        self._state_version += 1

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
        self, lab_name: str, device_name: str, task_name: str, protocol_run_name: str | None, named: bool = False
    ) -> bool:
        """Check if a device is available for a task. Pass named when the task asks for this specific device."""
        entry = self._device_index.get((lab_name, device_name))
        if not entry:
            # Allocated outside the scheduler, e.g. by a manual reservation
            return not self._allocation_manager.is_device_allocated(lab_name, device_name)
        if entry.owner == task_name and entry.protocol_run_name == protocol_run_name:
            return True

        return self._is_hold_transparent(entry, task_name, protocol_run_name, named)

    def _is_resource_available(
        self, resource_name: str, task_name: str, protocol_run_name: str | None, named: bool = False
    ) -> bool:
        """Check if a resource is available. Pass named when the task asks for this specific resource."""
        entry = self._resource_index.get(resource_name)
        if not entry:
            return not self._allocation_manager.is_resource_allocated(resource_name)
        if entry.owner == task_name and entry.protocol_run_name == protocol_run_name:
            return True

        return self._is_hold_transparent(entry, task_name, protocol_run_name, named)

    def _is_hold_transparent(
        self, entry: AllocationEntry, task_name: str, protocol_run_name: str | None, named: bool = False
    ) -> bool:
        """
        Whether a held allocation is available to a task of the same protocol run.

        Its hold users may take it. So may a task that asks for this specific item and must run before a hold user,
        since the hold user would otherwise wait for it forever. Any other task must not, e.g. one that wants any
        vial must not take a vial holding another sample.
        """
        if not entry.held or protocol_run_name is None or entry.protocol_run_name != protocol_run_name:
            return False
        if task_name in entry.hold_for:
            return True
        ancestors = self._ancestors_cache.get(protocol_run_name, {})
        return named and any(task_name in ancestors.get(user, ()) for user in entry.hold_for)

    def _named_slots(self, protocol_run_name: str, task_name: str) -> tuple[set[str], set[str]]:
        """The device and resource slots in which a task asks for a specific device or resource by name."""
        task = self._task_defs.get(protocol_run_name, {}).get(task_name)
        if task is None:
            return set(), set()
        devices = {slot for slot, value in task.devices.items() if isinstance(value, DeviceAssignmentDef)}
        resources = {
            slot
            for slot, value in task.resources.items()
            if isinstance(value, str) and not is_resource_reference(value)
        }
        return devices, resources

    def _crosses_other_holds(
        self, protocol_run_name: str, task_name: str, devices: dict[str, DeviceAssignmentDef], resources: dict[str, str]
    ) -> bool:
        """
        Whether a task would start a hold while another run holds something the hold users also need.

        Each run could then wait for the other's held item forever, so the new hold waits instead.
        """
        for slots, index, needs in (
            ({slot: (d.lab_name, d.name) for slot, d in devices.items()}, self._device_index, self._device_hold_needs),
            (resources, self._resource_index, self._resource_hold_needs),
        ):
            for slot, item in slots.items():
                current = index.get(item)
                if current is not None and current.held and current.protocol_run_name == protocol_run_name:
                    continue  # Continues a hold of its own run rather than starting one
                for needed in needs.get(protocol_run_name, {}).get((task_name, slot), ()):
                    other = index.get(needed)
                    if (
                        other is not None
                        and other.hold_for
                        and other.protocol_run_name not in (None, protocol_run_name)
                    ):
                        return True
        return False

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

    async def _resolve_task(self, db: AsyncDbSession, protocol_run_name: str, task_name: str) -> TaskDef:
        """A copy of the task with its resource references resolved."""
        task = self._task_defs[protocol_run_name][task_name]
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
        # Cheap check before resolving references, which reads the database
        named_devices = self._task_defs[protocol_run_name][task_name].devices
        if any(
            isinstance(dev, DeviceAssignmentDef)
            and not self._is_device_available(dev.lab_name, dev.name, task_name, protocol_run_name, named=True)
            for dev in named_devices.values()
        ):
            return None

        task = await self._resolve_task(db, protocol_run_name, task_name)

        resolved_resources = await self._build_resolved_resources(db, protocol_run_name, task)
        if resolved_resources is None:
            return None
        task.resources = resolved_resources

        assigned_devices = await self._build_assigned_devices(db, protocol_run_name, task)
        if assigned_devices is None:
            return None

        return await self._finalize_scheduling(db, protocol_run_name, task_name, task, assigned_devices)

    async def _finalize_scheduling(
        self,
        db: AsyncDbSession,
        protocol_run_name: str,
        task_name: str,
        task: TaskDef,
        assigned_devices: dict[str, DeviceAssignmentDef],
    ) -> ScheduledTask | None:
        named_devices, named_resources = self._named_slots(protocol_run_name, task_name)
        for slot, dev in assigned_devices.items():
            named = slot in named_devices
            if not self._is_device_available(dev.lab_name, dev.name, task_name, protocol_run_name, named):
                return None
            if not await self._check_device_active(db, dev.lab_name, dev.name, task_name):
                return None

        for slot, resource_name in task.resources.items():
            if not self._is_resource_available(resource_name, task_name, protocol_run_name, slot in named_resources):
                return None

        if self._crosses_other_holds(protocol_run_name, task_name, assigned_devices, task.resources):
            return None

        device_hold_users = self._device_hold_users.get(protocol_run_name, {})
        resource_hold_users = self._resource_hold_users.get(protocol_run_name, {})
        self._state_version += 1

        device_pairs = [(dev.lab_name, dev.name) for dev in assigned_devices.values()]
        if device_pairs:
            await self._allocation_manager.allocate_devices(db, device_pairs, task_name, protocol_run_name)
            for slot, dev in assigned_devices.items():
                key = (dev.lab_name, dev.name)
                self._device_index[key] = AllocationEntry(
                    owner=task_name,
                    protocol_run_name=protocol_run_name,
                    hold_for=device_hold_users.get((task_name, slot), frozenset())
                    | self._inherited_hold(self._device_index.get(key), task_name, protocol_run_name),
                )

        resource_names = list(task.resources.values())
        if resource_names:
            await self._allocation_manager.allocate_resources(db, resource_names, task_name, protocol_run_name)
            for slot, res_name in task.resources.items():
                self._resource_index[res_name] = AllocationEntry(
                    owner=task_name,
                    protocol_run_name=protocol_run_name,
                    hold_for=resource_hold_users.get((task_name, slot), frozenset())
                    | self._inherited_hold(self._resource_index.get(res_name), task_name, protocol_run_name),
                )

        self._dispatched_tasks.setdefault(protocol_run_name, set()).add(task_name)
        self._assigned_devices.setdefault(protocol_run_name, {})[task_name] = dict(assigned_devices)
        self._assigned_resources.setdefault(protocol_run_name, {})[task_name] = dict(task.resources)
        return ScheduledTask(
            name=task_name,
            protocol_run_name=protocol_run_name,
            devices=assigned_devices,
            resources=task.resources,
        )

    @staticmethod
    def _inherited_hold(entry: AllocationEntry | None, task_name: str, protocol_run_name: str) -> frozenset[str]:
        """Hold users a task inherits when it takes over a held allocation of its own protocol run."""
        if entry is None or not entry.held or entry.protocol_run_name != protocol_run_name:
            return frozenset()
        return entry.hold_for - {task_name}

    async def _release_task_allocations(
        self, db: AsyncDbSession, task_name: str, protocol_run_name: str | None
    ) -> None:
        """Release every allocation of a task, ignoring holds."""
        await self._release_allocations(
            db, lambda entry: entry.owner == task_name and entry.protocol_run_name == protocol_run_name
        )

    async def _release_allocations(self, db: AsyncDbSession, matches: Callable[[AllocationEntry], bool]) -> None:
        """Release every allocation whose entry matches, including holds."""
        devices_to_release = [key for key, entry in self._device_index.items() if matches(entry)]
        resources_to_release = [name for name, entry in self._resource_index.items() if matches(entry)]
        if not devices_to_release and not resources_to_release:
            return

        self._state_version += 1
        for key in devices_to_release:
            del self._device_index[key]
        for name in resources_to_release:
            del self._resource_index[name]

        if devices_to_release:
            await self._allocation_manager.deallocate_devices(db, devices_to_release)
        if resources_to_release:
            await self._allocation_manager.deallocate_resources(db, resources_to_release)

    async def _release_completed_allocations(self, db: AsyncDbSession, completed_by_exp: dict[str, set[str]]) -> None:
        """Release allocations of completed tasks, including holds no pending task needs anymore."""
        tasks_to_release = {
            (entry.protocol_run_name, entry.owner)
            for entry in [*self._device_index.values(), *self._resource_index.values()]
            if entry.protocol_run_name in completed_by_exp
            and entry.owner in completed_by_exp[entry.protocol_run_name]
            and (not entry.held or entry.hold_for <= completed_by_exp[entry.protocol_run_name])
        }

        for run_name, task_name in tasks_to_release:
            if run_name in self._registered_protocol_runs:
                await self._release_protocol_run_task(db, task_name, run_name, completed_by_exp[run_name])
            else:
                await self._release_task_allocations(db, task_name, run_name)

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
        # Keyed on the lab objects too, so a reloaded lab with changed resources invalidates the caches
        current_labs = frozenset(
            (name, id(lab)) for name, lab in getattr(self._configuration_manager, "labs", {}).items()
        )
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

    async def _restore_assignments(self, db: AsyncDbSession, protocol_run_names: list[str]) -> None:
        """Load the devices and resources of completed tasks of newly seen runs, e.g. after a resume."""
        for run_name in protocol_run_names:
            if run_name in self._restored_runs:
                continue
            self._restored_runs.add(run_name)
            tasks = await self._task_manager.get_tasks(
                db, protocol_run_name=run_name, status=TaskStatus.COMPLETED.value
            )
            settled = await self._protocol_run_manager.get_completed_and_skipped_tasks(db, run_name)
            for task in tasks:
                resources = {name: resource.name for name, resource in (task.input_resources or {}).items()}
                self._restore_task_assignments(run_name, task.name, dict(task.devices), resources)
                await self._restore_holds(db, run_name, task.name, dict(task.devices), resources, settled)

    async def _restore_holds(
        self,
        db: AsyncDbSession,
        protocol_run_name: str,
        task_name: str,
        devices: dict[str, DeviceAssignmentDef],
        resources: dict[str, str],
        settled: set[str],
    ) -> None:
        """Hold a completed task's items again for its pending hold users, since allocations do not survive restarts."""
        for slot, device in devices.items():
            users = self._device_hold_users[protocol_run_name].get((task_name, slot), frozenset())
            key = (device.lab_name, device.name)
            if (
                users - settled
                and key not in self._device_index
                and not self._allocation_manager.is_device_allocated(*key)
            ):
                await self._allocation_manager.allocate_devices(db, [key], task_name, protocol_run_name)
                await self._allocation_manager.mark_devices_held(db, [key])
                self._device_index[key] = AllocationEntry(task_name, protocol_run_name, users, held=True)
        for slot, name in resources.items():
            users = self._resource_hold_users[protocol_run_name].get((task_name, slot), frozenset())
            if (
                users - settled
                and name not in self._resource_index
                and not self._allocation_manager.is_resource_allocated(name)
            ):
                await self._allocation_manager.allocate_resources(db, [name], task_name, protocol_run_name)
                await self._allocation_manager.mark_resources_held(db, [name])
                self._resource_index[name] = AllocationEntry(task_name, protocol_run_name, users, held=True)

    def _restore_task_assignments(
        self, protocol_run_name: str, task_name: str, devices: dict[str, DeviceAssignmentDef], resources: dict[str, str]
    ) -> None:
        """Record the assignments of a task completed before the run was registered."""
        self._assigned_devices.setdefault(protocol_run_name, {}).setdefault(task_name, devices)
        self._assigned_resources.setdefault(protocol_run_name, {}).setdefault(task_name, resources)

    def _referenced_device(self, protocol_run_name: str, reference: str) -> DeviceAssignmentDef | None:
        """The device a dispatched task actually used, for a 'task.slot' reference."""
        ref_task_name, ref_slot = reference.split(".")
        return self._assigned_devices.get(protocol_run_name, {}).get(ref_task_name, {}).get(ref_slot)

    def _check_deadlock(self, protocol_run_name: str, scheduled_any: bool) -> None:
        """Report when every run is stuck while nothing runs and holds of other runs block them."""
        allocations = [*self._device_index.items(), *self._resource_index.items()]
        running = any(self._dispatched_tasks.values()) or any(
            entry.protocol_run_name is None for _, entry in allocations
        )
        if scheduled_any or running:
            self._idle_runs.clear()
            return

        if self._idle_version != self._state_version:
            self._idle_runs, self._idle_version = set(), self._state_version
        self._idle_runs.add(protocol_run_name)
        if (
            self._idle_runs < set(self._registered_protocol_runs)
            or self._deadlock_reported_version == self._state_version
        ):
            return

        holds = [f"{key} held by {entry.protocol_run_name}.{entry.owner}" for key, entry in allocations if entry.held]
        if holds:
            self._deadlock_reported_version = self._state_version
            log.error(f"Scheduling deadlock: no protocol run can progress. Holds: {'; '.join(holds)}")

    def _running_tasks(self, protocol_run_name: str, completed_tasks: set[str]) -> set[str]:
        """Dispatched tasks of a run that have not settled yet."""
        return self._dispatched_tasks.get(protocol_run_name, set()) - completed_tasks

    def _schedulable_tasks(self, protocol_run_name: str, completed_tasks: set[str]) -> list[str]:
        """Tasks of a run in topological order that are neither settled nor already dispatched."""
        dispatched = self._dispatched_tasks.setdefault(protocol_run_name, set())
        dispatched -= completed_tasks  # Settled tasks no longer count as dispatched
        return [
            task_name
            for task_name in self._topo_sorted_cache[protocol_run_name]
            if task_name not in completed_tasks and task_name not in dispatched
        ]

    def _planning_snapshot(
        self,
        completed_by_run: dict[str, set[str]],
        run_priorities: dict[str, int],
        remaining_time: Callable[[str, str, int], int],
    ) -> tuple[dict[str, LabDef], list[ProtocolRunInstance], list[RunningTask], LockManager]:
        """Copy the scheduling state into simulator inputs, so a plan can be computed in a worker thread."""
        instances = [
            self._build_instance(run_name, completed_by_run.get(run_name, set()), run_priorities.get(run_name, 0))
            for run_name in self._registered_protocol_runs
        ]
        running = [
            RunningTask(
                protocol_run_name=exp.name,
                task_name=task_name,
                start_time=0,
                end_time=max(1, remaining_time(exp.name, task_name, exp.tasks[task_name].duration)),
                devices=exp.task_device_assignments.get(task_name, {}),
                resources=exp.task_resource_assignments.get(task_name, {}),
            )
            for exp in instances
            for task_name in self._running_tasks(exp.name, exp.completed_tasks)
        ]
        # Planning ignores device status. Inactive devices are still rejected at dispatch.
        labs = dict(getattr(self._configuration_manager, "labs", {}))
        return labs, instances, running, self._lock_snapshot()

    def _build_instance(self, run_name: str, completed: set[str], priority: int) -> ProtocolRunInstance:
        protocol, protocol_graph = self._registered_protocol_runs[run_name]
        all_tasks = self._all_tasks_cache[run_name]
        return ProtocolRunInstance(
            name=run_name,
            protocol_type=protocol,
            protocol_graph=protocol_graph,
            tasks=self._task_defs[run_name],
            ancestors=self._ancestors_cache[run_name],
            priority=priority,
            all_tasks=set(all_tasks),
            completed_tasks=set(completed),
            task_device_assignments=dict(self._assigned_devices.get(run_name, {})),
            task_resource_assignments=dict(self._assigned_resources.get(run_name, {})),
            device_hold_users=self._device_hold_users[run_name],
            resource_hold_users=self._resource_hold_users[run_name],
            device_hold_needs=self._device_hold_needs[run_name],
            resource_hold_needs=self._resource_hold_needs[run_name],
        )

    def _lock_snapshot(self) -> LockManager:
        """Copy protocol run allocations into a simulation lock manager. On-demand allocations are not planned."""
        locks = LockManager()
        for (lab_name, device_name), entry in self._device_index.items():
            if entry.protocol_run_name is not None:
                locks.lock_device(
                    lab_name, device_name, entry.protocol_run_name, entry.owner, entry.held, entry.hold_for
                )
        for resource_name, entry in self._resource_index.items():
            if entry.protocol_run_name is not None:
                locks.lock_resource(resource_name, entry.protocol_run_name, entry.owner, entry.held, entry.hold_for)
        return locks

    def _clear_per_cycle_caches(self) -> None:
        self._active_devices_cache = None
        self._active_device_set_cache = None
