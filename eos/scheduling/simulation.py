"""
Discrete-event simulation of the EOS scheduler.

Reads actual EOS lab/protocol definitions via PackageManager and simulates
scheduling algorithms (greedy or CP-SAT) with exclusive device/resource locking.
Produces a timeline and summary statistics showing task ordering, parallelism,
and device utilization.
"""

import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import yaml

from eos.configuration.entities.protocol_def import ProtocolDef
from eos.configuration.entities.lab_def import LabDef
from eos.configuration.entities.task_def import (
    DeviceAssignmentDef,
    DynamicDeviceAssignmentDef,
    DynamicResourceAssignmentDef,
    TaskDef,
)
from eos.configuration.protocol_graph import ProtocolGraph
from eos.configuration.packages import PackageManager
from eos.configuration.registries import TaskSpecRegistry
from eos.configuration.utils import is_device_reference, is_resource_reference
from eos.scheduling.utils import filter_device_pool, sort_resource_pool
from eos.utils.timer import Timer


@dataclass
class ProtocolRunConfig:
    """Per-protocol-type simulation parameters."""

    type: str
    iterations: int
    max_concurrent: int = 0


@dataclass
class SimConfig:
    """Top-level simulation configuration parsed from YAML."""

    packages: list[str]
    protocol_runs: list[ProtocolRunConfig]


@dataclass
class ProtocolRunInstance:
    """Runtime state for a single protocol run instance during simulation."""

    name: str
    protocol_type: str
    protocol_graph: ProtocolGraph
    tasks: dict[str, TaskDef]
    ancestors: dict[str, set[str]]
    all_tasks: set[str] = field(default_factory=set)
    completed_tasks: set[str] = field(default_factory=set)
    task_device_assignments: dict[str, dict[str, DeviceAssignmentDef]] = field(default_factory=dict)
    task_resource_assignments: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass
class RunningTask:
    """A task currently executing in the simulation."""

    protocol_run_name: str
    task_name: str
    start_time: int
    end_time: int
    devices: dict[str, DeviceAssignmentDef]
    resources: dict[str, str]


@dataclass
class TimelineEvent:
    """A START or DONE event in the simulation timeline."""

    time: int
    event_type: str
    protocol_run_name: str
    task_name: str
    devices: dict[str, DeviceAssignmentDef]
    resources: dict[str, str]
    duration: int = 0


@dataclass
class ScheduledSimTask:
    """A task selected for execution by the simulation scheduler."""

    protocol_run_name: str
    task_name: str
    duration: int
    devices: dict[str, DeviceAssignmentDef]
    resources: dict[str, str]


def load_sim_config(path: str) -> SimConfig:
    """Parse a simulation config YAML file."""
    with Path(path).open() as f:
        raw = yaml.safe_load(f)
    protocol_runs = [
        ProtocolRunConfig(
            type=e["type"],
            iterations=e["iterations"],
            max_concurrent=e.get("max_concurrent", 0),
        )
        for e in raw.get("protocols", [])
    ]
    return SimConfig(packages=raw.get("packages", []), protocol_runs=protocol_runs)


def load_simulation_data(
    sim_config: SimConfig,
    user_dir: Path,
) -> tuple[dict[str, LabDef], dict[str, ProtocolDef]]:
    """Load labs and protocols using EOS PackageManager."""
    TaskSpecRegistry({}, {})

    package_names = set(sim_config.packages)
    pkg_manager = PackageManager(str(user_dir), package_names)

    protocol_types = {e.type for e in sim_config.protocol_runs}
    protocols: dict[str, ProtocolDef] = {}
    required_labs: set[str] = set()

    for protocol_type in protocol_types:
        protocol_def = pkg_manager.read_protocol(protocol_type)
        protocols[protocol_type] = protocol_def
        required_labs.update(protocol_def.labs)

    labs: dict[str, LabDef] = {}
    for lab_name in required_labs:
        labs[lab_name] = pkg_manager.read_lab(lab_name)

    return labs, protocols


def build_type_indices(
    labs: dict[str, LabDef],
) -> tuple[dict[str, list[tuple[str, str]]], dict[str, list[str]]]:
    """Build device-by-type and resource-by-type indices from lab definitions."""
    devices_by_type: dict[str, list[tuple[str, str]]] = {}
    resources_by_type: dict[str, list[str]] = {}

    for lab_name, lab in labs.items():
        for dev_name, dev_def in lab.devices.items():
            devices_by_type.setdefault(dev_def.type, []).append((lab_name, dev_name))
        for res_name, res_def in lab.resources.items():
            resources_by_type.setdefault(res_def.type, []).append(res_name)

    for lst in devices_by_type.values():
        lst.sort()
    for lst in resources_by_type.values():
        lst.sort()

    return devices_by_type, resources_by_type


def _build_resources_with_labs(labs: dict[str, LabDef]) -> dict[str, list[tuple[str, str]]]:
    """Build resource-by-type index with (lab_name, resource_name) tuples for CP-SAT solver."""
    resources_by_type: dict[str, list[tuple[str, str]]] = {}
    for lab_name, lab in labs.items():
        for res_name, res_def in lab.resources.items():
            resources_by_type.setdefault(res_def.type, []).append((lab_name, res_name))
    for lst in resources_by_type.values():
        lst.sort()
    return resources_by_type


