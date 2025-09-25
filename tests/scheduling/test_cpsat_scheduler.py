from typing import NamedTuple

from eos.experiments.entities.experiment import ExperimentDefinition
from eos.resource_allocation.entities.resource_request import ResourceRequestAllocationStatus
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerRegistrationError
from eos.tasks.entities.task import TaskDefinition
from tests.fixtures import *


EXPERIMENT_TYPE = "abstract_experiment_2"


class ExpectedTask(NamedTuple):
    """Helper class to define expected task scheduling results"""

    task_id: str
    lab_id: str
    device_id: str


@pytest.fixture()
def experiment_graph(configuration_manager):
    experiment = configuration_manager.experiments["abstract_experiment_2"]
    return ExperimentGraph(experiment)


@pytest.mark.parametrize("setup_lab_experiment", [("abstract_lab", EXPERIMENT_TYPE)], indirect=True)
class TestCpSatScheduler:
    @pytest.mark.asyncio
    async def test_register_experiment(self, cpsat_scheduler, experiment_graph):
        await cpsat_scheduler.register_experiment("exp1", EXPERIMENT_TYPE, experiment_graph)
        assert cpsat_scheduler._registered_experiments["exp1"] == (
            EXPERIMENT_TYPE,
            experiment_graph,
        )

    @pytest.mark.asyncio
    async def test_register_invalid_experiment(self, cpsat_scheduler, experiment_graph):
        with pytest.raises(EosSchedulerRegistrationError):
            await cpsat_scheduler.register_experiment("exp1", "invalid_type", experiment_graph)

    @pytest.mark.asyncio
    async def test_unregister_experiment(self, db, cpsat_scheduler, experiment_graph, setup_lab_experiment):
        # Register experiment
        await cpsat_scheduler.register_experiment("exp1", EXPERIMENT_TYPE, experiment_graph)
        assert "exp1" in cpsat_scheduler._registered_experiments

        # Unregister experiment
        await cpsat_scheduler.unregister_experiment(db, "exp1")
        assert "exp1" not in cpsat_scheduler._registered_experiments

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_experiment(self, db, cpsat_scheduler):
        with pytest.raises(EosSchedulerRegistrationError):
            await cpsat_scheduler.unregister_experiment(db, "nonexistent")

    @pytest.mark.asyncio
    async def test_request_tasks_unregistered_experiment(self, db, cpsat_scheduler):
        with pytest.raises(EosSchedulerRegistrationError):
            await cpsat_scheduler.request_tasks(db, "nonexistent")

    async def _create_and_start_experiment(
        self, db, experiment_manager, experiment_id: str = "experiment_1", priority: int = 0
    ):
        """Helper to create and start an experiment"""
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type=EXPERIMENT_TYPE, id=experiment_id, owner="test", priority=priority)
        )
        await experiment_manager.start_experiment(db, experiment_id)

    async def _complete_task(self, db, task_manager, task_id: str, experiment_id: str = "experiment_1"):
        """Helper to mark a task as completed"""
        await task_manager.create_task(db, TaskDefinition(id=task_id, type="Noop", experiment_id=experiment_id))
        await task_manager.start_task(db, experiment_id, task_id)
        await task_manager.complete_task(db, experiment_id, task_id)

    def _verify_scheduled_task(self, task: ScheduledTask, expected: ExpectedTask):
        """Helper to verify a scheduled task matches expectations"""
        assert task.id == expected.task_id
        assert task.devices[0].lab_id == expected.lab_id
        assert task.devices[0].id == expected.device_id
        assert task.allocated_resources.status == ResourceRequestAllocationStatus.ALLOCATED

    async def _process_and_verify_tasks(
        self, db, scheduler, resource_manager, task_manager, experiment_id: str, expected_tasks: list[ExpectedTask]
    ):
        """Helper to process and verify a batch of scheduled tasks (order not enforced)"""
        await scheduler.request_tasks(db, experiment_id)
        await resource_manager.process_requests(db)
        tasks = await scheduler.request_tasks(db, experiment_id)
        print(tasks)

        tasks_by_id = {task.id: task for task in tasks}

        # Verify each expected task exists and then complete it
        for expected in expected_tasks:
            task = tasks_by_id.get(expected.task_id)
            assert task is not None, f"Expected task with id {expected.task_id} not found"
            self._verify_scheduled_task(task, expected)
            await self._complete_task(db, task_manager, expected.task_id, experiment_id)

    @pytest.mark.asyncio
    async def test_correct_schedule(
        self,
        db,
        cpsat_scheduler,
        experiment_graph,
        experiment_manager,
        task_manager,
        resource_allocation_manager,
    ):
        """Test complete experiment scheduling workflow"""
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        # Setup experiment
        await self._create_and_start_experiment(db, experiment_manager)
        await cpsat_scheduler.register_experiment("experiment_1", EXPERIMENT_TYPE, experiment_graph)

        # Define expected task scheduling sequence
        scheduling_sequence = [
            [ExpectedTask("A", "abstract_lab", "D1")],
            [ExpectedTask("B", "abstract_lab", "D2"), ExpectedTask("C", "abstract_lab", "D3")],
            [ExpectedTask("D", "abstract_lab", "D3")],
            [ExpectedTask("E", "abstract_lab", "D4"), ExpectedTask("F", "abstract_lab", "D3")],
            [ExpectedTask("G", "abstract_lab", "D5")],
        ]

        # Process each batch of tasks
        for expected_batch in scheduling_sequence:
            print("------------------")
            print(expected_batch)
            await self._process_and_verify_tasks(
                db, cpsat_scheduler, resource_allocation_manager, task_manager, "experiment_1", expected_batch
            )

        # Verify experiment completion
        assert await cpsat_scheduler.is_experiment_completed(db, "experiment_1")

        # Verify no more tasks are scheduled
        await cpsat_scheduler.request_tasks(db, "experiment_1")
        await resource_allocation_manager.process_requests(db)
        final_tasks = await cpsat_scheduler.request_tasks(db, "experiment_1")
        assert len(final_tasks) == 0

    @pytest.mark.asyncio
    async def test_multi_experiment_correct_schedule(
        self,
        db,
        cpsat_scheduler,
        experiment_graph,
        experiment_manager,
        task_manager,
        resource_allocation_manager,
    ):
        """Test experiment scheduling workflow with multiple experiments."""
        await cpsat_scheduler.update_parameters({"num_search_workers": 1, "random_seed": 40})

        # Create and start both experiments.
        await self._create_and_start_experiment(db, experiment_manager, "experiment_1", priority=1)
        await self._create_and_start_experiment(db, experiment_manager, "experiment_2", priority=0)

        # --- Phase 1: Experiment 1 only ---
        # Register experiment 1
        await cpsat_scheduler.register_experiment("experiment_1", EXPERIMENT_TYPE, experiment_graph)

        # EX1-A
        expected_tasks = [ExpectedTask("A", "abstract_lab", "D1")]
        await self._process_and_verify_tasks(
            db, cpsat_scheduler, resource_allocation_manager, task_manager, "experiment_1", expected_tasks
        )

        # EX1-B and EX1-C
        expected_tasks = [
            ExpectedTask("B", "abstract_lab", "D2"),
            ExpectedTask("C", "abstract_lab", "D3"),
        ]
        await self._process_and_verify_tasks(
            db, cpsat_scheduler, resource_allocation_manager, task_manager, "experiment_1", expected_tasks
        )

        # --- Phase 2: Experiment 1 + Experiment 2 ---
        await cpsat_scheduler.register_experiment("experiment_2", EXPERIMENT_TYPE, experiment_graph)

        # EX1-D and EX2-A
        expected_tasks_ex1 = [ExpectedTask("D", "abstract_lab", "D3")]
        expected_tasks_ex2 = [ExpectedTask("A", "abstract_lab", "D1")]
        await self._process_and_verify_tasks(
            db, cpsat_scheduler, resource_allocation_manager, task_manager, "experiment_1", expected_tasks_ex1
        )
        await self._process_and_verify_tasks(
            db, cpsat_scheduler, resource_allocation_manager, task_manager, "experiment_2", expected_tasks_ex2
        )

        # EX2-B
        expected_tasks_ex2 = [ExpectedTask("B", "abstract_lab", "D2")]
        await self._process_and_verify_tasks(
            db, cpsat_scheduler, resource_allocation_manager, task_manager, "experiment_2", expected_tasks_ex2
        )

        # EX1-E and EX2-C
        expected_tasks_ex1 = [ExpectedTask("E", "abstract_lab", "D4")]
        expected_tasks_ex2 = [ExpectedTask("C", "abstract_lab", "D3")]
        await self._process_and_verify_tasks(
            db, cpsat_scheduler, resource_allocation_manager, task_manager, "experiment_1", expected_tasks_ex1
        )
        await self._process_and_verify_tasks(
            db, cpsat_scheduler, resource_allocation_manager, task_manager, "experiment_2", expected_tasks_ex2
        )

        # EX2-D
        expected_tasks_ex2 = [ExpectedTask("D", "abstract_lab", "D3")]
        await self._process_and_verify_tasks(
            db, cpsat_scheduler, resource_allocation_manager, task_manager, "experiment_2", expected_tasks_ex2
        )

        # EX1-F and EX2-E
        expected_tasks_ex1 = [ExpectedTask("F", "abstract_lab", "D3")]
        expected_tasks_ex2 = [ExpectedTask("E", "abstract_lab", "D4")]
        await self._process_and_verify_tasks(
            db, cpsat_scheduler, resource_allocation_manager, task_manager, "experiment_1", expected_tasks_ex1
        )
        await self._process_and_verify_tasks(
            db, cpsat_scheduler, resource_allocation_manager, task_manager, "experiment_2", expected_tasks_ex2
        )

        # EX1-G and EX2-F
        expected_tasks_ex1 = [ExpectedTask("G", "abstract_lab", "D5")]
        expected_tasks_ex2 = [ExpectedTask("F", "abstract_lab", "D3")]
        await self._process_and_verify_tasks(
            db, cpsat_scheduler, resource_allocation_manager, task_manager, "experiment_1", expected_tasks_ex1
        )
        await self._process_and_verify_tasks(
            db, cpsat_scheduler, resource_allocation_manager, task_manager, "experiment_2", expected_tasks_ex2
        )

        # EX2-G
        expected_tasks_ex2 = [ExpectedTask("G", "abstract_lab", "D5")]
        await self._process_and_verify_tasks(
            db, cpsat_scheduler, resource_allocation_manager, task_manager, "experiment_2", expected_tasks_ex2
        )
