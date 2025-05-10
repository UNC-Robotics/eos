import asyncio

from ortools.sat.python import cp_model
from ortools.sat.sat_parameters_pb2 import SatParameters

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.experiment_graph.experiment_graph import ExperimentGraph
from eos.devices.device_manager import DeviceManager
from eos.experiments.experiment_manager import ExperimentManager
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.resource_allocation.resource_allocation_manager import ResourceAllocationManager
from eos.scheduling.base_scheduler import BaseScheduler
from eos.scheduling.cpsat_scheduling_model_builder import CpSatSchedulingModelBuilder, OptimizationPass
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerRegistrationError, EosSchedulerError
from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import inject
from eos.utils.timer import Timer


class CpSatScheduler(BaseScheduler):
    """
    A scheduler that strives for global optimality with regards to minimizing makespan.
    Uses the CP-SAT solver to compute a global schedule across all registered experiments.
    The schedule accounts for each task's expected duration, experiment priority, task dependencies, and required
    resources.
    """

    @inject
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        experiment_manager: ExperimentManager,
        task_manager: TaskManager,
        device_manager: DeviceManager,
        resource_allocation_manager: ResourceAllocationManager,
    ):
        super().__init__(
            configuration_manager, experiment_manager, task_manager, device_manager, resource_allocation_manager
        )
        self._schedule: dict[str, dict[str, int]] = {}
        self._schedule_is_stale = False

        # For each experiment: {task_id: duration}
        self._task_durations: dict[str, dict[str, int]] = {}

        # The current "virtual" time
        self._current_time: int = 0

        self._cpsolver_parameters = SatParameters()
        self._cpsolver_parameters.max_time_in_seconds = 30.0
        self._cpsolver_parameters.num_search_workers = 0
        self._cpsolver_parameters.push_all_tasks_toward_start = True
        self._cpsolver_parameters.optimize_with_lb_tree_search = True
        self._cpsolver_parameters.use_objective_lb_search = True
        self._cpsolver_parameters.use_timetable_edge_finding_in_cumulative = True
        self._cpsolver_parameters.linearization_level = 2
        self._cpsolver_parameters.use_hard_precedences_in_cumulative = True
        self._cpsolver_parameters.use_strong_propagation_in_disjunctive = True
        self._cpsolver_parameters.use_dynamic_precedence_in_disjunctive = True

        log.debug("CP-SAT scheduler initialized.")

    async def register_experiment(
        self, experiment_id: str, experiment_type: str, experiment_graph: ExperimentGraph
    ) -> None:
        async with self._lock:
            await super().register_experiment(experiment_id, experiment_type, experiment_graph)

            self._schedule_is_stale = True

    async def unregister_experiment(self, db: AsyncDbSession, experiment_id: str) -> None:
        async with self._lock:
            await super().unregister_experiment(db, experiment_id)

            self._schedule_is_stale = True
            if not self._registered_experiments:
                self._schedule.clear()
                self._current_time = 0

    async def update_parameters(self, parameters: dict) -> None:
        """Update the CP-SAT solver parameters.

        This method allows modifying the CP-SAT solver configuration at runtime
        to tune performance for different workloads.

        :param parameters: Dictionary of parameter names and values to update
        :type parameters: dict

        :return: None

        Supports any parameter supported by ``ortools.sat.sat_parameters_pb2.SatParameters``

        **Example:**

        .. code-block:: python

            await scheduler.update_solver_parameters({
                "max_time_in_seconds": 60.0,
                "num_workers": 4
            })
        """
        async with self._lock:
            for param_name, param_value in parameters.items():
                if hasattr(self._cpsolver_parameters, param_name):
                    setattr(self._cpsolver_parameters, param_name, param_value)
                else:
                    log.warning(f"Unsupported CP-SAT parameter: {param_name}")

            # Mark the schedule as stale to force recomputation with new parameters
            self._schedule_is_stale = True

    async def _compute_schedule(self, db: AsyncDbSession) -> None:
        """
        Build and solve the CP-SAT model in two phases.
          Phase 1: Minimize the makespan.
          Phase 2: With the makespan fixed, refine the schedule by minimizing the task start times.
        """
        completed_by_exp = await self._experiment_manager.get_all_completed_tasks(
            db, list(self._registered_experiments.keys())
        )
        running_by_exp = {
            exp_id: set(self._allocated_resources.get(exp_id, {}).keys()) for exp_id in self._registered_experiments
        }

        # Build a dictionary mapping experiment IDs to their priority
        experiment_ids = list(self._registered_experiments.keys())
        experiment_priority_tasks = [self._experiment_manager.get_experiment(db, exp_id) for exp_id in experiment_ids]
        experiment_priorities = {
            exp_id: exp.priority
            for exp_id, exp in zip(experiment_ids, await asyncio.gather(*experiment_priority_tasks), strict=True)
        }

        # Build the CP-SAT model
        model_builder = CpSatSchedulingModelBuilder(
            experiments=self._registered_experiments,
            task_durations=self._task_durations,
            schedule=self._schedule,
            completed_by_exp=completed_by_exp,
            running_by_exp=running_by_exp,
            current_time=self._current_time,
            experiment_priorities=experiment_priorities,
        )

        solver = cp_model.CpSolver()
        solver.parameters.CopyFrom(self._cpsolver_parameters)

        # --- Phase 1: Minimize makespan ---
        with Timer() as timer_phase1:
            model, task_vars, objective = model_builder.build_model(optimization_pass=OptimizationPass.MAKESPAN)
            status = solver.Solve(model)
        time_phase1 = timer_phase1.get_duration("ms")

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise EosSchedulerError("Could not compute a valid schedule in the makespan optimization pass with CP-SAT.")

        optimal_makespan = solver.Value(objective)

        # --- Phase 2: Minimize task start times ---
        with Timer() as timer_phase2:
            refined_model, refined_task_vars, refined_objective = model_builder.build_model(
                target_makespan=optimal_makespan,
                optimization_pass=OptimizationPass.TASK_START_TIMES,
            )
            status = solver.Solve(refined_model)
        time_phase2 = timer_phase2.get_duration("ms")

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            log.warning("Could not refine schedule in the task start time minimization optimization pass with CP-SAT.")

        # Extract the refined schedule.
        new_schedule = {
            exp_id: {
                task_id: solver.Value(tv.start) for (e_id, task_id), tv in refined_task_vars.items() if e_id == exp_id
            }
            for exp_id in self._registered_experiments
        }
        self._schedule = new_schedule

        status_str = "optimal" if status == cp_model.OPTIMAL else "feasible"
        log.info(
            f"Computed {status_str} schedule (makespan={optimal_makespan - self._current_time}, "
            f"compute_duration={time_phase1 + time_phase2:.2f} ms):\n{new_schedule}",
        )

    async def request_tasks(self, db: AsyncDbSession, experiment_id: str) -> list[ScheduledTask]:
        """
        Return tasks eligible for execution for a given experiment. Eligibility is determined by:
          1. Not already completed.
          2. Dependencies met.
          3. Scheduled start time is not later than the current time.
          4. Required resources (devices/containers) are available.
        """
        if experiment_id not in self._registered_experiments:
            raise EosSchedulerRegistrationError(f"Experiment {experiment_id} is not registered.")

        async with self._lock:
            # Retrieve completed tasks for all experiments.
            all_completed_by_exp = await self._experiment_manager.get_all_completed_tasks(
                db, list(self._registered_experiments.keys())
            )

            # Get completed tasks for the current experiment.
            completed_tasks = all_completed_by_exp.get(experiment_id, set())

            # Release resources for completed tasks across all experiments.
            release_tasks = []
            for exp_id, completed in all_completed_by_exp.items():
                allocated_tasks = set(self._allocated_resources.get(exp_id, {}))
                tasks_to_release = completed.intersection(allocated_tasks)
                for task_id in tasks_to_release:
                    release_tasks.append(self._release_task_resources(db, exp_id, task_id))
            await asyncio.gather(*release_tasks)

            # Compute the global current time from all completed tasks across experiments.
            max_end_time = max(
                [0]  # Default if no tasks found
                + [
                    self._schedule[exp_id][task_id] + self._task_durations[exp_id][task_id]
                    for exp_id, completed in all_completed_by_exp.items()
                    for task_id in completed
                    if task_id in self._schedule[exp_id]
                ]
            )

            self._current_time = max(self._current_time, max_end_time)

            if self._schedule_is_stale:
                await self._compute_schedule(db)
                self._schedule_is_stale = False

            # Process tasks for the given experiment.
            _, exp_graph = self._registered_experiments[experiment_id]
            all_tasks = exp_graph.get_topologically_sorted_tasks()

            scheduled_tasks = []
            for task_id in all_tasks:
                if task_id in completed_tasks:
                    continue
                if self._schedule[experiment_id][task_id] > self._current_time:
                    continue

                scheduled_task = await self._check_and_allocate_resources(
                    db, experiment_id, task_id, completed_tasks, exp_graph
                )
                if scheduled_task:
                    scheduled_tasks.append(scheduled_task)

            return scheduled_tasks