def create_protocol_run_instances(
    protocol_type: str,
    protocol_def: ProtocolDef,
    iterations: int,
) -> list[ProtocolRunInstance]:
    """Create N protocol run instances with independent graphs."""
    instances = []
    for i in range(1, iterations + 1):
        name = f"{protocol_type}_{i:03d}"
        graph = ProtocolGraph(protocol_def)
        task_map = {t.name: t for t in protocol_def.tasks}

        task_graph = graph.get_task_graph()
        ancestors = {t: nx.ancestors(task_graph, t) for t in task_graph.nodes}
        all_tasks = set(task_graph.nodes)

        instances.append(
            ProtocolRunInstance(
                name=name,
                protocol_type=protocol_type,
                protocol_graph=graph,
                tasks=task_map,
                ancestors=ancestors,
                all_tasks=all_tasks,
            )
        )
    return instances


@dataclass
class SimLockEntry:
    """A device or resource lock held by a task in the simulation."""

    protocol_run_name: str
    task_name: str
    held: bool = False


class LockManager:
    """Exclusive device and resource locks for simulation with hold transparency."""

    def __init__(self) -> None:
        self._device_locks: dict[tuple[str, str], SimLockEntry] = {}
        self._resource_locks: dict[str, SimLockEntry] = {}

    def is_device_available(
        self,
        lab_name: str,
        device_name: str,
        protocol_run_name: str,
        task_name: str,
        ancestors: set[str] | None = None,
        completed_tasks: set[str] | None = None,
    ) -> bool:
        entry = self._device_locks.get((lab_name, device_name))
        if entry is None:
            return True
        if entry.protocol_run_name == protocol_run_name and entry.task_name == task_name:
            return True
        return self._is_hold_transparent(entry, protocol_run_name, task_name, ancestors, completed_tasks)

    def is_resource_available(
        self,
        resource_name: str,
        protocol_run_name: str,
        task_name: str,
        ancestors: set[str] | None = None,
        completed_tasks: set[str] | None = None,
    ) -> bool:
        entry = self._resource_locks.get(resource_name)
        if entry is None:
            return True
        if entry.protocol_run_name == protocol_run_name and entry.task_name == task_name:
            return True
        return self._is_hold_transparent(entry, protocol_run_name, task_name, ancestors, completed_tasks)

    @staticmethod
    def _is_hold_transparent(
        entry: SimLockEntry,
        protocol_run_name: str,
        task_name: str,
        ancestors: set[str] | None,
        completed_tasks: set[str] | None,
    ) -> bool:
        return bool(
            entry.held
            and ancestors
            and completed_tasks
            and entry.protocol_run_name == protocol_run_name
            and entry.task_name in completed_tasks
            and entry.task_name in ancestors
        )

    def lock_device(self, lab_name: str, device_name: str, protocol_run_name: str, task_name: str) -> None:
        self._device_locks[(lab_name, device_name)] = SimLockEntry(protocol_run_name, task_name)

    def lock_resource(self, resource_name: str, protocol_run_name: str, task_name: str) -> None:
        self._resource_locks[resource_name] = SimLockEntry(protocol_run_name, task_name)

    def release_task(
        self,
        protocol_run_name: str,
        task_name: str,
        device_hold_keys: set[tuple[str, str]],
        resource_hold_keys: set[str],
        has_pending_successors: bool,
    ) -> None:
        """Release locks for a completed task, holding where configured and successors exist."""
        for key, entry in list(self._device_locks.items()):
            if entry.protocol_run_name != protocol_run_name or entry.task_name != task_name:
                continue
            if key in device_hold_keys and has_pending_successors:
                entry.held = True
            else:
                del self._device_locks[key]

        for key, entry in list(self._resource_locks.items()):
            if entry.protocol_run_name != protocol_run_name or entry.task_name != task_name:
                continue
            if key in resource_hold_keys and has_pending_successors:
                entry.held = True
            else:
                del self._resource_locks[key]

    def release_all_for_protocol_run(self, protocol_run_name: str) -> None:
        """Release all locks for a protocol run (including held)."""
        self._device_locks = {k: v for k, v in self._device_locks.items() if v.protocol_run_name != protocol_run_name}
        self._resource_locks = {
            k: v for k, v in self._resource_locks.items() if v.protocol_run_name != protocol_run_name
        }

    @property
    def device_locks(self) -> dict[tuple[str, str], SimLockEntry]:
        return self._device_locks

    @property
    def resource_locks(self) -> dict[str, SimLockEntry]:
        return self._resource_locks


