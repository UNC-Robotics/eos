from dataclasses import dataclass

from ortools.sat.python import cp_model
from ortools.sat.sat_parameters_pb2 import SatParameters

from eos.configuration.entities.task_def import (
    DynamicDeviceAssignmentDef,
    DynamicResourceAssignmentDef,
    TaskDef,
    DeviceAssignmentDef,
)
from eos.configuration.protocol_graph import ProtocolGraph
from eos.configuration.utils import is_device_reference, is_resource_reference
from eos.logging.logger import log
from eos.scheduling.exceptions import EosSchedulerError
from eos.scheduling.utils import filter_device_pool
from eos.utils.timer import Timer


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


class CpSatSchedulingSolver:
    """CP-SAT solver for scheduling."""

    @staticmethod
    def _create_default_parameters() -> SatParameters:
        """Create default CP-SAT solver parameters optimized for scheduling."""
        params = SatParameters()
        params.max_time_in_seconds = 15.0
        params.num_search_workers = 4
        params.push_all_tasks_toward_start = True
        params.optimize_with_lb_tree_search = True
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
        completed_by_exp: dict[str, set[str]],
        running_by_exp: dict[str, set[str]],
        current_time: int,
        protocol_run_priorities: dict[str, int],
        eligible_devices_by_type: dict[str, list[tuple[str, str]]],
        eligible_resources_by_type: dict[str, list[tuple[str, str]]],
        previous_device_assignments: dict[str, dict[str, dict[str, DeviceAssignmentDef]]] | None = None,
        previous_resource_assignments: dict[str, dict[str, dict[str, str]]] | None = None,
        parameter_overrides: dict[str, float | int | bool] | None = None,
    ):
        self._protocol_runs = protocol_runs
        self._task_durations = task_durations
        self._schedule = schedule
        self._completed_by_exp = completed_by_exp
        self._running_by_exp = running_by_exp
        self._current_time = current_time
        self._protocol_run_priorities = protocol_run_priorities
        self._eligible_devices_by_type = eligible_devices_by_type
        self._eligible_resources_by_type = eligible_resources_by_type
        self._previous_device_assignments = previous_device_assignments or {}
        self._previous_resource_assignments = previous_resource_assignments or {}

        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

        # Configure solver parameters with defaults and optional overrides
        self.solver.parameters.CopyFrom(self._create_default_parameters())
        if parameter_overrides:
            for param_name, param_value in parameter_overrides.items():
                if hasattr(self.solver.parameters, param_name):
                    setattr(self.solver.parameters, param_name, param_value)
                else:
                    log.warning(f"Unsupported CP-SAT parameter: {param_name}")

        self._task_vars: dict[tuple[str, str], TaskVariables] = {}
        self._dynamic_choice_vars: dict[tuple[str, str], list[list[tuple[tuple[str, str], cp_model.IntVar]]]] = {}
        self._dynamic_resource_choice_vars: dict[
            tuple[str, str], list[tuple[str, list[tuple[tuple[str, str], cp_model.IntVar]]]]
        ] = {}
        self._device_references: dict[
            tuple[str, str], list[tuple[str, str, str]]
        ] = {}  # (exp, task) -> [(device_name, ref_task, ref_device)]
        self._resource_references: dict[
            tuple[str, str], list[tuple[str, str, str]]
        ] = {}  # (exp, task) -> [(resource_name, ref_task, ref_resource)]
        self._resource_intervals: dict[str, list[cp_model.IntervalVar]] = {}
        self._horizon: int = 0
        self._makespan: cp_model.IntVar | None = None

    def _calculate_horizon(self) -> int:
        """
        Calculate horizon and refresh task durations.

        The horizon must be large enough to accommodate resource contention
        and hold bridges which extend the schedule beyond the sum of task durations.
        """
        total_duration = 0
        self._task_durations.clear()

        for run_name, (_, protocol_graph) in self._protocol_runs.items():
            tasks = protocol_graph.get_topologically_sorted_tasks()
            durations = {task_name: protocol_graph.get_task(task_name).duration for task_name in tasks}
            total_duration += sum(durations.values())
            self._task_durations[run_name] = durations

        return self._current_time + total_duration * 2

    def _eligible_dynamic_devices_for(self, device_req: DynamicDeviceAssignmentDef) -> list[tuple[str, str]]:
        """Get eligible concrete devices for a dynamic request after filtering."""
        return filter_device_pool(device_req, self._eligible_devices_by_type.get(device_req.device_type, ()))

    def _eligible_dynamic_resources_for(self, cont_req: DynamicResourceAssignmentDef) -> list[tuple[str, str]]:
        """Get eligible concrete resources for a dynamic request after filtering."""
        return list(self._eligible_resources_by_type.get(cont_req.resource_type, []))

    def _create_dynamic_device_slot(
        self,
        run_name: str,
        task_name: str,
        dev_req: DynamicDeviceAssignmentDef,
        eligible: list[tuple[str, str]],
        slot_index: int,
        start_var: cp_model.IntVar,
        end_var: cp_model.IntVar,
        duration: int,
    ) -> tuple[list[tuple[tuple[str, str], cp_model.IntVar]], list[cp_model.IntVar]]:
        """Create optional intervals for a single dynamic device slot using task start/end variables."""
        slot_choices: list[tuple[tuple[str, str], cp_model.IntVar]] = []
        present_bools: list[cp_model.IntVar] = []

        for lab_name, device_name in eligible:
            present = self._new_opt_interval_and_bool(
                start_var,
                end_var,
                duration,
                present_name=(
                    f"assign_{run_name}_{task_name}_{dev_req.device_type}_slot{slot_index}_{lab_name}_{device_name}"
                ),
                interval_name=(
                    f"opt_{run_name}_{task_name}_iv_{dev_req.device_type}_slot{slot_index}_{lab_name}_{device_name}"
                ),
                resource_bucket=f"device_{lab_name}_{device_name}",
            )

            slot_choices.append(((lab_name, device_name), present))
            present_bools.append(present)

        return slot_choices, present_bools

    def _add_dynamic_device_constraints(
        self,
        run_name: str,
        task_name: str,
        task: TaskDef,
        start_var: cp_model.IntVar,
        end_var: cp_model.IntVar,
        duration: int,
    ) -> None:
        """Add dynamic device allocation constraints for a task (single selection)."""
        slots: list[list[tuple[tuple[str, str], cp_model.IntVar]]] = []

        for dev_req in task.devices.values():
            if not isinstance(dev_req, DynamicDeviceAssignmentDef):
                continue

            eligible = self._eligible_dynamic_devices_for(dev_req)
            if not eligible:
                # Force infeasibility if no eligible devices exist
                dummy = self.model.NewIntVar(0, 0, f"{run_name}_{task_name}_no_dynamic_options")
                self.model.Add(dummy == 1)
                continue

            # Single selection
            slot_choices, present_bools = self._create_dynamic_device_slot(
                run_name, task_name, dev_req, eligible, 0, start_var, end_var, duration
            )
            self.model.AddExactlyOne(present_bools)
            slots.append(slot_choices)

        if slots:
            self._dynamic_choice_vars[(run_name, task_name)] = slots

    def _new_opt_interval_and_bool(
        self,
        start_var: cp_model.IntVar,
        end_var: cp_model.IntVar,
        duration: int,
        present_name: str,
        interval_name: str,
        resource_bucket: str,
    ) -> cp_model.IntVar:
        """Create a BoolVar and OptionalIntervalVar, registering interval under resource_bucket for NoOverlap."""
        is_present = self.model.NewBoolVar(present_name)
        optional_interval = self.model.NewOptionalIntervalVar(start_var, duration, end_var, is_present, interval_name)
        self._resource_intervals.setdefault(resource_bucket, []).append(optional_interval)
        return is_present

    def _add_dynamic_resource_constraints(
        self,
        run_name: str,
        task_name: str,
        task: TaskDef,
        start_var: cp_model.IntVar,
        end_var: cp_model.IntVar,
        duration: int,
    ) -> None:
        """Add dynamic resource allocation constraints for resource requests in the task config (single selection)."""
        entries: list[tuple[str, list[tuple[tuple[str, str], cp_model.IntVar]]]] = []

        for name, value in task.resources.items():
            if isinstance(value, str):
                continue

            # value is DynamicTaskResourceConfig
            eligible = self._eligible_dynamic_resources_for(value)
            if not eligible:
                # Force infeasibility if no eligible resources exist
                dummy = self.model.NewIntVar(0, 0, f"{run_name}_{task_name}_no_dynamic_resource_options")
                self.model.Add(dummy == 1)
                continue

            # Single selection
            choices: list[tuple[tuple[str, str], cp_model.IntVar]] = []
            present_bools: list[cp_model.IntVar] = []

            for lab_name, resource_name in eligible:
                present = self._new_opt_interval_and_bool(
                    start_var,
                    end_var,
                    duration,
                    present_name=(f"assign_{run_name}_{task_name}_resource_{name}_slot0_{lab_name}_{resource_name}"),
                    interval_name=(f"opt_{run_name}_{task_name}_civ_{name}_slot0_{resource_name}"),
                    resource_bucket=f"resource_{resource_name}",
                )
                choices.append(((lab_name, resource_name), present))
                present_bools.append(present)

            if present_bools:
                self.model.AddExactlyOne(present_bools)

            entries.append((name, choices))

        if entries:
            self._dynamic_resource_choice_vars[(run_name, task_name)] = entries

    def _create_task_time_variables(
        self, run_name: str, task_name: str, duration: int, is_running: bool
    ) -> TaskVariables:
        """Create time variables (start, end, interval) for a task."""
        start_lb = 0 if is_running else self._current_time
        end_lb = 0 if is_running else self._current_time

        start_var = self.model.NewIntVar(start_lb, self._horizon, f"{run_name}_{task_name}_start")
        end_var = self.model.NewIntVar(end_lb, self._horizon, f"{run_name}_{task_name}_end")
        interval_var = self.model.NewIntervalVar(start_var, duration, end_var, f"{run_name}_{task_name}_interval")

        return TaskVariables(start=start_var, end=end_var, interval=interval_var)

    def _process_task_devices(self, run_name: str, task_name: str, task: TaskDef, task_vars: TaskVariables) -> None:
        """Process specific and dynamic device requirements for a task."""
        # Specific devices: create fixed resource intervals
        for dev in task.devices.values():
            if isinstance(dev, DeviceAssignmentDef):
                resource_name = f"device_{dev.lab_name}_{dev.name}"
                self._resource_intervals.setdefault(resource_name, []).append(task_vars.interval)

        # Dynamic devices: create optional intervals for each eligible device
        self._add_dynamic_device_constraints(run_name, task_name, task, task_vars.start, task_vars.end, task.duration)

    def _process_task_resources(self, run_name: str, task_name: str, task: TaskDef, task_vars: TaskVariables) -> None:
        """Process specific and dynamic resource requirements for a task."""
        # Specific resources (non-references): create fixed resource intervals
        for resource_value in task.resources.values():
            if isinstance(resource_value, str) and not is_resource_reference(resource_value):
                resource_name = f"resource_{resource_value}"
                self._resource_intervals.setdefault(resource_name, []).append(task_vars.interval)

        # Dynamic resources: optional intervals for eligible resources
        self._add_dynamic_resource_constraints(run_name, task_name, task, task_vars.start, task_vars.end, task.duration)

    def _track_task_references(self, run_name: str, task_name: str, task: TaskDef) -> None:
        """Track device and resource references for later constraint creation."""
        # Track device references
        for device_name, device_value in task.devices.items():
            if isinstance(device_value, str) and is_device_reference(device_value):
                ref_task_name, ref_device_name = device_value.split(".")
                self._device_references.setdefault((run_name, task_name), []).append(
                    (device_name, ref_task_name, ref_device_name)
                )

        # Track resource references
        for resource_name, resource_value in task.resources.items():
            if isinstance(resource_value, str) and is_resource_reference(resource_value):
                ref_task_name, ref_resource_name = resource_value.split(".")
                self._resource_references.setdefault((run_name, task_name), []).append(
                    (resource_name, ref_task_name, ref_resource_name)
                )

    def _apply_task_timing_constraints(
        self, run_name: str, task_name: str, task_vars: TaskVariables, duration: int, is_running: bool
    ) -> None:
        """Apply timing constraints: fix running tasks or constrain duration."""
        if is_running:
            fixed_start = self._schedule.get(run_name, {})[task_name]
            self.model.Add(task_vars.start == fixed_start)
            self.model.Add(task_vars.end == fixed_start + duration)
        else:
            self.model.Add(task_vars.end == task_vars.start + duration)

    def _create_task_variables(self) -> None:
        """Create task variables, resource intervals, and dynamic choice variables."""
        for run_name, (_, protocol_graph) in self._protocol_runs.items():
            tasks = protocol_graph.get_topologically_sorted_tasks()
            for task_name in tasks:
                if task_name in self._completed_by_exp.get(run_name, set()):
                    continue

                task: TaskDef = protocol_graph.get_task(task_name)
                is_running = task_name in self._running_by_exp.get(run_name, set())

                # Create time variables
                task_vars = self._create_task_time_variables(run_name, task_name, task.duration, is_running)
                self._task_vars[(run_name, task_name)] = task_vars

                # Process devices and resources
                self._process_task_devices(run_name, task_name, task, task_vars)
                self._process_task_resources(run_name, task_name, task, task_vars)

                # Track references
                self._track_task_references(run_name, task_name, task)

                # Apply timing constraints
                self._apply_task_timing_constraints(run_name, task_name, task_vars, task.duration, is_running)

    def _apply_precedence_constraints(self) -> None:
        """Apply precedence constraints: start(task) >= end(dep) for each dependency."""
        for run_name, (_, protocol_graph) in self._protocol_runs.items():
            tasks = protocol_graph.get_topologically_sorted_tasks()
            for task_name in tasks:
                if (run_name, task_name) not in self._task_vars:
                    continue

                for dep_task_name in protocol_graph.get_task_dependencies(task_name):
                    if (run_name, dep_task_name) in self._task_vars:
                        self.model.Add(
                            self._task_vars[(run_name, task_name)].start
                            >= self._task_vars[(run_name, dep_task_name)].end
                        )

    def _apply_resource_constraints(self) -> None:
        """Apply NoOverlap constraints per resource (devices and resources)."""
        for intervals in self._resource_intervals.values():
            if intervals:
                self.model.AddNoOverlap(intervals)

    def _apply_group_constraints(self) -> None:
        """Tasks in the same group are consecutive: next.start == current.end."""
        for run_name, (_, protocol_graph) in self._protocol_runs.items():
            all_tasks_sorted = protocol_graph.get_topologically_sorted_tasks()

            # Collect tasks by group, maintaining topological order
            groups: dict[str, list[str]] = {}
            for task_name in all_tasks_sorted:
                if (run_name, task_name) not in self._task_vars:
                    continue

                task = protocol_graph.get_task(task_name)
                if task.group:
                    groups.setdefault(task.group, []).append(task_name)

            # Apply constraints for each group
            for _group_name, task_names in groups.items():
                if len(task_names) <= 1:
                    continue

                for i in range(len(task_names) - 1):
                    current_task = task_names[i]
                    next_task = task_names[i + 1]
                    self.model.Add(
                        self._task_vars[(run_name, next_task)].start == self._task_vars[(run_name, current_task)].end
                    )

    @staticmethod
    def _resolve_device_root(
        protocol_graph: ProtocolGraph, ref_task_name: str, ref_device_name: str
    ) -> tuple[str, str, object] | None:
        """
        Follow a chain of device string references to the root definition.

        Returns (root_task_name, root_device_name, root_device_value) or None on a cycle.
        """
        visited: set[tuple[str, str]] = set()
        while True:
            key = (ref_task_name, ref_device_name)
            if key in visited:
                return None
            visited.add(key)

            ref_task = protocol_graph.get_task(ref_task_name)
            ref_device_value = ref_task.devices.get(ref_device_name)

            if isinstance(ref_device_value, str) and is_device_reference(ref_device_value):
                ref_task_name, ref_device_name = ref_device_value.split(".")
            else:
                return ref_task_name, ref_device_name, ref_device_value

    @staticmethod
    def _resolve_resource_root(
        protocol_graph: ProtocolGraph, ref_task_name: str, ref_resource_name: str
    ) -> tuple[str, str, object] | None:
        """
        Follow a chain of resource string references to the root definition.

        Returns (root_task_name, root_resource_name, root_resource_value) or None on a cycle.
        """
        visited: set[tuple[str, str]] = set()
        while True:
            key = (ref_task_name, ref_resource_name)
            if key in visited:
                return None
            visited.add(key)

            ref_task = protocol_graph.get_task(ref_task_name)
            ref_resource_value = ref_task.resources.get(ref_resource_name)

            if isinstance(ref_resource_value, str) and is_resource_reference(ref_resource_value):
                ref_task_name, ref_resource_name = ref_resource_value.split(".")
            else:
                return ref_task_name, ref_resource_name, ref_resource_value

    def _apply_device_reference_constraints(self) -> None:
        """Enforce that device references use the same device as the referenced task."""
        for (run_name, task_name), refs in self._device_references.items():
            _, protocol_graph = self._protocol_runs[run_name]
            task = protocol_graph.get_task(task_name)
            task_vars = self._task_vars[(run_name, task_name)]
            duration = task.duration

            for device_name, ref_task_name, ref_device_name in refs:
                # Resolve chained references to the root device definition
                root = self._resolve_device_root(protocol_graph, ref_task_name, ref_device_name)
                if root is None:
                    continue
                root_task_name, root_device_name, ref_device_value = root
                ref_task = protocol_graph.get_task(root_task_name)

                if isinstance(ref_device_value, DynamicDeviceAssignmentDef):
                    # Find the slot index in the referenced task
                    ref_slot_idx = 0
                    for ref_dev_name, ref_dev_val in ref_task.devices.items():
                        if ref_dev_name == root_device_name:
                            break
                        if isinstance(ref_dev_val, DynamicDeviceAssignmentDef):
                            ref_slot_idx += 1

                    # Get the choice variables from the referenced task
                    ref_slots = self._dynamic_choice_vars.get((run_name, root_task_name), [])
                    if ref_slot_idx >= len(ref_slots):
                        continue

                    ref_choices = ref_slots[ref_slot_idx]

                    # Create optional intervals for the current task, one for each possible device choice
                    # Each interval is only active when the referenced task selects that specific device
                    for (lab_name, dev_name), ref_bool_var in ref_choices:
                        # Create an optional interval that's only active when ref task selects this device
                        optional_interval = self.model.NewOptionalIntervalVar(
                            task_vars.start,
                            duration,
                            task_vars.end,
                            ref_bool_var,  # Only active when referenced task selects this device
                            f"opt_ref_{run_name}_{task_name}_{device_name}_{lab_name}_{dev_name}",
                        )
                        resource_name = f"device_{lab_name}_{dev_name}"
                        self._resource_intervals.setdefault(resource_name, []).append(optional_interval)

                elif isinstance(ref_device_value, DeviceAssignmentDef):
                    # Referenced device is specific, add this task's interval to that device's resource bucket
                    resource_name = f"device_{ref_device_value.lab_name}_{ref_device_value.name}"
                    self._resource_intervals.setdefault(resource_name, []).append(task_vars.interval)

    def _apply_resource_reference_constraints(self) -> None:
        """Enforce that resource references use the same resource as the referenced task."""
        for (run_name, task_name), refs in self._resource_references.items():
            _, protocol_graph = self._protocol_runs[run_name]
            task = protocol_graph.get_task(task_name)
            task_vars = self._task_vars[(run_name, task_name)]
            duration = task.duration

            for resource_name, ref_task_name, ref_resource_name in refs:
                # Resolve chained references to the root resource definition
                root = self._resolve_resource_root(protocol_graph, ref_task_name, ref_resource_name)
                if root is None:
                    continue
                root_task_name, root_resource_name, ref_resource_value = root

                if isinstance(ref_resource_value, DynamicResourceAssignmentDef):
                    # Find the entry index in the referenced task's dynamic resource choices
                    ref_entries = self._dynamic_resource_choice_vars.get((run_name, root_task_name), [])
                    for entry_name, choices in ref_entries:
                        if entry_name == root_resource_name:
                            # Create optional intervals for each possible resource choice
                            # Each interval is only active when the referenced task selects that specific resource
                            for (_lab_name, concrete_resource_name), ref_bool_var in choices:
                                # Create an optional interval that's only active when ref task selects this resource
                                optional_interval = self.model.NewOptionalIntervalVar(
                                    task_vars.start,
                                    duration,
                                    task_vars.end,
                                    ref_bool_var,  # Only active when referenced task selects this resource
                                    f"opt_res_ref_{run_name}_{task_name}_{resource_name}_{concrete_resource_name}",
                                )
                                bucket_name = f"resource_{concrete_resource_name}"
                                self._resource_intervals.setdefault(bucket_name, []).append(optional_interval)
                            break
                elif isinstance(ref_resource_value, str) and not is_resource_reference(ref_resource_value):
                    # Referenced resource is specific (non-reference string), add this task's interval to that
                    # resource bucket
                    bucket_name = f"resource_{ref_resource_value}"
                    self._resource_intervals.setdefault(bucket_name, []).append(task_vars.interval)

    def _apply_hold_bridge_constraints(self) -> None:
        """
        Add bridge intervals for tasks with hold=true.

        When a task declares hold=true on a device/resource, a bridge interval is added
        between the task's end and its successor's start on that device/resource.
        This prevents the solver from scheduling other protocols' tasks in the gap.

        For static devices, a regular bridge interval is created.
        For dynamic devices, optional bridge intervals are created per choice variable.
        """
        for run_name, (_, protocol_graph) in self._protocol_runs.items():
            for task_name in protocol_graph.get_topologically_sorted_tasks():
                if (run_name, task_name) not in self._task_vars:
                    continue
                task = protocol_graph.get_task(task_name)
                task_vars = self._task_vars[(run_name, task_name)]
                self._apply_device_hold_bridges(run_name, task_name, task, task_vars, protocol_graph)
                self._apply_resource_hold_bridges(run_name, task_name, task, task_vars, protocol_graph)

    def _apply_device_hold_bridges(
        self, run_name: str, task_name: str, task: TaskDef, task_vars: TaskVariables, protocol_graph: ProtocolGraph
    ) -> None:
        """Add bridge intervals for held device slots."""
        for slot, dev in task.devices.items():
            if not task.device_holds.get(slot, False):
                continue

            if isinstance(dev, DeviceAssignmentDef):
                bucket = f"device_{dev.lab_name}_{dev.name}"
                self._add_bridge_for_successors(
                    run_name, task_name, task_vars, protocol_graph, slot, bucket, is_device=True
                )
            elif isinstance(dev, DynamicDeviceAssignmentDef):
                self._add_dynamic_bridge_for_successors(
                    run_name, task_name, task_vars, protocol_graph, slot, task_name, slot, is_device=True
                )
            elif isinstance(dev, str) and is_device_reference(dev):
                self._add_device_ref_hold_bridge(run_name, task_name, task_vars, protocol_graph, slot, dev)

    def _add_device_ref_hold_bridge(
        self,
        run_name: str,
        task_name: str,
        task_vars: TaskVariables,
        protocol_graph: ProtocolGraph,
        slot: str,
        ref: str,
    ) -> None:
        """Add bridge for a device reference hold (resolves to static or dynamic root)."""
        root = self._resolve_device_root(protocol_graph, *ref.split("."))
        if not root:
            return
        root_task_name, root_device_name, root_dev = root
        if isinstance(root_dev, DeviceAssignmentDef):
            bucket = f"device_{root_dev.lab_name}_{root_dev.name}"
            self._add_bridge_for_successors(
                run_name, task_name, task_vars, protocol_graph, slot, bucket, is_device=True
            )
        elif isinstance(root_dev, DynamicDeviceAssignmentDef):
            self._add_dynamic_bridge_for_successors(
                run_name, task_name, task_vars, protocol_graph, slot, root_task_name, root_device_name, is_device=True
            )

    def _apply_resource_hold_bridges(
        self, run_name: str, task_name: str, task: TaskDef, task_vars: TaskVariables, protocol_graph: ProtocolGraph
    ) -> None:
        """Add bridge intervals for held resource slots."""
        for slot, res in task.resources.items():
            if not task.resource_holds.get(slot, False):
                continue

            if isinstance(res, DynamicResourceAssignmentDef):
                self._add_dynamic_bridge_for_successors(
                    run_name, task_name, task_vars, protocol_graph, slot, task_name, slot, is_device=False
                )
            elif isinstance(res, str):
                if not is_resource_reference(res):
                    bucket = f"resource_{res}"
                    self._add_bridge_for_successors(
                        run_name, task_name, task_vars, protocol_graph, slot, bucket, is_device=False
                    )
                else:
                    self._add_resource_ref_hold_bridge(run_name, task_name, task_vars, protocol_graph, slot, res)

    def _add_resource_ref_hold_bridge(
        self,
        run_name: str,
        task_name: str,
        task_vars: TaskVariables,
        protocol_graph: ProtocolGraph,
        slot: str,
        ref: str,
    ) -> None:
        """Add bridge for a resource reference hold (resolves to static or dynamic root)."""
        root = self._resolve_resource_root(protocol_graph, *ref.split("."))
        if not root:
            return
        root_task_name, root_resource_name, root_res = root
        if isinstance(root_res, str) and not is_resource_reference(root_res):
            bucket = f"resource_{root_res}"
            self._add_bridge_for_successors(
                run_name, task_name, task_vars, protocol_graph, slot, bucket, is_device=False
            )
        elif isinstance(root_res, DynamicResourceAssignmentDef):
            self._add_dynamic_bridge_for_successors(
                run_name,
                task_name,
                task_vars,
                protocol_graph,
                slot,
                root_task_name,
                root_resource_name,
                is_device=False,
            )

    def _get_task_successors(self, run_name: str, task_name: str, protocol_graph: ProtocolGraph) -> list[str]:
        """Get direct task-node successors that have solver variables."""
        graph = protocol_graph.get_graph()
        return [
            s
            for s in graph.successors(task_name)
            if graph.nodes[s].get("node_type") == "task" and (run_name, s) in self._task_vars
        ]

    def _add_bridge_for_successors(
        self,
        run_name: str,
        task_name: str,
        task_vars: TaskVariables,
        protocol_graph: ProtocolGraph,
        slot: str,
        bucket: str,
        is_device: bool,
    ) -> None:
        """Add a bridge interval between task_name and each successor that uses the same device/resource."""
        for succ_name in self._get_task_successors(run_name, task_name, protocol_graph):
            succ_task = protocol_graph.get_task(succ_name)
            succ_vars = self._task_vars[(run_name, succ_name)]

            if is_device:
                uses_same = self._successor_uses_device_bucket(protocol_graph, succ_task, bucket)
            else:
                uses_same = self._successor_uses_resource_bucket(protocol_graph, succ_task, bucket)

            if not uses_same:
                continue

            bridge_size = self.model.NewIntVar(
                0, self._horizon, f"bridge_size_{run_name}_{task_name}_to_{succ_name}_{bucket}"
            )
            bridge_interval = self.model.NewIntervalVar(
                task_vars.end,
                bridge_size,
                succ_vars.start,
                f"bridge_iv_{run_name}_{task_name}_to_{succ_name}_{bucket}",
            )
            self._resource_intervals.setdefault(bucket, []).append(bridge_interval)

    def _successor_uses_device_bucket(self, protocol_graph: ProtocolGraph, succ_task: TaskDef, bucket: str) -> bool:
        """Check if a successor task uses the device identified by bucket."""
        for _slot, s_dev in succ_task.devices.items():
            if isinstance(s_dev, DeviceAssignmentDef):
                if f"device_{s_dev.lab_name}_{s_dev.name}" == bucket:
                    return True
            elif isinstance(s_dev, str) and is_device_reference(s_dev):
                root = self._resolve_device_root(protocol_graph, *s_dev.split("."))
                if root:
                    _, _, root_dev = root
                    if (
                        isinstance(root_dev, DeviceAssignmentDef)
                        and f"device_{root_dev.lab_name}_{root_dev.name}" == bucket
                    ):
                        return True
        return False

    def _successor_uses_resource_bucket(self, protocol_graph: ProtocolGraph, succ_task: TaskDef, bucket: str) -> bool:
        """Check if a successor task uses the resource identified by bucket."""
        for _slot, s_res in succ_task.resources.items():
            if isinstance(s_res, str):
                if is_resource_reference(s_res):
                    root = self._resolve_resource_root(protocol_graph, *s_res.split("."))
                    if root:
                        _, _, root_res = root
                        if (
                            isinstance(root_res, str)
                            and not is_resource_reference(root_res)
                            and f"resource_{root_res}" == bucket
                        ):
                            return True
                elif f"resource_{s_res}" == bucket:
                    return True
        return False

    def _find_dynamic_device_slot_index(self, protocol_graph: ProtocolGraph, task_name: str, slot_name: str) -> int:
        """Compute the slot index for a dynamic device by counting prior dynamic entries."""
        task = protocol_graph.get_task(task_name)
        idx = 0
        for dev_name, dev_val in task.devices.items():
            if dev_name == slot_name:
                return idx
            if isinstance(dev_val, DynamicDeviceAssignmentDef):
                idx += 1
        return idx

    def _add_dynamic_bridge_for_successors(
        self,
        run_name: str,
        task_name: str,
        task_vars: TaskVariables,
        protocol_graph: ProtocolGraph,
        slot: str,
        dynamic_root_task: str,
        dynamic_root_slot: str,
        is_device: bool,
    ) -> None:
        """
        Add optional bridge intervals for dynamic device/resource holds.

        For each candidate device/resource in the dynamic pool, creates an optional
        bridge interval conditioned on the choice boolean. The bridge is only active
        when that specific device/resource is chosen.
        """
        # Find the choice variables for the dynamic root
        if is_device:
            slot_idx = self._find_dynamic_device_slot_index(protocol_graph, dynamic_root_task, dynamic_root_slot)
            choices = self._dynamic_choice_vars.get((run_name, dynamic_root_task), [])
            if slot_idx >= len(choices):
                return
            slot_choices = choices[slot_idx]
        else:
            entries = self._dynamic_resource_choice_vars.get((run_name, dynamic_root_task), [])
            slot_choices = None
            for entry_name, entry_choices in entries:
                if entry_name == dynamic_root_slot:
                    slot_choices = entry_choices
                    break
            if not slot_choices:
                return

        for succ_name in self._get_task_successors(run_name, task_name, protocol_graph):
            succ_task = protocol_graph.get_task(succ_name)
            succ_vars = self._task_vars[(run_name, succ_name)]

            # Check if successor uses the same dynamic device/resource
            uses_same = self._successor_uses_dynamic_root(
                protocol_graph, succ_task, dynamic_root_task, dynamic_root_slot, slot_choices, is_device
            )
            if not uses_same:
                continue

            # Create optional bridge intervals for each choice
            for (lab_name, dev_name), bool_var in slot_choices:
                bucket = f"device_{lab_name}_{dev_name}" if is_device else f"resource_{dev_name}"

                bridge_size = self.model.NewIntVar(
                    0,
                    self._horizon,
                    f"bridge_size_{run_name}_{task_name}_to_{succ_name}_{bucket}",
                )
                bridge_interval = self.model.NewOptionalIntervalVar(
                    task_vars.end,
                    bridge_size,
                    succ_vars.start,
                    bool_var,
                    f"bridge_iv_{run_name}_{task_name}_to_{succ_name}_{bucket}",
                )
                self._resource_intervals.setdefault(bucket, []).append(bridge_interval)

    def _successor_uses_dynamic_root(
        self,
        protocol_graph: ProtocolGraph,
        succ_task: TaskDef,
        dynamic_root_task: str,
        dynamic_root_slot: str,
        slot_choices: list[tuple[tuple[str, str], cp_model.IntVar]],
        is_device: bool,
    ) -> bool:
        """Check if a successor task uses the same dynamic device/resource root."""
        if is_device:
            return self._successor_uses_dynamic_device_root(
                protocol_graph, succ_task, dynamic_root_task, dynamic_root_slot, slot_choices
            )
        return self._successor_uses_dynamic_resource_root(
            protocol_graph, succ_task, dynamic_root_task, dynamic_root_slot, slot_choices
        )

    def _successor_uses_dynamic_device_root(
        self,
        protocol_graph: ProtocolGraph,
        succ_task: TaskDef,
        dynamic_root_task: str,
        dynamic_root_slot: str,
        slot_choices: list[tuple[tuple[str, str], cp_model.IntVar]],
    ) -> bool:
        """Check if successor uses the same dynamic device root."""
        for _s_slot, s_dev in succ_task.devices.items():
            if isinstance(s_dev, str) and is_device_reference(s_dev):
                root = self._resolve_device_root(protocol_graph, *s_dev.split("."))
                if root:
                    r_task, r_slot, r_dev = root
                    if (
                        isinstance(r_dev, DynamicDeviceAssignmentDef)
                        and r_task == dynamic_root_task
                        and r_slot == dynamic_root_slot
                    ):
                        return True
            elif isinstance(s_dev, DeviceAssignmentDef):
                for (lab, dev), _ in slot_choices:
                    if s_dev.lab_name == lab and s_dev.name == dev:
                        return True
        return False

    def _successor_uses_dynamic_resource_root(
        self,
        protocol_graph: ProtocolGraph,
        succ_task: TaskDef,
        dynamic_root_task: str,
        dynamic_root_slot: str,
        slot_choices: list[tuple[tuple[str, str], cp_model.IntVar]],
    ) -> bool:
        """Check if successor uses the same dynamic resource root."""
        for _s_slot, s_res in succ_task.resources.items():
            if isinstance(s_res, str):
                if is_resource_reference(s_res):
                    root = self._resolve_resource_root(protocol_graph, *s_res.split("."))
                    if root:
                        r_task, r_slot, r_dev = root
                        if (
                            isinstance(r_dev, DynamicResourceAssignmentDef)
                            and r_task == dynamic_root_task
                            and r_slot == dynamic_root_slot
                        ):
                            return True
                else:
                    for (_, res_name), _ in slot_choices:
                        if s_res == res_name:
                            return True
        return False

    def _build_model(self) -> None:
        """Build the complete scheduling model."""
        self._horizon = self._calculate_horizon()
        self._create_task_variables()
        self._apply_precedence_constraints()
        self._apply_device_reference_constraints()
        self._apply_resource_reference_constraints()
        self._apply_hold_bridge_constraints()
        self._apply_resource_constraints()
        self._apply_group_constraints()
        self._apply_solution_hints()

        # Create makespan variable
        self._makespan = self.model.NewIntVar(0, self._horizon, "makespan")
        self.model.AddMaxEquality(self._makespan, [tv.end for tv in self._task_vars.values()])

    def _apply_solution_hints(self) -> None:
        """Warm-start the solver with start times from the previous solution."""
        for (run_name, task_name), tv in self._task_vars.items():
            prev_start = self._schedule.get(run_name, {}).get(task_name)
            if prev_start is not None:
                self.model.AddHint(tv.start, prev_start)

    def _extract_schedule(self) -> dict[str, dict[str, int]]:
        """Extract task schedule from solved model efficiently in a single pass."""
        schedule: dict[str, dict[str, int]] = {exp: {} for exp in self._protocol_runs}
        for (run_name, task_name), tv in self._task_vars.items():
            schedule[run_name][task_name] = self.solver.Value(tv.start)
        return schedule

    def _extract_device_assignments(self) -> dict[str, dict[str, dict[str, DeviceAssignmentDef]]]:
        """Extract dynamic + specific device assignments per task (concise logging)."""
        # Start with previous assignments (from completed/running tasks)
        device_assignments: dict[str, dict[str, dict[str, DeviceAssignmentDef]]] = {
            exp: {task: devs.copy() for task, devs in tasks.items()}
            for exp, tasks in self._previous_device_assignments.items()
        }

        for (run_name, task_name), _tv in self._task_vars.items():
            _, protocol_graph = self._protocol_runs[run_name]
            task: TaskDef = protocol_graph.get_task(task_name)
            task_devices: dict[str, DeviceAssignmentDef] = {}

            # Extract selections preserving device names from task
            slots = self._dynamic_choice_vars.get((run_name, task_name), [])
            slot_idx = 0

            # Dynamic and specific devices
            for device_name, dev in task.devices.items():
                if isinstance(dev, DynamicDeviceAssignmentDef):
                    if slot_idx < len(slots):
                        slot = slots[slot_idx]
                        for (lab_name, dev_name), b in slot:
                            if self.solver.Value(b) == 1:
                                task_devices[device_name] = DeviceAssignmentDef(lab_name=lab_name, name=dev_name)
                                break
                        slot_idx += 1
                elif isinstance(dev, DeviceAssignmentDef):
                    task_devices[device_name] = dev

            # Resolve device references against already-built assignments
            for device_name, dev in task.devices.items():
                if isinstance(dev, str) and is_device_reference(dev):
                    ref_task_name, ref_device_name = dev.split(".")
                    ref_map = device_assignments.get(run_name, {}).get(ref_task_name, {})
                    ref_device = ref_map.get(ref_device_name)
                    if ref_device:
                        task_devices[device_name] = ref_device

            if task_devices:
                device_assignments.setdefault(run_name, {})[task_name] = task_devices

        return device_assignments

    def _extract_resource_assignments(self) -> dict[str, dict[str, dict[str, str]]]:
        """Extract chosen resources per task and resource name (concise logging)."""
        # Start with previous assignments (from completed/running tasks)
        resource_assignments: dict[str, dict[str, dict[str, str]]] = {
            exp: {task: res.copy() for task, res in tasks.items()}
            for exp, tasks in self._previous_resource_assignments.items()
        }

        for (run_name, task_name), _tv in self._task_vars.items():
            _, protocol_graph = self._protocol_runs[run_name]
            task: TaskDef = protocol_graph.get_task(task_name)
            assigned: dict[str, str] = {}

            # Dynamic resource assignments
            entries = self._dynamic_resource_choice_vars.get((run_name, task_name), [])
            for name, choices in entries:
                for (_lab_name, resource_name), b in choices:
                    if self.solver.Value(b) == 1:
                        assigned[name] = resource_name
                        break

            # Explicit (non-reference) strings
            for name, value in task.resources.items():
                if isinstance(value, str) and not is_resource_reference(value):
                    assigned[name] = value

            # Resolve resource references
            for name, value in task.resources.items():
                if isinstance(value, str) and is_resource_reference(value):
                    ref_task_name, ref_resource_name = value.split(".")
                    ref_map = resource_assignments.get(run_name, {}).get(ref_task_name, {})
                    ref_value = ref_map.get(ref_resource_name)
                    if ref_value:
                        assigned[name] = ref_value

            if assigned:
                resource_assignments.setdefault(run_name, {})[task_name] = assigned

        return resource_assignments

    def solve(self) -> SchedulingSolution:
        """
        Solve the scheduling problem with a single hierarchical objective.

        Primary: minimize makespan. Secondary: minimize priority-weighted task start times.
        The makespan weight is set large enough to guarantee strict lexicographic dominance
        over the start-time term.
        """
        self._build_model()

        relative_horizon = self._horizon - self._current_time

        total_task_weight = sum(self._protocol_run_priorities.get(run_name, 0) + 1 for (run_name, _) in self._task_vars)
        weighted_start_sum = sum(
            (self._protocol_run_priorities.get(run_name, 0) + 1) * (task_vars.start - self._current_time)
            for (run_name, _), task_vars in self._task_vars.items()
        )

        makespan_weight = total_task_weight * relative_horizon + 1
        self.model.Minimize((self._makespan - self._current_time) * makespan_weight + weighted_start_sum)

        with Timer() as timer:
            status = self.solver.Solve(self.model)
        compute_duration = timer.get_duration("ms")

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise EosSchedulerError("Could not compute a valid schedule with CP-SAT.")

        optimal_makespan = self.solver.Value(self._makespan)
        schedule = self._extract_schedule()
        device_assignments = self._extract_device_assignments()
        resource_assignments = self._extract_resource_assignments()
        status_str = "optimal" if status == cp_model.OPTIMAL else "feasible"

        log.info(
            f"Computed {status_str} schedule "
            f"(makespan={optimal_makespan - self._current_time}, compute_duration={compute_duration:.2f} ms)."
        )

        return SchedulingSolution(
            schedule=schedule,
            device_assignments=device_assignments,
            resource_assignments=resource_assignments,
            makespan=optimal_makespan,
            compute_duration_ms=compute_duration,
            status=status_str,
        )
