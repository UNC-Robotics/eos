import threading
from collections import defaultdict
from dataclasses import dataclass
from itertools import pairwise

import networkx as nx
from ortools.sat.python import cp_model
from ortools.sat.sat_parameters_pb2 import SatParameters

from eos.configuration.entities.task_def import (
    DeviceAssignmentDef,
    DynamicDeviceAssignmentDef,
    DynamicResourceAssignmentDef,
    TaskDef,
)
from eos.configuration.protocol_graph import ProtocolGraph
from eos.configuration.utils import is_resource_reference
from eos.logging.logger import log
from eos.scheduling.entities.planned_task import PlannedTask
from eos.scheduling.exceptions import EosSchedulerError
from eos.scheduling.utils import compute_hold_users, filter_device_pool, resolve_device_root, resolve_resource_root
from eos.utils.timer import Timer

DEVICE, RESOURCE = "device", "resource"


@dataclass(slots=True)
class TaskVariables:
    start: cp_model.IntVar
    end: cp_model.IntVar
    interval: cp_model.IntervalVar


@dataclass(slots=True)
class SchedulingSolution:
    schedule: dict[str, dict[str, int]]
    device_assignments: dict[str, dict[str, dict[str, DeviceAssignmentDef]]]
    resource_assignments: dict[str, dict[str, dict[str, str]]]
    makespan: int
    compute_duration_ms: float
    status: str


@dataclass(frozen=True, slots=True)
class HeldAllocation:
    """A device or resource held by a completed task of a run for its pending hold users."""

    protocol_run_name: str
    kind: str  # DEVICE or RESOURCE
    item: object  # (lab_name, device_name) or resource name
    hold_users: frozenset[str]


def _named_item(kind: str, value: object) -> object | None:
    """The item a slot value names, as an allocation index key, or None if it does not name one."""
    if kind == DEVICE and isinstance(value, DeviceAssignmentDef):
        return value.lab_name, value.name
    if kind == RESOURCE and isinstance(value, str) and not is_resource_reference(value):
        return value
    return None


@dataclass(frozen=True, slots=True)
class _Use:
    """A task slot's use of a device or resource: a known item, or the item a dynamic slot chooses."""

    run: str
    task: str
    kind: str
    slot: str
    item: object | None  # Known item, as (lab_name, device_name) or a resource name
    root: tuple[str, str] | None  # Otherwise the (task, slot) whose choice decides the item
    named: bool  # Whether the protocol names the item itself, rather than referencing or requesting one

    @property
    def identity(self) -> tuple:
        return ("item", self.item) if self.item is not None else ("choice", self.root)


