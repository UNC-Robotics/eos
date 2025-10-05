from dataclasses import dataclass

from ortools.sat.python import cp_model
from ortools.sat.sat_parameters_pb2 import SatParameters

from eos.configuration.entities.task import (
    DynamicTaskDeviceConfig,
    DynamicTaskResourceConfig,
    TaskConfig,
    TaskDeviceConfig,
)
from eos.configuration.experiment_graph.experiment_graph import ExperimentGraph
from eos.configuration.validation import validation_utils
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
    device_assignments: dict[str, dict[str, dict[str, TaskDeviceConfig]]]
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
        params.max_time_in_seconds = 30.0
        params.num_search_workers = 0
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
        experiments: dict[str, tuple[str, ExperimentGraph]],
        task_durations: dict[str, dict[str, int]],
        schedule: dict[str, dict[str, int]],
        completed_by_exp: dict[str, set[str]],
        running_by_exp: dict[str, set[str]],
        current_time: int,
        experiment_priorities: dict[str, int],
        eligible_devices_by_type: dict[str, list[tuple[str, str]]],
        eligible_resources_by_type: dict[str, list[tuple[str, str]]],
        previous_device_assignments: dict[str, dict[str, dict[str, TaskDeviceConfig]]] | None = None,
        previous_resource_assignments: dict[str, dict[str, dict[str, str]]] | None = None,
        parameter_overrides: dict[str, float | int | bool] | None = None,
    ):
        self._experiments = experiments
        self._task_durations = task_durations
        self._schedule = schedule
        self._completed_by_exp = completed_by_exp
        self._running_by_exp = running_by_exp
        self._current_time = current_time
        self._experiment_priorities = experiment_priorities
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
        self._device_references: dict[tuple[str, str], list[tuple[str, str, str]]] = (
            {}
        )  # (exp, task) -> [(device_name, ref_task, ref_device)]
        self._resource_references: dict[tuple[str, str], list[tuple[str, str, str]]] = (
            {}
        )  # (exp, task) -> [(resource_name, ref_task, ref_resource)]
        self._resource_intervals: dict[str, list[cp_model.IntervalVar]] = {}
        self._horizon: int = 0
        self._makespan: cp_model.IntVar | None = None

    def _calculate_horizon(self) -> int:
        """Calculate horizon and refresh task durations."""
        horizon = self._current_time
        self._task_durations.clear()

        for exp_name, (_, exp_graph) in self._experiments.items():
            tasks = exp_graph.get_topologically_sorted_tasks()
            durations = {task_name: exp_graph.get_task_config(task_name).duration for task_name in tasks}
            horizon += sum(durations.values())
            self._task_durations[exp_name] = durations

        return horizon

    def _eligible_dynamic_devices_for(self, device_req: DynamicTaskDeviceConfig) -> list[tuple[str, str]]:
        """Get eligible concrete devices for a dynamic request after filtering."""
        return filter_device_pool(device_req, self._eligible_devices_by_type.get(device_req.device_type, ()))

    def _eligible_dynamic_resources_for(self, cont_req: DynamicTaskResourceConfig) -> list[tuple[str, str]]:
        """Get eligible concrete resources for a dynamic request after filtering."""
        return list(self._eligible_resources_by_type.get(cont_req.resource_type, []))

    def _create_dynamic_device_slot(
        self,
        exp_name: str,
        task_name: str,
        dev_req: DynamicTaskDeviceConfig,
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
                    f"assign_{exp_name}_{task_name}_{dev_req.device_type}_slot{slot_index}_{lab_name}_{device_name}"
                ),
                interval_name=(
                    f"opt_{exp_name}_{task_name}_iv_{dev_req.device_type}_slot{slot_index}_{lab_name}_{device_name}"
                ),
                resource_bucket=f"device_{lab_name}_{device_name}",
            )

            slot_choices.append(((lab_name, device_name), present))
            present_bools.append(present)

        return slot_choices, present_bools

    def _add_dynamic_device_constraints(
        self,
        exp_name: str,
        task_name: str,
        task_config: TaskConfig,
        start_var: cp_model.IntVar,
        end_var: cp_model.IntVar,
        duration: int,
    ) -> None:
        """Add dynamic device allocation constraints for a task (single selection)."""
        slots: list[list[tuple[tuple[str, str], cp_model.IntVar]]] = []

        for dev_req in task_config.devices.values():
            if not isinstance(dev_req, DynamicTaskDeviceConfig):
                continue

            eligible = self._eligible_dynamic_devices_for(dev_req)
            if not eligible:
                # Force infeasibility if no eligible devices exist
                dummy = self.model.NewIntVar(0, 0, f"{exp_name}_{task_name}_no_dynamic_options")
                self.model.Add(dummy == 1)
                continue

            # Single selection
            slot_choices, present_bools = self._create_dynamic_device_slot(
                exp_name, task_name, dev_req, eligible, 0, start_var, end_var, duration
            )
            self.model.AddExactlyOne(present_bools)
            slots.append(slot_choices)

        if slots:
            self._dynamic_choice_vars[(exp_name, task_name)] = slots

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
        exp_name: str,
        task_name: str,
        task_config: TaskConfig,
        start_var: cp_model.IntVar,
        end_var: cp_model.IntVar,
        duration: int,
    ) -> None:
        """Add dynamic resource allocation constraints for resource requests in the task config (single selection)."""
        entries: list[tuple[str, list[tuple[tuple[str, str], cp_model.IntVar]]]] = []

        for name, value in task_config.resources.items():
            if isinstance(value, str):
                continue

            # value is DynamicTaskResourceConfig
            eligible = self._eligible_dynamic_resources_for(value)
            if not eligible:
                # Force infeasibility if no eligible resources exist
                dummy = self.model.NewIntVar(0, 0, f"{exp_name}_{task_name}_no_dynamic_resource_options")
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
                    present_name=(f"assign_{exp_name}_{task_name}_resource_{name}_slot0_{lab_name}_{resource_name}"),
                    interval_name=(f"opt_{exp_name}_{task_name}_civ_{name}_slot0_{resource_name}"),
                    resource_bucket=f"resource_{resource_name}",
                )
                choices.append(((lab_name, resource_name), present))
                present_bools.append(present)

            if present_bools:
                self.model.AddExactlyOne(present_bools)

            entries.append((name, choices))

        if entries:
            self._dynamic_resource_choice_vars[(exp_name, task_name)] = entries

    def _create_task_time_variables(
        self, exp_name: str, task_name: str, duration: int, is_running: bool
    ) -> TaskVariables:
        """Create time variables (start, end, interval) for a task."""
        start_lb = 0 if is_running else self._current_time
        end_lb = 0 if is_running else self._current_time

        start_var = self.model.NewIntVar(start_lb, self._horizon, f"{exp_name}_{task_name}_start")
        end_var = self.model.NewIntVar(end_lb, self._horizon, f"{exp_name}_{task_name}_end")
        interval_var = self.model.NewIntervalVar(start_var, duration, end_var, f"{exp_name}_{task_name}_interval")

        return TaskVariables(start=start_var, end=end_var, interval=interval_var)

    def _process_task_devices(
        self, exp_name: str, task_name: str, task_config: TaskConfig, task_vars: TaskVariables
    ) -> None:
        """Process specific and dynamic device requirements for a task."""
        # Specific devices: create fixed resource intervals
        for dev in task_config.devices.values():
            if isinstance(dev, TaskDeviceConfig):
                resource_name = f"device_{dev.lab_name}_{dev.name}"
                self._resource_intervals.setdefault(resource_name, []).append(task_vars.interval)

        # Dynamic devices: create optional intervals for each eligible device
        self._add_dynamic_device_constraints(
            exp_name, task_name, task_config, task_vars.start, task_vars.end, task_config.duration
        )

    def _process_task_resources(
        self, exp_name: str, task_name: str, task_config: TaskConfig, task_vars: TaskVariables
    ) -> None:
        """Process specific and dynamic resource requirements for a task."""
        # Specific resources (non-references): create fixed resource intervals
        for resource_value in task_config.resources.values():
            if isinstance(resource_value, str) and not validation_utils.is_resource_reference(resource_value):
                resource_name = f"resource_{resource_value}"
                self._resource_intervals.setdefault(resource_name, []).append(task_vars.interval)

        # Dynamic resources: optional intervals for eligible resources
        self._add_dynamic_resource_constraints(
            exp_name, task_name, task_config, task_vars.start, task_vars.end, task_config.duration
        )

    def _track_task_references(self, exp_name: str, task_name: str, task_config: TaskConfig) -> None:
        """Track device and resource references for later constraint creation."""
        # Track device references
        for device_name, device_value in task_config.devices.items():
            if isinstance(device_value, str) and validation_utils.is_device_reference(device_value):
                ref_task_name, ref_device_name = device_value.split(".")
                self._device_references.setdefault((exp_name, task_name), []).append(
                    (device_name, ref_task_name, ref_device_name)
                )

        # Track resource references
        for resource_name, resource_value in task_config.resources.items():
            if isinstance(resource_value, str) and validation_utils.is_resource_reference(resource_value):
                ref_task_name, ref_resource_name = resource_value.split(".")
                self._resource_references.setdefault((exp_name, task_name), []).append(
                    (resource_name, ref_task_name, ref_resource_name)
                )

    def _apply_task_timing_constraints(
        self, exp_name: str, task_name: str, task_vars: TaskVariables, duration: int, is_running: bool
    ) -> None:
        """Apply timing constraints: fix running tasks or constrain duration."""
        if is_running:
            fixed_start = self._schedule.get(exp_name, {})[task_name]
            self.model.Add(task_vars.start == fixed_start)
            self.model.Add(task_vars.end == fixed_start + duration)
        else:
            self.model.Add(task_vars.end == task_vars.start + duration)

    def _create_task_variables(self) -> None:
        """Create task variables, resource intervals, and dynamic choice variables."""
        for exp_name, (_, exp_graph) in self._experiments.items():
            tasks = exp_graph.get_topologically_sorted_tasks()
            for task_name in tasks:
                if task_name in self._completed_by_exp.get(exp_name, set()):
                    continue

                task_config: TaskConfig = exp_graph.get_task_config(task_name)
                is_running = task_name in self._running_by_exp.get(exp_name, set())

                # Create time variables
                task_vars = self._create_task_time_variables(exp_name, task_name, task_config.duration, is_running)
                self._task_vars[(exp_name, task_name)] = task_vars

                # Process devices and resources
                self._process_task_devices(exp_name, task_name, task_config, task_vars)
                self._process_task_resources(exp_name, task_name, task_config, task_vars)

                # Track references
                self._track_task_references(exp_name, task_name, task_config)

                # Apply timing constraints
                self._apply_task_timing_constraints(exp_name, task_name, task_vars, task_config.duration, is_running)

    def _apply_precedence_constraints(self) -> None:
        """Apply precedence constraints: start(task) >= end(dep) for each dependency."""
        for exp_name, (_, exp_graph) in self._experiments.items():
            tasks = exp_graph.get_topologically_sorted_tasks()
            for task_name in tasks:
                if (exp_name, task_name) not in self._task_vars:
                    continue

                for dep_task_name in exp_graph.get_task_dependencies(task_name):
                    if (exp_name, dep_task_name) in self._task_vars:
                        self.model.Add(
                            self._task_vars[(exp_name, task_name)].start
                            >= self._task_vars[(exp_name, dep_task_name)].end
                        )

    def _apply_resource_constraints(self) -> None:
        """Apply NoOverlap constraints per resource (devices and resources)."""
        for intervals in self._resource_intervals.values():
            if intervals:
                self.model.AddNoOverlap(intervals)

    def _apply_experiment_ordering_constraints(self) -> None:
        """
        If priorities differ, higher-priority experiments must finish no later
        than lower-priority ones.
        """
        exp_finish_times = {}
        for exp_name, (_, exp_graph) in self._experiments.items():
            tasks = [
                task_name
                for task_name in exp_graph.get_topologically_sorted_tasks()
                if (exp_name, task_name) in self._task_vars
            ]
            if tasks:
                finish_time = self.model.NewIntVar(0, self._horizon, f"{exp_name}_finish")
                self.model.AddMaxEquality(
                    finish_time, [self._task_vars[(exp_name, task_name)].end for task_name in tasks]
                )
                exp_finish_times[exp_name] = finish_time

        # Only add ordering constraints if experiments have differing priorities
        if len(set(self._experiment_priorities.values())) <= 1:
            return

        for exp_i, exp_i_finish_time in exp_finish_times.items():
            for exp_j, exp_j_finish_time in exp_finish_times.items():
                if exp_i == exp_j:
                    continue
                if self._experiment_priorities.get(exp_i, 0) > self._experiment_priorities.get(exp_j, 0):
                    self.model.Add(exp_i_finish_time <= exp_j_finish_time)

    def _apply_group_constraints(self) -> None:
        """Tasks in the same group are consecutive: next.start == current.end."""
        for exp_name, (_, exp_graph) in self._experiments.items():
            all_tasks_sorted = exp_graph.get_topologically_sorted_tasks()

            # Collect tasks by group, maintaining topological order
            groups: dict[str, list[str]] = {}
            for task_name in all_tasks_sorted:
                if (exp_name, task_name) not in self._task_vars:
                    continue

                task_config = exp_graph.get_task_config(task_name)
                if task_config.group:
                    groups.setdefault(task_config.group, []).append(task_name)

            # Apply constraints for each group
            for _group_name, task_names in groups.items():
                if len(task_names) <= 1:
                    continue

                for i in range(len(task_names) - 1):
                    current_task = task_names[i]
                    next_task = task_names[i + 1]
                    self.model.Add(
                        self._task_vars[(exp_name, next_task)].start == self._task_vars[(exp_name, current_task)].end
                    )

    def _apply_device_reference_constraints(self) -> None:
        """Enforce that device references use the same device as the referenced task."""
        for (exp_name, task_name), refs in self._device_references.items():
            _, exp_graph = self._experiments[exp_name]
            task_config = exp_graph.get_task_config(task_name)
            task_vars = self._task_vars[(exp_name, task_name)]
            duration = task_config.duration

            for device_name, ref_task_name, ref_device_name in refs:
                # Get the referenced task's config and find the slot for the referenced device
                ref_task_config = exp_graph.get_task_config(ref_task_name)
                ref_device_value = ref_task_config.devices.get(ref_device_name)

                if isinstance(ref_device_value, DynamicTaskDeviceConfig):
                    # Find the slot index in the referenced task
                    ref_slot_idx = 0
                    for ref_dev_name, ref_dev_val in ref_task_config.devices.items():
                        if ref_dev_name == ref_device_name:
                            break
                        if isinstance(ref_dev_val, DynamicTaskDeviceConfig):
                            ref_slot_idx += 1

                    # Get the choice variables from the referenced task
                    ref_slots = self._dynamic_choice_vars.get((exp_name, ref_task_name), [])
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
                            f"opt_ref_{exp_name}_{task_name}_{device_name}_{lab_name}_{dev_name}",
                        )
                        resource_name = f"device_{lab_name}_{dev_name}"
                        self._resource_intervals.setdefault(resource_name, []).append(optional_interval)

                elif isinstance(ref_device_value, TaskDeviceConfig):
                    # Referenced device is specific, add this task's interval to that device's resource bucket
                    resource_name = f"device_{ref_device_value.lab_name}_{ref_device_value.name}"
                    self._resource_intervals.setdefault(resource_name, []).append(task_vars.interval)

    def _apply_resource_reference_constraints(self) -> None:
        """Enforce that resource references use the same resource as the referenced task."""
        for (exp_name, task_name), refs in self._resource_references.items():
            _, exp_graph = self._experiments[exp_name]
            task_config = exp_graph.get_task_config(task_name)
            task_vars = self._task_vars[(exp_name, task_name)]
            duration = task_config.duration

            for resource_name, ref_task_name, ref_resource_name in refs:
                # Get the referenced task's config and find the resource
                ref_task_config = exp_graph.get_task_config(ref_task_name)
                ref_resource_value = ref_task_config.resources.get(ref_resource_name)

                if isinstance(ref_resource_value, DynamicTaskResourceConfig):
                    # Find the entry index in the referenced task's dynamic resource choices
                    ref_entries = self._dynamic_resource_choice_vars.get((exp_name, ref_task_name), [])
                    for entry_name, choices in ref_entries:
                        if entry_name == ref_resource_name:
                            # Create optional intervals for each possible resource choice
                            # Each interval is only active when the referenced task selects that specific resource
                            for (_lab_name, concrete_resource_name), ref_bool_var in choices:
                                # Create an optional interval that's only active when ref task selects this resource
                                optional_interval = self.model.NewOptionalIntervalVar(
                                    task_vars.start,
                                    duration,
                                    task_vars.end,
                                    ref_bool_var,  # Only active when referenced task selects this resource
                                    f"opt_res_ref_{exp_name}_{task_name}_{resource_name}_{concrete_resource_name}",
                                )
                                bucket_name = f"resource_{concrete_resource_name}"
                                self._resource_intervals.setdefault(bucket_name, []).append(optional_interval)
                            break
                elif isinstance(ref_resource_value, str) and not validation_utils.is_resource_reference(
                    ref_resource_value
                ):
                    # Referenced resource is specific (non-reference string), add this task's interval to that
                    # resource bucket
                    bucket_name = f"resource_{ref_resource_value}"
                    self._resource_intervals.setdefault(bucket_name, []).append(task_vars.interval)

    def _build_model(self) -> None:
        """Build the complete scheduling model."""
        self._horizon = self._calculate_horizon()
        self._create_task_variables()
        self._apply_precedence_constraints()
        self._apply_device_reference_constraints()
        self._apply_resource_reference_constraints()
        self._apply_resource_constraints()
        self._apply_experiment_ordering_constraints()
        self._apply_group_constraints()

        # Create makespan variable
        self._makespan = self.model.NewIntVar(0, self._horizon, "makespan")
        self.model.AddMaxEquality(self._makespan, [tv.end for tv in self._task_vars.values()])

    def _extract_schedule(self) -> dict[str, dict[str, int]]:
        """Extract task schedule from solved model efficiently in a single pass."""
        schedule: dict[str, dict[str, int]] = {exp: {} for exp in self._experiments}
        for (exp_name, task_name), tv in self._task_vars.items():
            schedule[exp_name][task_name] = self.solver.Value(tv.start)
        return schedule

    def _extract_device_assignments(self) -> dict[str, dict[str, dict[str, TaskDeviceConfig]]]:
        """Extract dynamic + specific device assignments per task (concise logging)."""
        # Start with previous assignments (from completed/running tasks)
        device_assignments: dict[str, dict[str, dict[str, TaskDeviceConfig]]] = {
            exp: {task: devs.copy() for task, devs in tasks.items()}
            for exp, tasks in self._previous_device_assignments.items()
        }

        for (exp_name, task_name), _tv in self._task_vars.items():
            _, exp_graph = self._experiments[exp_name]
            task_cfg: TaskConfig = exp_graph.get_task_config(task_name)
            task_devices: dict[str, TaskDeviceConfig] = {}

            # Extract selections preserving device names from task_cfg
            slots = self._dynamic_choice_vars.get((exp_name, task_name), [])
            slot_idx = 0

            # Dynamic and specific devices
            for device_name, dev in task_cfg.devices.items():
                if isinstance(dev, DynamicTaskDeviceConfig):
                    if slot_idx < len(slots):
                        slot = slots[slot_idx]
                        for (lab_name, dev_name), b in slot:
                            if self.solver.Value(b) == 1:
                                task_devices[device_name] = TaskDeviceConfig(lab_name=lab_name, name=dev_name)
                                break
                        slot_idx += 1
                elif isinstance(dev, TaskDeviceConfig):
                    task_devices[device_name] = dev

            # Resolve device references against already-built assignments
            for device_name, dev in task_cfg.devices.items():
                if isinstance(dev, str) and validation_utils.is_device_reference(dev):
                    ref_task_name, ref_device_name = dev.split(".")
                    ref_map = device_assignments.get(exp_name, {}).get(ref_task_name, {})
                    ref_device = ref_map.get(ref_device_name)
                    if ref_device:
                        task_devices[device_name] = ref_device

            if task_devices:
                device_assignments.setdefault(exp_name, {})[task_name] = task_devices

        return device_assignments

    def _extract_resource_assignments(self) -> dict[str, dict[str, dict[str, str]]]:
        """Extract chosen resources per task and resource name (concise logging)."""
        # Start with previous assignments (from completed/running tasks)
        resource_assignments: dict[str, dict[str, dict[str, str]]] = {
            exp: {task: res.copy() for task, res in tasks.items()}
            for exp, tasks in self._previous_resource_assignments.items()
        }

        for (exp_name, task_name), _tv in self._task_vars.items():
            _, exp_graph = self._experiments[exp_name]
            task_cfg: TaskConfig = exp_graph.get_task_config(task_name)
            assigned: dict[str, str] = {}

            # Dynamic resource assignments
            entries = self._dynamic_resource_choice_vars.get((exp_name, task_name), [])
            for name, choices in entries:
                for (_lab_name, resource_name), b in choices:
                    if self.solver.Value(b) == 1:
                        assigned[name] = resource_name
                        break

            # Explicit (non-reference) strings
            for name, value in task_cfg.resources.items():
                if isinstance(value, str) and not validation_utils.is_resource_reference(value):
                    assigned[name] = value

            # Resolve resource references
            for name, value in task_cfg.resources.items():
                if isinstance(value, str) and validation_utils.is_resource_reference(value):
                    ref_task_name, ref_resource_name = value.split(".")
                    ref_map = resource_assignments.get(exp_name, {}).get(ref_task_name, {})
                    ref_value = ref_map.get(ref_resource_name)
                    if ref_value:
                        assigned[name] = ref_value

            if assigned:
                resource_assignments.setdefault(exp_name, {})[task_name] = assigned

        return resource_assignments

    def _solve_phase1_makespan(self) -> tuple[int, int, float]:
        """
        Phase 1: Minimize makespan.

        Returns: (status, optimal_makespan, duration_ms)
        """
        with Timer() as timer:
            self.model.Minimize(self._makespan)
            status = self.solver.Solve(self.model)
        duration_ms = timer.get_duration("ms")

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise EosSchedulerError("Could not compute a valid schedule in the makespan optimization pass with CP-SAT.")

        optimal_makespan = self.solver.Value(self._makespan)
        return status, optimal_makespan, duration_ms

    def _solve_phase2_start_times(self, optimal_makespan: int) -> tuple[int, float]:
        """
        Phase 2: Minimize task start times with fixed makespan.

        Returns: (status, duration_ms)
        """
        with Timer() as timer:
            self.model.Add(self._makespan <= optimal_makespan)
            total_start = self.model.NewIntVar(0, self._horizon * len(self._task_vars), "total_start")
            self.model.Add(total_start == sum(task_vars.start for task_vars in self._task_vars.values()))
            self.model.Minimize(total_start)
            status = self.solver.Solve(self.model)
        duration_ms = timer.get_duration("ms")

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            log.warning("Could not refine schedule in the task start time minimization optimization pass with CP-SAT.")

        return status, duration_ms

    def solve(self) -> SchedulingSolution:
        """
        Solve the scheduling problem with two-phase optimization.

        Phase 1: Minimize makespan
        Phase 2: Minimize task start times with fixed makespan
        """
        self._build_model()

        # Phase 1: Minimize makespan
        _, optimal_makespan, time_phase1 = self._solve_phase1_makespan()

        # Phase 2: Minimize start times
        status, time_phase2 = self._solve_phase2_start_times(optimal_makespan)

        # Extract solution
        schedule = self._extract_schedule()
        device_assignments = self._extract_device_assignments()
        resource_assignments = self._extract_resource_assignments()
        compute_duration = time_phase1 + time_phase2
        status_str = "optimal" if status == cp_model.OPTIMAL else "feasible"

        # Keep INFO concise; full schedule available at DEBUG if needed
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