class SimGreedyScheduler:
    """Synchronous greedy scheduler for simulation."""

    def __init__(
        self,
        devices_by_type: dict[str, list[tuple[str, str]]],
        resources_by_type: dict[str, list[str]],
        lock_manager: LockManager,
        verbose: bool = False,
    ) -> None:
        self._devices_by_type = devices_by_type
        self._resources_by_type = resources_by_type
        self._locks = lock_manager
        self._verbose = verbose

    def schedule(
        self,
        protocol_runs: list[ProtocolRunInstance],
        running_tasks: set[tuple[str, str]],
        current_time: int = 0,
    ) -> list[ScheduledSimTask]:
        """One scheduling cycle across all active protocols."""
        scheduled: list[ScheduledSimTask] = []

        for exp in protocol_runs:
            if exp.completed_tasks == exp.all_tasks:
                continue

            topo_order = exp.protocol_graph.get_topologically_sorted_tasks()
            for task_name in topo_order:
                if task_name in exp.completed_tasks or (exp.name, task_name) in running_tasks:
                    continue
                result = self._try_schedule_task(exp, task_name)
                if result:
                    scheduled.append(result)

        return scheduled

    def _try_schedule_task(self, exp: ProtocolRunInstance, task_name: str) -> ScheduledSimTask | None:
        task = exp.tasks[task_name]
        deps = exp.protocol_graph.get_task_dependencies(task_name)
        if not all(d in exp.completed_tasks for d in deps):
            if self._verbose:
                unmet = [d for d in deps if d not in exp.completed_tasks]
                _echo(f"  [skip] {exp.name}.{task_name}: unmet deps {unmet}")
            return None

        ancestors = exp.ancestors.get(task_name, set())

        resolved_resources = self._resolve_resources(exp, task, ancestors)
        if resolved_resources is None:
            if self._verbose:
                _echo(f"  [skip] {exp.name}.{task_name}: resources unavailable")
            return None

        resolved_devices = self._resolve_devices(exp, task, ancestors)
        if resolved_devices is None:
            if self._verbose:
                _echo(f"  [skip] {exp.name}.{task_name}: devices unavailable")
            return None

        if not self._check_all_available(
            exp.name, task_name, resolved_devices, resolved_resources, ancestors, exp.completed_tasks
        ):
            if self._verbose:
                _echo(f"  [skip] {exp.name}.{task_name}: lock conflict")
            return None

        for dev in resolved_devices.values():
            self._locks.lock_device(dev.lab_name, dev.name, exp.name, task_name)
        for res_name in resolved_resources.values():
            self._locks.lock_resource(res_name, exp.name, task_name)

        return ScheduledSimTask(
            protocol_run_name=exp.name,
            task_name=task_name,
            duration=task.duration,
            devices=resolved_devices,
            resources=resolved_resources,
        )

    def _resolve_resources(self, exp: ProtocolRunInstance, task: TaskDef, ancestors: set[str]) -> dict[str, str] | None:
        resolved: dict[str, str] = {}
        chosen: set[str] = set()

        for slot, value in task.resources.items():
            if isinstance(value, str) and is_resource_reference(value):
                ref_task, ref_slot = value.split(".")
                assignments = exp.task_resource_assignments.get(ref_task)
                if assignments is None or ref_slot not in assignments:
                    return None
                concrete = assignments[ref_slot]
                resolved[slot] = concrete
                chosen.add(concrete)
            elif isinstance(value, str):
                if not self._locks.is_resource_available(value, exp.name, task.name, ancestors, exp.completed_tasks):
                    return None
                if value in chosen:
                    continue
                resolved[slot] = value
                chosen.add(value)

        for slot, value in task.resources.items():
            if isinstance(value, DynamicResourceAssignmentDef):
                pool = sort_resource_pool(self._resources_by_type.get(value.resource_type, []))
                selected = None
                for res_name in pool:
                    if res_name in chosen:
                        continue
                    if self._locks.is_resource_available(res_name, exp.name, task.name, ancestors, exp.completed_tasks):
                        selected = res_name
                        break
                if selected is None:
                    return None
                resolved[slot] = selected
                chosen.add(selected)

        return resolved

    def _resolve_devices(
        self, exp: ProtocolRunInstance, task: TaskDef, ancestors: set[str]
    ) -> dict[str, DeviceAssignmentDef] | None:
        assigned: dict[str, DeviceAssignmentDef] = {}
        chosen_pairs: set[tuple[str, str]] = set()

        for slot, dev in task.devices.items():
            if isinstance(dev, DeviceAssignmentDef):
                assigned[slot] = dev
                chosen_pairs.add((dev.lab_name, dev.name))

        for slot, dev in task.devices.items():
            if isinstance(dev, str) and is_device_reference(dev):
                ref_task, ref_slot = dev.split(".")
                dev_assignments = exp.task_device_assignments.get(ref_task)
                if dev_assignments is None or ref_slot not in dev_assignments:
                    return None
                resolved_dev = dev_assignments[ref_slot]
                assigned[slot] = resolved_dev
                chosen_pairs.add((resolved_dev.lab_name, resolved_dev.name))

        for slot, dev in task.devices.items():
            if not isinstance(dev, DynamicDeviceAssignmentDef):
                continue
            pool = filter_device_pool(dev, self._devices_by_type.get(dev.device_type, []))
            if not pool:
                return None

            selected = None
            for lab_name, dev_name in pool:
                if (lab_name, dev_name) in chosen_pairs:
                    continue
                if self._locks.is_device_available(
                    lab_name, dev_name, exp.name, task.name, ancestors, exp.completed_tasks
                ):
                    selected = DeviceAssignmentDef(lab_name=lab_name, name=dev_name)
                    break
            if selected is None:
                return None
            assigned[slot] = selected
            chosen_pairs.add((selected.lab_name, selected.name))

        return assigned

    def _check_all_available(
        self,
        protocol_run_name: str,
        task_name: str,
        devices: dict[str, DeviceAssignmentDef],
        resources: dict[str, str],
        ancestors: set[str],
        completed_tasks: set[str] | None = None,
    ) -> bool:
        for dev in devices.values():
            if not self._locks.is_device_available(
                dev.lab_name, dev.name, protocol_run_name, task_name, ancestors, completed_tasks
            ):
                return False
        for res_name in resources.values():
            if not self._locks.is_resource_available(
                res_name, protocol_run_name, task_name, ancestors, completed_tasks
            ):
                return False
        return True