class CpSatSchedulingSolver:
    """
    CP-SAT model of the scheduling problem.

    Every task slot is a use of a device or resource. Uses connected by holds form a hold component, which occupies
    its item for one span (from its first to its last use) that no other protocol run may overlap. Inside the span
    the run's own uses take turns. This matches how the schedulers keep held items for their hold users.
    """

    @staticmethod
    def _create_default_parameters() -> SatParameters:
        """Create default CP-SAT solver parameters optimized for scheduling."""
        params = SatParameters()
        params.max_time_in_seconds = 15.0
        params.num_search_workers = 4
        params.push_all_tasks_toward_start = True
        params.optimize_with_lb_tree_search = False  # It discards solution hints, so warm starts would be lost
        params.use_objective_lb_search = True
        params.use_timetable_edge_finding_in_cumulative = True
        params.linearization_level = 2
        params.use_hard_precedences_in_cumulative = True
        params.use_strong_propagation_in_disjunctive = True
        params.use_dynamic_precedence_in_disjunctive = True
        return params

    def __init__(
        self,
        protocol_runs: dict[str, tuple[str, ProtocolGraph]],
        task_durations: dict[str, dict[str, int]],
        schedule: dict[str, dict[str, int]],
        completed_or_skipped_by_run: dict[str, set[str]],
        running_by_exp: dict[str, set[str]],
        current_time: int,
        protocol_run_priorities: dict[str, int],
        eligible_devices_by_type: dict[str, list[tuple[str, str]]],
        eligible_resources_by_type: dict[str, list[tuple[str, str]]],
        previous_device_assignments: dict[str, dict[str, dict[str, DeviceAssignmentDef]]] | None = None,
        previous_resource_assignments: dict[str, dict[str, dict[str, str]]] | None = None,
        parameter_overrides: dict[str, float | int | bool] | None = None,
        held_allocations: list[HeldAllocation] | None = None,
    ):
        self._protocol_runs = protocol_runs
        self._task_durations = task_durations
        self._schedule = schedule
        self._completed_or_skipped_by_run = completed_or_skipped_by_run
        self._running_by_exp = running_by_exp
        self._current_time = current_time
        self._protocol_run_priorities = protocol_run_priorities
        self._eligible_devices_by_type = eligible_devices_by_type
        self._eligible_resources_by_type = eligible_resources_by_type
        self._previous_device_assignments = previous_device_assignments or {}
        self._previous_resource_assignments = previous_resource_assignments or {}
        self._held_allocations = held_allocations or []

        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        self.solver.parameters.CopyFrom(self._create_default_parameters())
        for name, value in (parameter_overrides or {}).items():
            setattr(self.solver.parameters, name, value)

        # Task definitions are copied once, since ProtocolGraph.get_task copies on every call
        self._tasks: dict[str, dict[str, TaskDef]] = {
            run: {name: graph.get_task(name) for name in graph.get_task_graph().nodes}
            for run, (_, graph) in protocol_runs.items()
        }
        self._topo: dict[str, list[str]] = {
            run: graph.get_topologically_sorted_tasks() for run, (_, graph) in protocol_runs.items()
        }

        self._task_vars: dict[tuple[str, str], TaskVariables] = {}
        self._choices: dict[tuple[str, str, str, str], list[tuple[object, cp_model.IntVar]]] = {}
        self._uses: list[_Use] = []
        self._excluded: dict[str, set[str]] = {}
        self._ancestor_sets: dict[str, dict[str, set[str]]] = {}
        self._horizon = 0
        self._makespan: cp_model.IntVar | None = None
        self._stopped = threading.Event()
        self._hint: dict[tuple[str, str], PlannedTask] = {}

    @property
    def stopped(self) -> threading.Event:
        return self._stopped

    def stop(self) -> None:
        """Stop a running or not yet started solve. Safe to call from another thread."""
        self._stopped.set()
        self.solver.parameters.max_time_in_seconds = 0.0  # Applies if the search has not started yet
        self.solver.stop_search()

    # Model

    def _build_model(self) -> None:
        self._horizon = self._calculate_horizon()
        self._exclude_unsatisfiable_tasks()
        self._create_task_variables()
        self._apply_precedence_constraints()
        self._collect_uses()
        self._apply_item_constraints()
        self._apply_group_constraints()
        self._apply_solution_hints()

        self._makespan = self.model.NewIntVar(0, self._horizon, "makespan")
        self.model.AddMaxEquality(self._makespan, [tv.end for tv in self._task_vars.values()])

    def _calculate_horizon(self) -> int:
        """Record every task's duration and bound the schedule by twice the remaining work."""
        remaining = 0
        self._task_durations.clear()
        for run, tasks in self._tasks.items():
            self._task_durations[run] = {name: task.duration for name, task in tasks.items()}
            completed = self._completed_or_skipped_by_run.get(run, set())
            remaining += sum(task.duration for name, task in tasks.items() if name not in completed)
        return self._current_time + 2 * remaining + 1

    def _exclude_unsatisfiable_tasks(self) -> None:
        """Leave out tasks that no eligible device or resource can serve, and their descendants, so the rest plan."""
        for run, (_, graph) in self._protocol_runs.items():
            settled = self._completed_or_skipped_by_run.get(run, set()) | self._running_by_exp.get(run, set())
            unsatisfiable = {
                name
                for name, task in self._tasks[run].items()
                if name not in settled and not all(self._eligible(slot_def) for slot_def in self._dynamic_defs(task))
            }
            if unsatisfiable:
                task_graph = graph.get_task_graph()
                excluded = unsatisfiable.union(*(nx.descendants(task_graph, name) for name in unsatisfiable))
                self._excluded[run] = excluded - settled
                log.warning(f"RUN '{run}' - No eligible devices or resources for {sorted(unsatisfiable)}, not planned")

    @staticmethod
    def _dynamic_defs(task: TaskDef) -> list:
        return [
            *(d for d in task.devices.values() if isinstance(d, DynamicDeviceAssignmentDef)),
            *(r for r in task.resources.values() if isinstance(r, DynamicResourceAssignmentDef)),
        ]

    def _eligible(self, request: DynamicDeviceAssignmentDef | DynamicResourceAssignmentDef) -> list:
        """The items a dynamic request may choose, as allocation index keys."""
        if isinstance(request, DynamicDeviceAssignmentDef):
            return filter_device_pool(request, self._eligible_devices_by_type.get(request.device_type, ()))
        return [name for _, name in self._eligible_resources_by_type.get(request.resource_type, ())]

    def _create_task_variables(self) -> None:
        for run, order in self._topo.items():
            completed = self._completed_or_skipped_by_run.get(run, set()) | self._excluded.get(run, set())
            running = self._running_by_exp.get(run, set())
            for name in order:
                if name in completed:
                    continue
                task = self._tasks[run][name]
                is_running = name in running
                lower_bound = 0 if is_running else self._current_time
                start = self.model.NewIntVar(lower_bound, self._horizon, f"{run}_{name}_start")
                end = self.model.NewIntVar(lower_bound, self._horizon, f"{run}_{name}_end")
                interval = self.model.NewIntervalVar(start, task.duration, end, f"{run}_{name}_interval")
                self._task_vars[(run, name)] = TaskVariables(start, end, interval)

                if is_running:
                    self.model.Add(start == self._schedule.get(run, {}).get(name, self._current_time))
                    continue  # A running task keeps the devices and resources it has
                for kind, slots in ((DEVICE, task.devices), (RESOURCE, task.resources)):
                    for slot, value in slots.items():
                        if isinstance(value, DynamicDeviceAssignmentDef | DynamicResourceAssignmentDef):
                            choices = [
                                (item, self.model.NewBoolVar(f"{run}_{name}_{slot}_{item}"))
                                for item in self._eligible(value)
                            ]
                            self.model.AddExactlyOne(var for _, var in choices)
                            self._choices[(run, name, kind, slot)] = choices

    def _apply_precedence_constraints(self) -> None:
        for run, (_, graph) in self._protocol_runs.items():
            for name in self._topo[run]:
                if (run, name) not in self._task_vars:
                    continue
                for dependency in graph.get_task_dependencies(name):
                    if (run, dependency) in self._task_vars:
                        self.model.Add(self._task_vars[(run, name)].start >= self._task_vars[(run, dependency)].end)

    def _collect_uses(self) -> None:
        for run, name in self._task_vars:
            task = self._tasks[run][name]
            for kind, slots in ((DEVICE, task.devices), (RESOURCE, task.resources)):
                for slot, value in slots.items():
                    if (use := self._resolve_use(run, name, kind, slot, value)) is not None:
                        self._uses.append(use)

    def _resolve_use(self, run: str, task_name: str, kind: str, slot: str, value: object) -> _Use | None:
        """What a slot uses: a named item, the item a dynamic choice decides, or a known item it references."""
        if (item := _named_item(kind, value)) is not None:
            return _Use(run, task_name, kind, slot, item, None, named=True)

        root_task, root_slot = task_name, slot
        if isinstance(value, str):
            resolve = resolve_device_root if kind == DEVICE else resolve_resource_root
            if (root := resolve(self._tasks[run], *value.split("."))) is None:
                return None
            root_task, root_slot, root_value = root
            if (item := _named_item(kind, root_value)) is not None:
                return _Use(run, task_name, kind, slot, item, None, named=False)

        if (run, root_task, kind, root_slot) in self._choices:
            return _Use(run, task_name, kind, slot, None, (root_task, root_slot), named=False)
        # The root task already ran or is running, so the item is known
        previous = self._previous_device_assignments if kind == DEVICE else self._previous_resource_assignments
        item = previous.get(run, {}).get(root_task, {}).get(root_slot)
        if item is None:
            return None
        return _Use(run, task_name, kind, slot, _named_item(kind, item) or item, None, named=False)

    def _use_intervals(self, use: _Use) -> list[tuple[object, cp_model.IntervalVar]]:
        """The intervals a use occupies, per item it may use."""
        task_vars = self._task_vars[(use.run, use.task)]
        if use.item is not None:
            return [(use.item, task_vars.interval)]
        duration = self._tasks[use.run][use.task].duration
        return [
            (
                item,
                self.model.NewOptionalIntervalVar(
                    task_vars.start, duration, task_vars.end, chosen, f"{use.run}_{use.task}_{use.slot}_{item}"
                ),
            )
            for item, chosen in self._choices[(use.run, use.root[0], use.kind, use.root[1])]
        ]

    def _hold_components(self) -> list[tuple[str, str, tuple, list[_Use], bool]]:
        """Group uses connected by holds, as (run, kind, identity, uses, whether the item is held already) tuples."""
        groups: dict[tuple[str, str, tuple], list[_Use]] = defaultdict(list)
        for use in self._uses:
            groups[(use.run, use.kind, use.identity)].append(use)
        hold_users = {run: compute_hold_users(graph) for run, (_, graph) in self._protocol_runs.items()}
        held: dict[tuple[str, str, tuple], set[str]] = defaultdict(set)
        for allocation in self._held_allocations:
            held[(allocation.protocol_run_name, allocation.kind, ("item", allocation.item))] |= allocation.hold_users

        components = []
        for (run, kind, identity), uses in groups.items():
            users_by_holder = hold_users[run][0 if kind == DEVICE else 1]
            for component, already_held in self._group_components(
                run, uses, users_by_holder, held[(run, kind, identity)]
            ):
                components.append((run, kind, identity, component, already_held))
        return components

    def _group_components(
        self, run: str, uses: list[_Use], users_by_holder: dict, already_held_for: set[str]
    ) -> list[tuple[list[_Use], bool]]:
        """
        Split the uses of one item into hold components.

        A component has holders, their hold users, and tasks that name the item and must run before a hold user,
        which the schedulers let take over the held item. "" stands for a completed holder whose item is held now.
        """
        tasks = {use.task for use in uses}
        parent: dict[str, str] = {}

        def find(node: str) -> str:
            while parent.setdefault(node, node) != node:
                node = parent[node]
            return node

        users = set()
        for use in uses:
            for user in users_by_holder.get((use.task, use.slot), frozenset()) & tasks:
                parent[find(use.task)] = find(user)
                users.add(user)
        for user in already_held_for & tasks:
            parent[find("")] = find(user)
            users.add(user)

        ancestors = self._ancestors(run)
        for use in uses:
            user = next((u for u in users if use.task in ancestors[u]), None) if use.named else None
            if user is not None and use.task not in parent:
                parent[find(use.task)] = find(user)

        members: dict[str, list[_Use]] = defaultdict(list)
        for use in uses:
            if use.task in parent:
                members[find(use.task)].append(use)
        return [(component, "" in parent and find("") == root) for root, component in members.items()]

    def _ancestors(self, run: str) -> dict[str, set[str]]:
        if run not in self._ancestor_sets:
            task_graph = self._protocol_runs[run][1].get_task_graph()
            self._ancestor_sets[run] = {name: nx.ancestors(task_graph, name) for name in task_graph.nodes}
        return self._ancestor_sets[run]

    def _apply_item_constraints(self) -> None:
        """No two runs use an item at once: plain uses and hold spans share each item's NoOverlap."""
        shared: dict[tuple[str, object], dict[object, cp_model.IntervalVar]] = defaultdict(dict)
        in_components = set()

        for run, kind, identity, uses, already_held in self._hold_components():
            in_components.update(uses)
            starts = [self._task_vars[(run, use.task)].start for use in uses]
            ends = [self._task_vars[(run, use.task)].end for use in uses]
            if already_held:
                starts.append(self.model.NewConstant(self._current_time))
            span_start = self.model.NewIntVar(0, self._horizon, f"span_start_{run}_{kind}_{identity}")
            span_end = self.model.NewIntVar(0, self._horizon, f"span_end_{run}_{kind}_{identity}")
            span_size = self.model.NewIntVar(0, self._horizon, f"span_size_{run}_{kind}_{identity}")
            self.model.AddMinEquality(span_start, starts)
            self.model.AddMaxEquality(span_end, ends)

            # Inside the span, the run's own uses take turns
            local: dict[object, dict[str, cp_model.IntervalVar]] = defaultdict(dict)
            for use in uses:
                for item, interval in self._use_intervals(use):
                    local[item].setdefault(use.task, interval)
            for intervals in local.values():
                self.model.AddNoOverlap(intervals.values())

            if identity[0] == "item":
                span = self.model.NewIntervalVar(span_start, span_size, span_end, f"span_{run}_{kind}_{identity}")
                shared[(kind, identity[1])][("span", run, kind, identity)] = span
                continue
            root_task, root_slot = identity[1]
            for item, chosen in self._choices[(run, root_task, kind, root_slot)]:
                span = self.model.NewOptionalIntervalVar(
                    span_start, span_size, span_end, chosen, f"span_{run}_{kind}_{identity}_{item}"
                )
                shared[(kind, item)][("span", run, kind, identity)] = span

        for use in self._uses:
            if use not in in_components:
                for item, interval in self._use_intervals(use):
                    shared[(use.kind, item)].setdefault((use.run, use.task), interval)
        for intervals in shared.values():
            self.model.AddNoOverlap(intervals.values())

    def _apply_group_constraints(self) -> None:
        """Tasks in the same group are consecutive: next.start == current.end."""
        for run, order in self._topo.items():
            groups: dict[str, list[str]] = defaultdict(list)
            for name in order:
                if (run, name) in self._task_vars and self._tasks[run][name].group:
                    groups[self._tasks[run][name].group].append(name)
            for names in groups.values():
                for current, following in pairwise(names):
                    self.model.Add(self._task_vars[(run, following)].start == self._task_vars[(run, current)].end)

    def _apply_solution_hints(self) -> None:
        """Warm-start the solver from the planned schedule, or else from the previous solution's start times."""
        for (run, name), tv in self._task_vars.items():
            planned = self._hint.get((run, name))
            if planned is None:
                if (previous_start := self._schedule.get(run, {}).get(name)) is not None:
                    self.model.AddHint(tv.start, previous_start)
                continue
            start = self._current_time + planned.start
            self.model.AddHint(tv.start, start)
            self.model.AddHint(tv.end, start + self._tasks[run][name].duration)
            planned_items = {
                **{(DEVICE, slot): (d.lab_name, d.name) for slot, d in planned.devices.items()},
                **{(RESOURCE, slot): r for slot, r in planned.resources.items()},
            }
            for (choice_run, choice_task, kind, slot), choices in self._choices.items():
                if (choice_run, choice_task) == (run, name) and (item := planned_items.get((kind, slot))) is not None:
                    for option, chosen in choices:
                        self.model.AddHint(chosen, int(option == item))

    # Solving

    def solve(self, hint: dict[tuple[str, str], PlannedTask] | None = None) -> SchedulingSolution:
        """
        Solve the scheduling problem with a single hierarchical objective.

        Primary: minimize makespan. Secondary: minimize priority-weighted task start times.
        The makespan weight is set large enough to guarantee strict lexicographic dominance
        over the start-time term. A planned schedule (hint) warm-starts the search, and is used instead
        when CP-SAT finds nothing better within its time limit.
        """
        self._hint = hint or {}
        self._build_model()

        relative_horizon = self._horizon - self._current_time
        total_task_weight = sum(self._protocol_run_priorities.get(run, 0) + 1 for run, _ in self._task_vars)
        weighted_start_sum = sum(
            (self._protocol_run_priorities.get(run, 0) + 1) * (tv.start - self._current_time)
            for (run, _), tv in self._task_vars.items()
        )
        makespan_weight = total_task_weight * relative_horizon + 1
        self.model.Minimize((self._makespan - self._current_time) * makespan_weight + weighted_start_sum)

        if self._stopped.is_set():
            raise EosSchedulerError("The CP-SAT solve was stopped.")
        with Timer() as timer:
            status = self.solver.Solve(self.model)
        compute_duration = timer.get_duration("ms")

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if self._stopped.is_set():
                raise EosSchedulerError("The CP-SAT solve was stopped.")
            if (planned := self._solution_from_hint()) is not None:
                log.warning("CP-SAT found no schedule in time, using the planned schedule instead.")
                return planned
            raise EosSchedulerError("Could not compute a valid schedule with CP-SAT.")

        makespan = self.solver.Value(self._makespan)
        if (planned := self._solution_from_hint()) is not None and planned.makespan < makespan:
            log.info("The planned schedule is shorter than CP-SAT's within its time limit, using it.")
            return planned

        device_assignments, resource_assignments = self._extract_assignments()
        status_str = "optimal" if status == cp_model.OPTIMAL else "feasible"
        log.info(
            f"Computed {status_str} schedule "
            f"(makespan={makespan - self._current_time}, compute_duration={compute_duration:.2f} ms)."
        )
        return SchedulingSolution(
            schedule=self._extract_schedule(),
            device_assignments=device_assignments,
            resource_assignments=resource_assignments,
            makespan=makespan,
            compute_duration_ms=compute_duration,
            status=status_str,
        )

    def _extract_schedule(self) -> dict[str, dict[str, int]]:
        schedule: dict[str, dict[str, int]] = {run: {} for run in self._protocol_runs}
        for (run, name), tv in self._task_vars.items():
            schedule[run][name] = self.solver.Value(tv.start)
        return schedule

    def _extract_assignments(
        self,
    ) -> tuple[dict[str, dict[str, dict[str, DeviceAssignmentDef]]], dict[str, dict[str, dict[str, str]]]]:
        """The devices and resources of every task: earlier assignments, updated with the planned tasks' uses."""
        devices = {
            run: {t: dict(d) for t, d in tasks.items()} for run, tasks in self._previous_device_assignments.items()
        }
        resources = {
            run: {t: dict(r) for t, r in tasks.items()} for run, tasks in self._previous_resource_assignments.items()
        }
        running = {(run, name) for run, names in self._running_by_exp.items() for name in names}
        for use in self._uses:
            if (use.run, use.task) in running:
                continue  # A running task keeps what it has
            item = use.item
            if item is None:
                choices = self._choices[(use.run, use.root[0], use.kind, use.root[1])]
                item = next(option for option, chosen in choices if self.solver.Value(chosen))
            if use.kind == DEVICE:
                devices.setdefault(use.run, {}).setdefault(use.task, {})[use.slot] = DeviceAssignmentDef(
                    lab_name=item[0], name=item[1]
                )
            else:
                resources.setdefault(use.run, {}).setdefault(use.task, {})[use.slot] = item
        return devices, resources

    def _solution_from_hint(self) -> SchedulingSolution | None:
        """The planned schedule as a solution, when it covers every task still to run."""
        grouped = any(self._tasks[run][name].group for run, name in self._task_vars)
        if not self._hint or grouped:
            return None  # The planner does not keep task groups together
        schedule: dict[str, dict[str, int]] = {run: {} for run in self._protocol_runs}
        devices = {
            run: {t: dict(d) for t, d in tasks.items()} for run, tasks in self._previous_device_assignments.items()
        }
        resources = {
            run: {t: dict(r) for t, r in tasks.items()} for run, tasks in self._previous_resource_assignments.items()
        }
        for run, name in self._task_vars:
            planned = self._hint.get((run, name))
            if planned is not None:
                schedule[run][name] = self._current_time + planned.start
                devices.setdefault(run, {})[name] = dict(planned.devices)
                resources.setdefault(run, {})[name] = dict(planned.resources)
            elif name in self._running_by_exp.get(run, set()):
                schedule[run][name] = self._schedule.get(run, {}).get(name, self._current_time)
            else:
                return None

        makespan = max(
            (
                start + self._tasks[run][name].duration
                for run, tasks in schedule.items()
                for name, start in tasks.items()
            ),
            default=self._current_time,
        )
        return SchedulingSolution(
            schedule=schedule,
            device_assignments=devices,
            resource_assignments=resources,
            makespan=makespan,
            compute_duration_ms=0.0,
            status="planned",
        )
