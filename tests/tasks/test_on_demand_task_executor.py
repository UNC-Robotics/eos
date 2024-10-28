import asyncio

from eos.configuration.entities.task import TaskConfig
from eos.tasks.entities.task import TaskStatus, TaskDefinition
from tests.fixtures import *


@pytest.mark.parametrize(
    "setup_lab_experiment",
    [("small_lab", "water_purification")],
    indirect=True,
)
class TestOnDemandTaskExecutor:
    @pytest.mark.asyncio
    async def test_execute_on_demand_task(self, on_demand_task_executor, task_manager):
        task_config = TaskConfig(
            id="mixing",
            type="Magnetic Mixing",
            desc="Mixing task",
            parameters={"time": 5},
        )
        task_definition = TaskDefinition.from_config(task_config, "on_demand")

        on_demand_task_executor.submit_task(task_definition)
        await on_demand_task_executor.process_tasks()

        while True:
            await on_demand_task_executor.process_tasks()
            task = await task_manager.get_task("on_demand", "mixing")
            if task and task.status == TaskStatus.COMPLETED:
                break
            await asyncio.sleep(0.5)

        assert task.status == TaskStatus.COMPLETED
        assert task.output.parameters["mixing_time"] == 5

    @pytest.mark.asyncio
    async def test_on_demand_task_output(self, on_demand_task_executor, task_manager):
        task_config = TaskConfig(
            id="file_gen",
            type="File Generation",
            desc="File generation task",
            parameters={"content_length": 32},
        )
        task_definition = TaskDefinition.from_config(task_config, "on_demand")

        on_demand_task_executor.submit_task(task_definition)
        await on_demand_task_executor.process_tasks()

        while True:
            await on_demand_task_executor.process_tasks()
            task = await task_manager.get_task("on_demand", "file_gen")
            if task and task.status == TaskStatus.COMPLETED:
                break
            await asyncio.sleep(0.5)

        assert task.status == TaskStatus.COMPLETED
        file = task_manager.get_task_output_file("on_demand", "file_gen", "file.txt")

        assert len(file) == 32

    @pytest.mark.asyncio
    async def test_request_task_cancellation(self, on_demand_task_executor, task_manager):
        task_config = TaskConfig(
            id="sleep",
            type="Sleep",
            desc="Sleeping task",
            parameters={"time": 20},
        )
        task_definition = TaskDefinition.from_config(task_config, "on_demand")

        on_demand_task_executor.submit_task(task_definition)
        await on_demand_task_executor.process_tasks()

        iterations = 0
        while True:
            await on_demand_task_executor.process_tasks()
            task = await task_manager.get_task("on_demand", "sleep")
            if task and task.status != TaskStatus.RUNNING:
                break
            await asyncio.sleep(0.5)
            iterations += 1

            if iterations > 5:
                await on_demand_task_executor.request_task_cancellation("sleep")

            if iterations > 40:
                raise Exception("Task did not cancel in time")

        task = await task_manager.get_task("on_demand", "sleep")
        assert task.status == TaskStatus.CANCELLED
