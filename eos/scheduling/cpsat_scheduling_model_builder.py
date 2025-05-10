from dataclasses import dataclass
from enum import Enum
from ortools.sat.python import cp_model
from eos.configuration.experiment_graph.experiment_graph import ExperimentGraph


class OptimizationPass(Enum):
    """
    Enumeration of supported optimization passes.

    :var MAKESPAN: Minimize the overall makespan.
    :var TASK_START_TIMES: With a fixed makespan, minimize the task start times.
    """

    MAKESPAN = "makespan"
    TASK_START_TIMES = "task_start_times"


@dataclass
class TaskVariables:
    """
    Container for task scheduling variables.

    :param start: The start time variable.
    :param end: The end time variable.
    :param interval: The interval variable representing the task duration.
    """

    start: cp_model.IntVar
    end: cp_model.IntVar
    interval: cp_model.IntervalVar


class CpSatSchedulingModelBuilder:
    """
    Encapsulates the CP-SAT model construction for scheduling.

    This builder creates a base model with task variables and common constraints,
    then adds a pass-specific objective. Constraints such as task precedence,
    resource non-overlap, and experiment ordering are defined once.
    """

    def __init__(
        self,
        experiments: dict[str, tuple[str, ExperimentGraph]],
        task_durations: dict[str, dict[str, int]],
        schedule: dict[str, dict[str, int]],
        running_by_exp: dict[str, set[str]],
        completed_by_exp: dict[str, set[str]],
        current_time: int,
        experiment_priorities: dict[str, int],
    ):
        """
        Initialize the model builder.

        :param experiments: A dictionary mapping experiment IDs to a tuple of (experiment type, ExperimentGraph).
        :param task_durations: A dictionary mapping experiment IDs to task durations.
        :param schedule: A dictionary representing the current schedule.
        :param fixed_tasks_by_exp: A dictionary mapping experiment IDs to the set of fixed (completed or running) task
        IDs.
        :param current_time: The current virtual time.
        :param experiment_priorities: A dictionary mapping experiment IDs to their priority.
        """
        self._experiments = experiments
        self._task_durations = task_durations
        self._schedule = schedule
        self._running_by_exp = running_by_exp
        self._completed_by_exp = completed_by_exp
        self._current_time = current_time
        self._experiment_priorities = experiment_priorities

    def calculate_horizon(self) -> int:
        """
        Calculate the scheduling horizon as the sum of task durations across all experiments.
        Also updates the task durations per experiment.

        :return: The computed horizon.
        """
        horizon = self._current_time
        self._task_durations.clear()

        for exp_id, (_, exp_graph) in self._experiments.items():
            tasks = exp_graph.get_topologically_sorted_tasks()
            durations = {task_id: exp_graph.get_task_config(task_id).duration for task_id in tasks}
            horizon += sum(durations.values())
            self._task_durations[exp_id] = durations

        return horizon

    def create_task_variables(
        self, model: cp_model.CpModel, horizon: int
    ) -> tuple[dict[tuple[str, str], TaskVariables], dict[str, list[cp_model.IntervalVar]]]:
        """
        Create task variables for each task and assign resource intervals.

        For each task, a start, end, and interval variable is created. If the task is fixed,
        its start and end times are constrained to known values.

        :param model: The CP-SAT model instance.
        :param horizon: The scheduling horizon.
        :return: A tuple containing a dictionary of task variables and a dictionary of resource intervals.
        """
        task_vars: dict[tuple[str, str], TaskVariables] = {}
        resource_intervals: dict[str, list[cp_model.IntervalVar]] = {}

        for exp_id, (_, exp_graph) in self._experiments.items():
            tasks = exp_graph.get_topologically_sorted_tasks()
            for task_id in tasks:
                if task_id in self._completed_by_exp.get(exp_id, set()):
                    continue

                task_config = exp_graph.get_task_config(task_id)
                duration = task_config.duration

                start_var = model.NewIntVar(self._current_time, horizon, f"{exp_id}_{task_id}_start")
                end_var = model.NewIntVar(self._current_time, horizon, f"{exp_id}_{task_id}_end")
                interval_var = model.NewIntervalVar(start_var, duration, end_var, f"{exp_id}_{task_id}_interval")
                task_vars[(exp_id, task_id)] = TaskVariables(start=start_var, end=end_var, interval=interval_var)

                # Add resource intervals for devices.
                for device in task_config.devices:
                    resource_id = f"device_{device.lab_id}_{device.id}"
                    resource_intervals.setdefault(resource_id, []).append(interval_var)

                # Add resource intervals for containers.
                for container_id in task_config.containers.values():
                    resource_id = f"container_{container_id}"
                    resource_intervals.setdefault(resource_id, []).append(interval_var)

                # Fix the task's start and end times if it is running.
                if task_id in self._running_by_exp.get(exp_id, set()):
                    fixed_start = self._schedule.get(exp_id, {})[task_id]
                    model.Add(start_var == fixed_start)
                    model.Add(end_var == fixed_start + duration)
                else:
                    model.Add(end_var == start_var + duration)

        return task_vars, resource_intervals

    def apply_precedence_constraints(
        self, model: cp_model.CpModel, task_vars: dict[tuple[str, str], TaskVariables]
    ) -> None:
        """
        Enforce task precedence constraints.

        Each task's start time is constrained to be no earlier than the end times of its dependencies.

        :param model: The CP-SAT model instance.
        :param task_vars: Dictionary mapping (experiment_id, task_id) tuples to TaskVariables.
        """
        for exp_id, (_, exp_graph) in self._experiments.items():
            tasks = exp_graph.get_topologically_sorted_tasks()
            for task_id in tasks:
                # Ignore completed tasks
                if (exp_id, task_id) not in task_vars:
                    continue

                for dep_task_id in exp_graph.get_task_dependencies(task_id):
                    if (exp_id, dep_task_id) in task_vars:
                        model.Add(task_vars[(exp_id, task_id)].start >= task_vars[(exp_id, dep_task_id)].end)

    def apply_resource_constraints(
        self, model: cp_model.CpModel, resource_intervals: dict[str, list[cp_model.IntervalVar]]
    ) -> None:
        """
        Enforce resource constraints to ensure that tasks sharing a resource do not overlap.

        :param model: The CP-SAT model instance.
        :param resource_intervals: Dictionary mapping resource IDs to lists of interval variables.
        """
        for intervals in resource_intervals.values():
            if intervals:
                model.AddNoOverlap(intervals)

    def apply_experiment_ordering_constraints(
        self, model: cp_model.CpModel, task_vars: dict[tuple[str, str], TaskVariables], horizon: int
    ) -> None:
        """
        Apply ordering constraints for experiments based on experiment priority.

        For each experiment, a finish time variable is defined as the maximum end time of its tasks.
        If experiments have differing priorities, then for any two experiments, if one experiment has a higher
        priority (e.g., priority 2 > 1) then its finish time is constrained to be less than or equal to that of
        the lower priority experiment.

        If all experiments have the same priority, no ordering constraints are added.
        """
        exp_finish_times = {}
        for exp_id, (_, exp_graph) in self._experiments.items():
            tasks = [
                task_id for task_id in exp_graph.get_topologically_sorted_tasks() if (exp_id, task_id) in task_vars
            ]
            if tasks:
                finish_time = model.NewIntVar(0, horizon, f"{exp_id}_finish")
                model.AddMaxEquality(finish_time, [task_vars[(exp_id, task_id)].end for task_id in tasks])
                exp_finish_times[exp_id] = finish_time

        # Only add ordering constraints if experiments have differing priorities.
        if len(set(self._experiment_priorities.values())) <= 1:
            return

        # For any two experiments, if one has a higher priority, ensure its finish time is no later.
        for exp_i, exp_i_finish_time in exp_finish_times.items():
            for exp_j, exp_j_finish_time in exp_finish_times.items():
                if exp_i == exp_j:
                    continue
                if self._experiment_priorities.get(exp_i, 0) > self._experiment_priorities.get(exp_j, 0):
                    model.Add(exp_i_finish_time <= exp_j_finish_time)

    def build_base_model(self) -> tuple[cp_model.CpModel, dict[tuple[str, str], TaskVariables], int, cp_model.IntVar]:
        """
        Construct the base CP-SAT model including common constraints.

        This includes creating task variables, applying precedence and resource constraints,
        and enforcing experiment ordering.

        :return: A tuple containing:
                 - The CP-SAT model.
                 - A dictionary of task variables.
                 - The scheduling horizon.
                 - The makespan variable defined as the maximum end time over all tasks.
        """
        model = cp_model.CpModel()
        horizon = self.calculate_horizon()
        task_vars, resource_intervals = self.create_task_variables(model, horizon)

        self.apply_precedence_constraints(model, task_vars)
        self.apply_resource_constraints(model, resource_intervals)
        self.apply_experiment_ordering_constraints(model, task_vars, horizon)

        makespan = model.NewIntVar(0, horizon, "makespan")
        model.AddMaxEquality(makespan, [tv.end for tv in task_vars.values()])

        return model, task_vars, horizon, makespan

    def build_model(
        self,
        target_makespan: int | None = None,
        optimization_pass: OptimizationPass = OptimizationPass.MAKESPAN,
    ) -> tuple[cp_model.CpModel, dict[tuple[str, str], TaskVariables], cp_model.IntVar]:
        """
        Build the complete CP-SAT model for scheduling with a pass-specific objective.

        :param target_makespan: The target makespan to optimize for. Used only for the TASK_START_TIMES pass.
        :param optimization_pass: The optimization pass to execute, either MAKESPAN or TASK_START_TIMES.
        :return: A tuple containing the CP-SAT model, task variables, and the objective variable.
        """
        model, task_vars, horizon, makespan = self.build_base_model()

        if optimization_pass == OptimizationPass.MAKESPAN:
            model.Minimize(makespan)
            objective = makespan

        elif optimization_pass == OptimizationPass.TASK_START_TIMES:
            if target_makespan is None:
                raise ValueError("Fixed value for makespan is required for the TASK_START_TIMES optimization pass.")
            model.Add(makespan <= target_makespan)
            total_start = model.NewIntVar(0, horizon * len(task_vars), "total_start")
            model.Add(total_start == sum(tv.start for tv in task_vars.values()))
            model.Minimize(total_start)
            objective = total_start

        else:
            raise ValueError(f"Unknown optimization pass: {optimization_pass}")

        return model, task_vars, objective