class SimCpSatScheduler:
    """CP-SAT scheduler for simulation using EOS's CpSatSchedulingSolver.

    Only recomputes the schedule when protocols are registered or unregistered
    (marked stale), matching the real EOS CP-SAT scheduler behavior.
    """

    def __init__(
        self,
        devices_by_type: dict[str, list[tuple[str, str]]],
        resources_by_type_with_labs: dict[str, list[tuple[str, str]]],
        lock_manager: LockManager,
        verbose: bool = False,
    ) -> None:
        self._devices_by_type = devices_by_type
        self._resources_by_type_with_labs = resources_by_type_with_labs
        self._locks = lock_manager
        self._verbose = verbose
        self._schedule: dict[str, dict[str, int]] = {}
        self._device_assignments: dict[str, dict[str, dict[str, DeviceAssignmentDef]]] = {}
        self._resource_assignments: dict[str, dict[str, dict[str, str]]] = {}
        self._task_durations: dict[str, dict[str, int]] = {}
        self._schedule_is_stale = True

    def mark_stale(self) -> None:
        """Mark the schedule as stale, triggering a recompute on the next scheduling cycle."""
        self._schedule_is_stale = True

    def schedule(
        self,
        protocol_runs: list[ProtocolRunInstance],
        running_tasks: set[tuple[str, str]],
        current_time: int = 0,
    ) -> list[ScheduledSimTask]:
        """Return tasks ready to start at current_time, recomputing schedule only if stale."""
        if not self._has_pending_tasks(protocol_runs, running_tasks):
            return []

        if self._schedule_is_stale:
            self._recompute(protocol_runs, running_tasks, current_time)
            self._schedule_is_stale = False

        return self._extract_ready_tasks(protocol_runs, running_tasks, current_time)

    @staticmethod
    def _has_pending_tasks(protocol_runs: list[ProtocolRunInstance], running_tasks: set[tuple[str, str]]) -> bool:
        for exp in protocol_runs:
            running_in_exp = {tn for en, tn in running_tasks if en == exp.name}
            if exp.all_tasks - exp.completed_tasks - running_in_exp:
                return True
        return False

    def _recompute(
        self,
        protocol_runs: list[ProtocolRunInstance],
        running_tasks: set[tuple[str, str]],
        current_time: int,
    ) -> None:
        from eos.scheduling.cpsat_scheduling_solver import CpSatSchedulingSolver  # noqa: PLC0415

        protocol_run_map = {exp.name: (exp.protocol_type, exp.protocol_graph) for exp in protocol_runs}
        completed_by_exp = {exp.name: set(exp.completed_tasks) for exp in protocol_runs}
        running_by_exp: dict[str, set[str]] = {}

        for run in protocol_runs:
            running_by_exp[run.name] = {tn for en, tn in running_tasks if en == run.name}

        solver = CpSatSchedulingSolver(
            protocol_runs=protocol_run_map,
            task_durations=self._task_durations,
            schedule=self._schedule,
            completed_by_exp=completed_by_exp,
            running_by_exp=running_by_exp,
            current_time=current_time,
            protocol_run_priorities={exp.name: 0 for exp in protocol_runs},
            eligible_devices_by_type=self._devices_by_type,
            eligible_resources_by_type=self._resources_by_type_with_labs,
            previous_device_assignments=self._device_assignments,
            previous_resource_assignments=self._resource_assignments,
        )
        solution = solver.solve()
        self._schedule = solution.schedule
        self._device_assignments = solution.device_assignments
        self._resource_assignments = solution.resource_assignments
        self._task_durations = {exp.name: {} for exp in protocol_runs}

    def _extract_ready_tasks(
        self,
        protocol_runs: list[ProtocolRunInstance],
        running_tasks: set[tuple[str, str]],
        current_time: int,
    ) -> list[ScheduledSimTask]:
        """Extract tasks whose planned start_time <= current_time from the solver's schedule."""
        scheduled: list[ScheduledSimTask] = []
        for exp in protocol_runs:
            for task_name, start_time in self._schedule.get(exp.name, {}).items():
                if task_name in exp.completed_tasks or (exp.name, task_name) in running_tasks:
                    continue
                if start_time > current_time:
                    continue

                task = exp.tasks[task_name]
                devices = self._device_assignments.get(exp.name, {}).get(task_name, {})
                resources = self._resource_assignments.get(exp.name, {}).get(task_name, {})

                for dev in devices.values():
                    self._locks.lock_device(dev.lab_name, dev.name, exp.name, task_name)
                for res_name in resources.values():
                    self._locks.lock_resource(res_name, exp.name, task_name)

                scheduled.append(
                    ScheduledSimTask(
                        protocol_run_name=exp.name,
                        task_name=task_name,
                        duration=task.duration,
                        devices=devices,
                        resources=resources,
                    )
                )
        return scheduled


