from typing import NamedTuple

from eos.experiments.entities.experiment import ExperimentDefinition
from eos.resource_allocation.entities.resource_request import ResourceRequestAllocationStatus
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.scheduling.exceptions import EosSchedulerRegistrationError
from eos.tasks.entities.task import TaskDefinition
from tests.fixtures import *


class ExpectedTask(NamedTuple):
    """Helper class to define expected task scheduling results"""

    task_id: str
    lab_id: str
    device_id: str


@pytest.fixture()
def experiment_graph(configuration_manager):
    experiment = configuration_manager.experiments["abstract_experiment"]
    return ExperimentGraph(experiment)


@pytest.mark.parametrize("setup_lab_experiment", [("abstract_lab", "abstract_experiment")], indirect=True)
class TestGreedyScheduler:

    @pytest.mark.asyncio
    async def test_register_experiment(self, greedy_scheduler, experiment_graph):
        await greedy_scheduler.register_experiment("exp1", "abstract_experiment", experiment_graph)
        assert greedy_scheduler._registered_experiments["exp1"] == (
            "abstract_experiment",
            experiment_graph,
        )

    @pytest.mark.asyncio
    async def test_register_invalid_experiment(self, greedy_scheduler, experiment_graph):
        with pytest.raises(EosSchedulerRegistrationError):
            await greedy_scheduler.register_experiment("exp1", "invalid_type", experiment_graph)

    @pytest.mark.asyncio
    async def test_unregister_experiment(self, db, greedy_scheduler, experiment_graph, setup_lab_experiment):
        # Register experiment
        await greedy_scheduler.register_experiment("exp1", "abstract_experiment", experiment_graph)
        assert "exp1" in greedy_scheduler._registered_experiments

        # Unregister experiment
        await greedy_scheduler.unregister_experiment(db, "exp1")
        assert "exp1" not in greedy_scheduler._registered_experiments

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_experiment(self, db, greedy_scheduler):
        with pytest.raises(EosSchedulerRegistrationError):
            await greedy_scheduler.unregister_experiment(db, "nonexistent")

    @pytest.mark.asyncio
    async def test_request_tasks_unregistered_experiment(self, db, greedy_scheduler):
        with pytest.raises(EosSchedulerRegistrationError):
            await greedy_scheduler.request_tasks(db, "nonexistent")

    async def _create_and_start_experiment(self, db, experiment_manager, experiment_id: str = "experiment_1"):
        """Helper to create and start an experiment"""
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type="abstract_experiment", id=experiment_id, owner="test")
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
        """Helper to process and verify a batch of scheduled tasks"""
        # Request initial scheduling (submits resource requests)
        await scheduler.request_tasks(db, experiment_id)
        # Process resource allocation
        await resource_manager.process_requests(db)
        # Get scheduled tasks
        tasks = await scheduler.request_tasks(db, experiment_id)

        # Verify results
        assert len(tasks) == len(expected_tasks)
        for task, expected in zip(tasks, expected_tasks, strict=False):
            self._verify_scheduled_task(task, expected)
            await self._complete_task(db, task_manager, expected.task_id, experiment_id)

    @pytest.mark.asyncio
    async def test_correct_schedule(
        self,
        db,
        greedy_scheduler,
        experiment_graph,
        experiment_manager,
        task_manager,
        resource_allocation_manager,
    ):
        """Test complete experiment scheduling workflow"""
        # Setup experiment
        await self._create_and_start_experiment(db, experiment_manager)
        await greedy_scheduler.register_experiment("experiment_1", "abstract_experiment", experiment_graph)

        # Define expected task scheduling sequence
        scheduling_sequence = [
            # First batch - Task A
            [ExpectedTask("A", "abstract_lab", "D2")],
            # Second batch - Tasks B and C (parallel)
            [ExpectedTask("B", "abstract_lab", "D1"), ExpectedTask("C", "abstract_lab", "D3")],
            # Third batch - Tasks D, E, and F (parallel)
            [
                ExpectedTask("D", "abstract_lab", "D1"),
                ExpectedTask("E", "abstract_lab", "D3"),
                ExpectedTask("F", "abstract_lab", "D2"),
            ],
            # Fourth batch - Task G
            [ExpectedTask("G", "abstract_lab", "D5")],
            # Fifth batch - Task H
            [ExpectedTask("H", "abstract_lab", "D6")],
        ]

        # Process each batch of tasks
        for expected_batch in scheduling_sequence:
            await self._process_and_verify_tasks(
                db, greedy_scheduler, resource_allocation_manager, task_manager, "experiment_1", expected_batch
            )

        # Verify experiment completion
        assert await greedy_scheduler.is_experiment_completed(db, "experiment_1")

        # Verify no more tasks are scheduled
        await greedy_scheduler.request_tasks(db, "experiment_1")
        await resource_allocation_manager.process_requests(db)
        final_tasks = await greedy_scheduler.request_tasks(db, "experiment_1")
        assert len(final_tasks) == 0
