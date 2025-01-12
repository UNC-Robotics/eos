import asyncio
from asyncio import CancelledError

from eos.configuration.entities.task import TaskConfig, TaskDeviceConfig
from eos.experiments.entities.experiment import ExperimentDefinition
from eos.tasks.entities.task import TaskDefinition
from tests.fixtures import *


@pytest.mark.parametrize(
    "setup_lab_experiment",
    [("small_lab", "water_purification")],
    indirect=True,
)
class TestTaskExecutor:
    async def _setup_experiment(self, db, experiment_manager):
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type="water_purification", id="water_purification", owner="test")
        )

    async def _process_until_done(self, task_executor, future, timeout_seconds=10):
        """Helper to process tasks until completion or timeout."""
        timeout = asyncio.create_task(asyncio.sleep(timeout_seconds))
        while not future.done() and not timeout.done():
            await task_executor.process_tasks()
            await asyncio.sleep(0.1)

        if timeout.done() and not future.done():
            raise TimeoutError(f"Task processing timed out after {timeout_seconds} seconds")

    @pytest.mark.asyncio
    async def test_request_task_execution(
        self,
        task_executor,
        experiment_manager,
        experiment_graph,
        db_interface,
    ):
        async with db_interface.get_async_session() as db:
            await self._setup_experiment(db, experiment_manager)

        task_config = experiment_graph.get_task_config("mixing")
        task_config.parameters["time"] = 5
        task_config.devices = [TaskDeviceConfig(lab_id="small_lab", id="magnetic_mixer")]

        # Test multiple executions
        for task_id in ["mixing", "mixing2", "mixing3"]:
            task_definition = TaskDefinition.from_config(task_config, "water_purification")
            task_definition.id = task_id

            future = asyncio.create_task(task_executor.request_task_execution(task_definition))
            await self._process_until_done(task_executor, future)

            task_output_parameters, _, _ = await future
            assert task_output_parameters["mixing_time"] == 5

    @pytest.mark.asyncio
    async def test_cancel_task(self, task_executor, experiment_manager, db_interface):
        async with db_interface.get_async_session() as db:
            await self._setup_experiment(db, experiment_manager)

        sleep_config = TaskConfig(
            id="sleep_task",
            type="Sleep",
            devices=[TaskDeviceConfig(lab_id="small_lab", id="general_computer")],
            parameters={"time": 5},
        )
        task_definition = TaskDefinition.from_config(sleep_config, "water_purification")

        future = asyncio.create_task(task_executor.request_task_execution(task_definition))

        # Give task time to start
        for _ in range(5):
            await task_executor.process_tasks()
            await asyncio.sleep(0.1)

        await task_executor.cancel_task(task_definition.experiment_id, task_definition.id)
        await self._process_until_done(task_executor, future, timeout_seconds=2)

        with pytest.raises(CancelledError):
            await future

        assert not task_executor._pending_tasks