class Simulator:
    """Discrete-event simulation of the EOS scheduler."""

    def __init__(
        self,
        labs: dict[str, LabDef],
        all_instances: list[ProtocolRunInstance],
        concurrency_limits: dict[str, int] | None = None,
        verbose: bool = False,
        jitter: float = 0.0,
        scheduler_type: str = "greedy",
    ) -> None:
        self._instance_map: dict[str, ProtocolRunInstance] = {exp.name: exp for exp in all_instances}
        self._concurrency_limits = concurrency_limits or {}
        self._lock_manager = LockManager()

        devices_by_type, resources_by_type = build_type_indices(labs)
        if scheduler_type == "cpsat":
            resources_by_type_with_labs = _build_resources_with_labs(labs)
            self._scheduler: SimGreedyScheduler | SimCpSatScheduler = SimCpSatScheduler(
                devices_by_type, resources_by_type_with_labs, self._lock_manager, verbose=verbose
            )
        else:
            self._scheduler = SimGreedyScheduler(
                devices_by_type, resources_by_type, self._lock_manager, verbose=verbose
            )
        self._use_holds = not isinstance(self._scheduler, SimCpSatScheduler)
        self._jitter = jitter
        self._running_tasks: list[RunningTask] = []
        self._running_set: set[tuple[str, str]] = set()
        self._timeline: list[TimelineEvent] = []
        self._current_time = 0
        self._verbose = verbose

        self._active: list[ProtocolRunInstance] = []
        self._queued: list[ProtocolRunInstance] = list(all_instances)
        self._completed_protocol_runs: set[str] = set()
        self._total_protocol_runs = len(all_instances)

        self._scheduler_time_ms = 0.0
        self._scheduler_calls = 0

    def run(self) -> list[TimelineEvent]:
        """Run the simulation to completion, returning the event timeline."""
        self._activate_protocol_runs()

        while len(self._completed_protocol_runs) < self._total_protocol_runs or self._queued:
            self._complete_tasks()
            self._activate_protocol_runs()

            incomplete = [e for e in self._active if e.name not in self._completed_protocol_runs]

            if self._verbose:
                _echo(f"\n--- t={self._current_time}s ---")

            with Timer() as t:
                scheduled = self._scheduler.schedule(incomplete, self._running_set, self._current_time)
            self._scheduler_time_ms += t.get_duration("ms")
            self._scheduler_calls += 1

            for s in scheduled:
                actual_duration = s.duration
                if self._jitter > 0 and s.duration > 0:
                    factor = 1.0 + random.uniform(-self._jitter, self._jitter)  # noqa: S311
                    actual_duration = max(1, round(s.duration * factor))
                rt = RunningTask(
                    protocol_run_name=s.protocol_run_name,
                    task_name=s.task_name,
                    start_time=self._current_time,
                    end_time=self._current_time + actual_duration,
                    devices=s.devices,
                    resources=s.resources,
                )
                self._running_tasks.append(rt)
                self._running_set.add((s.protocol_run_name, s.task_name))
                self._timeline.append(
                    TimelineEvent(
                        time=self._current_time,
                        event_type="START",
                        protocol_run_name=s.protocol_run_name,
                        task_name=s.task_name,
                        devices=s.devices,
                        resources=s.resources,
                        duration=actual_duration,
                    )
                )
                exp = self._instance_map[s.protocol_run_name]
                exp.task_resource_assignments[s.task_name] = dict(s.resources)
                exp.task_device_assignments[s.task_name] = dict(s.devices)

            if self._running_tasks:
                self._current_time = min(rt.end_time for rt in self._running_tasks)
            elif len(self._completed_protocol_runs) < self._total_protocol_runs or self._queued:
                next_time = self._next_scheduled_start()
                if next_time is not None:
                    self._current_time = next_time
                else:
                    _echo_err("\nDEADLOCK: No running tasks but protocols are incomplete!")
                    self._print_deadlock_info()
                    break

        return self._timeline

    def _activate_protocol_runs(self) -> None:
        still_queued: list[ProtocolRunInstance] = []
        activated = False
        for exp in self._queued:
            limit = self._concurrency_limits.get(exp.protocol_type, 0)
            if limit > 0:
                active_count = sum(
                    1
                    for a in self._active
                    if a.protocol_type == exp.protocol_type and a.name not in self._completed_protocol_runs
                )
                if active_count >= limit:
                    still_queued.append(exp)
                    continue
            self._active.append(exp)
            activated = True
        self._queued = still_queued
        if activated and not self._use_holds:
            self._scheduler.mark_stale()

    def _complete_tasks(self) -> None:
        completed = [rt for rt in self._running_tasks if rt.end_time <= self._current_time]
        self._running_tasks = [rt for rt in self._running_tasks if rt.end_time > self._current_time]

        for rt in completed:
            self._running_set.discard((rt.protocol_run_name, rt.task_name))
            exp = self._instance_map[rt.protocol_run_name]

            if self._use_holds:
                task = exp.tasks[rt.task_name]
                device_hold_keys = {
                    (rt.devices[slot].lab_name, rt.devices[slot].name)
                    for slot in task.device_holds
                    if task.device_holds[slot] and slot in rt.devices
                }
                resource_hold_keys = {
                    rt.resources[slot]
                    for slot in task.resource_holds
                    if task.resource_holds[slot] and slot in rt.resources
                }
                graph = exp.protocol_graph.get_graph()
                has_pending_successors = any(
                    graph.nodes[s].get("node_type") == "task" and s not in exp.completed_tasks
                    for s in graph.successors(rt.task_name)
                )
                self._lock_manager.release_task(
                    rt.protocol_run_name, rt.task_name, device_hold_keys, resource_hold_keys, has_pending_successors
                )
                if self._verbose and (device_hold_keys or resource_hold_keys) and has_pending_successors:
                    for dp in device_hold_keys:
                        _echo(f"  [hold] {dp[0]}.{dp[1]} kept under {rt.protocol_run_name}.{rt.task_name}")
                    for rn in resource_hold_keys:
                        _echo(f"  [hold] resource {rn} kept under {rt.protocol_run_name}.{rt.task_name}")
            else:
                self._lock_manager.release_task(rt.protocol_run_name, rt.task_name, set(), set(), False)

            exp.completed_tasks.add(rt.task_name)
            if exp.completed_tasks == exp.all_tasks:
                self._completed_protocol_runs.add(exp.name)
                self._lock_manager.release_all_for_protocol_run(exp.name)

            self._timeline.append(
                TimelineEvent(
                    time=self._current_time,
                    event_type="DONE",
                    protocol_run_name=rt.protocol_run_name,
                    task_name=rt.task_name,
                    devices=rt.devices,
                    resources=rt.resources,
                    duration=rt.end_time - rt.start_time,
                )
            )

    def _next_scheduled_start(self) -> int | None:
        """Find the next future start time in the CP-SAT schedule, if any."""
        if self._use_holds:
            return None
        next_start = None
        for exp in self._active:
            if exp.name in self._completed_protocol_runs:
                continue
            for task_name, start_time in self._scheduler._schedule.get(exp.name, {}).items():
                if task_name in exp.completed_tasks:
                    continue
                if start_time > self._current_time and (next_start is None or start_time < next_start):
                    next_start = start_time
        return next_start

    @property
    def scheduler_time_ms(self) -> float:
        return self._scheduler_time_ms

    @property
    def scheduler_calls(self) -> int:
        return self._scheduler_calls

    def _print_deadlock_info(self) -> None:
        if self._queued:
            _echo_err(f"\n  {len(self._queued)} protocol run(s) still queued (awaiting concurrency slots)")
        for exp in self._active:
            remaining = exp.all_tasks - exp.completed_tasks
            if remaining:
                _echo_err(f"  {exp.name}: pending tasks = {sorted(remaining)}")
                for task_name in sorted(remaining):
                    deps = exp.protocol_graph.get_task_dependencies(task_name)
                    unmet = [d for d in deps if d not in exp.completed_tasks]
                    if unmet:
                        _echo_err(f"    {task_name}: waiting on deps {unmet}")
                    else:
                        _echo_err(f"    {task_name}: deps met, blocked on resources/devices")

        if self._lock_manager.device_locks:
            _echo_err("\n  Active device locks:")
            for (lab, dev), entry in sorted(self._lock_manager.device_locks.items()):
                held_tag = " [HELD]" if entry.held else ""
                _echo_err(f"    {lab}.{dev} -> {entry.protocol_run_name}.{entry.task_name}{held_tag}")
        if self._lock_manager.resource_locks:
            _echo_err("\n  Active resource locks:")
            for res, entry in sorted(self._lock_manager.resource_locks.items()):
                held_tag = " [HELD]" if entry.held else ""
                _echo_err(f"    {res} -> {entry.protocol_run_name}.{entry.task_name}{held_tag}")


def _echo(msg: str) -> None:
    sys.stdout.write(msg + "\n")


def _echo_err(msg: str) -> None:
    sys.stderr.write(msg + "\n")


_SECONDS_PER_MINUTE = 60
_SECONDS_PER_HOUR = 3600


def format_time(seconds: int) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds < _SECONDS_PER_MINUTE:
        return f"{seconds}s"
    if seconds < _SECONDS_PER_HOUR:
        m, s = divmod(seconds, _SECONDS_PER_MINUTE)
        return f"{m}m{s:02d}s" if s else f"{m}m"
    h, rem = divmod(seconds, _SECONDS_PER_HOUR)
    m, s = divmod(rem, _SECONDS_PER_MINUTE)
    parts = [f"{h}h"]
    if m:
        parts.append(f"{m:02d}m")
    if s:
        parts.append(f"{s:02d}s")
    return "".join(parts)


def print_timeline(timeline: list[TimelineEvent]) -> None:
    """Print a formatted timeline of all simulation events."""
    if not timeline:
        _echo("No events.")
        return

    events = sorted(timeline, key=lambda e: (e.time, 0 if e.event_type == "DONE" else 1))
    max_time_len = len(str(events[-1].time))

    _echo("\n" + "=" * 100)
    _echo("TIMELINE")
    _echo("=" * 100)

    for ev in events:
        time_str = f"{ev.time:>{max_time_len}}s"
        tag = ev.event_type
        task_id = f"{ev.protocol_run_name}.{ev.task_name}"

        if ev.event_type == "START":
            devices_str = ", ".join(f"{d.lab_name}.{d.name}" for d in ev.devices.values()) if ev.devices else "-"
            resources_str = ", ".join(ev.resources.values()) if ev.resources else "-"
            _echo(f"  [{time_str}] {tag:<5}  {task_id:<45} | devices: {devices_str}")
            if ev.resources:
                _echo(f"  {' ' * (max_time_len + 2)}       {' ' * 45} | resources: {resources_str}")
        else:
            _echo(f"  [{time_str}] {tag:<5}  {task_id:<45} | dur={format_time(ev.duration)}")


def print_stats(timeline: list[TimelineEvent]) -> None:
    """Print summary statistics for the simulation."""
    if not timeline:
        return

    starts = [e for e in timeline if e.event_type == "START"]
    completions = [e for e in timeline if e.event_type == "DONE"]
    if not completions:
        return

    makespan = max(e.time for e in completions)
    if makespan == 0:
        return

    _echo("\n" + "=" * 100)
    _echo("SUMMARY STATISTICS")
    _echo("=" * 100)

    _echo(f"\n  Makespan: {format_time(makespan)}")

    _echo("\n  ProtocolRun completion times:")
    run_times: dict[str, int] = {}
    for ev in completions:
        run_times[ev.protocol_run_name] = max(run_times.get(ev.protocol_run_name, 0), ev.time)
    for run_name in sorted(run_times):
        _echo(f"    {run_name:<40} {format_time(run_times[run_name])}")

    _print_device_utilization(starts, makespan)
    _print_resource_utilization(starts, makespan)
    _print_parallelism(starts, makespan)


def _merged_busy_time(intervals: list[tuple[int, int]]) -> int:
    """Compute total busy time from a list of (start, end) intervals, merging overlaps."""
    if not intervals:
        return 0
    sorted_intervals = sorted(intervals)
    total = 0
    cur_start, cur_end = sorted_intervals[0]
    for start, end in sorted_intervals[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            total += cur_end - cur_start
            cur_start, cur_end = start, end
    total += cur_end - cur_start
    return total


def _print_device_utilization(starts: list[TimelineEvent], makespan: int) -> None:
    device_intervals: dict[str, list[tuple[int, int]]] = {}
    for ev in starts:
        for dev in ev.devices.values():
            key = f"{dev.lab_name}.{dev.name}"
            device_intervals.setdefault(key, []).append((ev.time, ev.time + ev.duration))

    if device_intervals:
        _echo(f"\n  Device utilization (of {format_time(makespan)} makespan):")
        for dev_key in sorted(device_intervals):
            busy = _merged_busy_time(device_intervals[dev_key])
            pct = (busy / makespan) * 100
            bar = "#" * int(pct / 2) + "." * (50 - int(pct / 2))
            _echo(f"    {dev_key:<35} {format_time(busy):>8} ({pct:5.1f}%) |{bar}|")


def _print_resource_utilization(starts: list[TimelineEvent], makespan: int) -> None:
    resource_intervals: dict[str, list[tuple[int, int]]] = {}
    for ev in starts:
        for res_name in ev.resources.values():
            resource_intervals.setdefault(res_name, []).append((ev.time, ev.time + ev.duration))

    if resource_intervals:
        _echo(f"\n  Resource utilization (of {format_time(makespan)} makespan):")
        for res_key in sorted(resource_intervals):
            busy = _merged_busy_time(resource_intervals[res_key])
            pct = (busy / makespan) * 100
            _echo(f"    {res_key:<35} {format_time(busy):>8} ({pct:5.1f}%)")


def _print_parallelism(starts: list[TimelineEvent], makespan: int) -> None:
    deltas: list[tuple[int, int]] = []
    for ev in starts:
        deltas.append((ev.time, +1))
        deltas.append((ev.time + ev.duration, -1))
    deltas.sort(key=lambda x: (x[0], x[1]))

    max_parallel = 0
    current = 0
    weighted_sum = 0
    prev_time = 0
    for t, d in deltas:
        if t != prev_time:
            weighted_sum += current * (t - prev_time)
            prev_time = t
        current += d
        max_parallel = max(max_parallel, current)
    if prev_time < makespan:
        weighted_sum += current * (makespan - prev_time)

    avg_parallel = weighted_sum / makespan if makespan > 0 else 0

    _echo("\n  Parallelism:")
    _echo(f"    Max concurrent tasks:  {max_parallel}")
    _echo(f"    Avg concurrent tasks:  {avg_parallel:.2f}")
    _echo(f"    Total task count:      {len(starts)}")

    total_task_time = sum(ev.duration for ev in starts)
    _echo(f"    Total task-seconds:    {format_time(total_task_time)}")
    theoretical_min = format_time(total_task_time // max_parallel) if max_parallel else "N/A"
    _echo(f"    Theoretical min (no contention): {format_time(total_task_time)} / {max_parallel} = {theoretical_min}")
    efficiency = (total_task_time / (makespan * max_parallel)) * 100 if max_parallel else 0
    _echo(f"    Scheduling efficiency: {efficiency:.1f}%")


def _print_scheduler_overhead(scheduler_ms: float, scheduler_calls: int) -> None:
    _echo("\n  Scheduler overhead:")
    _echo(f"    Total scheduler time:  {scheduler_ms:.1f} ms ({scheduler_calls} calls)")
    if scheduler_calls > 0:
        _echo(f"    Avg per call:          {scheduler_ms / scheduler_calls:.2f} ms")


def run_simulation(
    config_path: str,
    user_dir: str,
    verbose: bool = False,
    jitter: float = 0.0,
    seed: int | None = None,
    scheduler_type: str = "greedy",
    quiet: bool = False,
) -> list[TimelineEvent]:
    """Run a complete scheduling simulation and print results."""
    echo = _echo if not quiet else lambda *_a, **_k: None

    if seed is not None:
        random.seed(seed)
    elif jitter > 0:
        seed = random.randint(0, 2**32 - 1)  # noqa: S311
        echo(f"Random seed: {seed} (use --seed {seed} to reproduce)")
        random.seed(seed)

    sim_config = load_sim_config(config_path)
    labs, protocols = load_simulation_data(sim_config, Path(user_dir))

    echo(f"Loaded {len(labs)} lab(s): {', '.join(sorted(labs.keys()))}")
    for lab in labs.values():
        echo(f"  {lab.name}: {len(lab.devices)} devices, {len(lab.resources)} resources")

    all_instances: list[ProtocolRunInstance] = []
    concurrency_limits: dict[str, int] = {}

    for protocol_run in sim_config.protocol_runs:
        protocol_def = protocols[protocol_run.type]
        instances = create_protocol_run_instances(protocol_run.type, protocol_def, protocol_run.iterations)
        all_instances.extend(instances)
        total_duration = sum(t.duration for t in protocol_def.tasks)
        echo(
            f"Created {len(instances)} instance(s) of '{protocol_run.type}' "
            f"({len(protocol_def.tasks)} tasks, {total_duration}s total per iteration)"
        )
        if protocol_run.max_concurrent > 0:
            concurrency_limits[protocol_run.type] = protocol_run.max_concurrent

    echo(f"\nTotal: {len(all_instances)} protocol run instances")
    for protocol_type, limit in concurrency_limits.items():
        echo(f"  {protocol_type}: max {limit} concurrent")

    echo(f"\nStarting simulation (scheduler={scheduler_type})...")
    sim = Simulator(
        labs,
        all_instances,
        concurrency_limits=concurrency_limits,
        verbose=verbose,
        jitter=jitter,
        scheduler_type=scheduler_type,
    )
    timeline = sim.run()

    if not quiet:
        print_timeline(timeline)
        print_stats(timeline)
        _print_scheduler_overhead(sim.scheduler_time_ms, sim.scheduler_calls)

    return timeline


def compute_sim_stats(
    starts: list[TimelineEvent],
    completions: list[TimelineEvent],
    scheduler_type: str,
) -> dict:
    """Compute summary statistics from simulation timeline events."""
    makespan = max((e.time for e in completions), default=0)

    run_times: dict[str, int] = {}
    for ev in completions:
        run_times[ev.protocol_run_name] = max(run_times.get(ev.protocol_run_name, 0), ev.time)
    run_completions = [(name, format_time(t)) for name, t in sorted(run_times.items())]

    device_intervals: dict[str, list[tuple[int, int]]] = {}
    for ev in starts:
        for d in ev.devices.values():
            key = f"{d.lab_name}.{d.name}"
            device_intervals.setdefault(key, []).append((ev.time, ev.time + ev.duration))
    device_util = []
    for name in sorted(device_intervals):
        busy = _merged_busy_time(device_intervals[name])
        pct = (busy / makespan) * 100 if makespan else 0
        device_util.append({"name": name, "time_fmt": format_time(busy), "pct": pct})

    resource_intervals: dict[str, list[tuple[int, int]]] = {}
    for ev in starts:
        for res_name in ev.resources.values():
            resource_intervals.setdefault(res_name, []).append((ev.time, ev.time + ev.duration))
    resource_util = []
    for name in sorted(resource_intervals):
        busy = _merged_busy_time(resource_intervals[name])
        pct = (busy / makespan) * 100 if makespan else 0
        resource_util.append({"name": name, "time_fmt": format_time(busy), "pct": pct})

    deltas: list[tuple[int, int]] = []
    for ev in starts:
        deltas.append((ev.time, +1))
        deltas.append((ev.time + ev.duration, -1))
    deltas.sort(key=lambda x: (x[0], x[1]))

    max_parallel = 0
    current = 0
    weighted_sum = 0
    prev_time = 0
    for t, d in deltas:
        if t != prev_time:
            weighted_sum += current * (t - prev_time)
            prev_time = t
        current += d
        max_parallel = max(max_parallel, current)
    if prev_time < makespan:
        weighted_sum += current * (makespan - prev_time)

    avg_parallel = weighted_sum / makespan if makespan else 0
    total_task_time = sum(ev.duration for ev in starts)
    theoretical_min = total_task_time // max_parallel if max_parallel else 0
    efficiency = (total_task_time / (makespan * max_parallel)) * 100 if max_parallel and makespan else 0

    return {
        "makespan": makespan,
        "makespan_fmt": format_time(makespan),
        "scheduler_type": scheduler_type,
        "total_tasks": len(starts),
        "run_completions": run_completions,
        "device_util": device_util,
        "resource_util": resource_util,
        "max_parallel": max_parallel,
        "avg_parallel": avg_parallel,
        "total_task_time_fmt": format_time(total_task_time),
        "theoretical_min_fmt": format_time(theoretical_min),
        "efficiency": efficiency,
    }
