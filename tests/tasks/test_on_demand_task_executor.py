import asyncio

from eos.configuration.entities.task_def import TaskDef, DeviceAssignmentDef
from eos.tasks.entities.task import TaskStatus, TaskSubmission
from tests.fixtures import *


@pytest.mark.parametrize(
    "setup_lab_experiment",
    [("small_lab", "water_purification")],
    indirect=True,
)
class TestOnDemandTaskExecutor:
    @pytest.mark.asyncio
    async def test_execute_on_demand_task(self, db, on_demand_task_executor, task_executor, task_manager):
        task = TaskDef(
            name="mixing",
            type="Magnetic Mixing",
            desc="Mixing task",
            devices={"magnetic_mixer": DeviceAssignmentDef(lab_name="small_lab", name="magnetic_mixer")},
            parameters={"time": 5},
        )
        task_submission = TaskSubmission.from_def(task, None)

        await on_demand_task_executor.submit_task(db, task_submission)
        await on_demand_task_executor.process_tasks()
        await task_executor.process_tasks()

        while True:
            await on_demand_task_executor.process_tasks()
            await task_executor.process_tasks()
            task = await task_manager.get_task(db, None, "mixing")
            if task and task.status == TaskStatus.COMPLETED:
                break
            await asyncio.sleep(0.5)

        assert task.status == TaskStatus.COMPLETED
        assert task.output_parameters["mixing_time"] == 5

    @pytest.mark.asyncio
    async def test_on_demand_task_output(self, db, on_demand_task_executor, task_executor, task_manager):
        task = TaskDef(
            name="file_gen",
            type="File Generation",
            desc="File generation task",
            parameters={"content_length": 32},
        )
        task_submission = TaskSubmission.from_def(task, None)

        await on_demand_task_executor.submit_task(db, task_submission)

        while True:
            await on_demand_task_executor.process_tasks()
            await task_executor.process_tasks()
            task = await task_manager.get_task(db, None, "file_gen")
            if task and task.status == TaskStatus.COMPLETED:
                break
            await asyncio.sleep(0.5)

        assert task.status == TaskStatus.COMPLETED
        file = task_manager.get_task_output_file(None, "file_gen", "file.txt")

        assert len(file) == 32

    @pytest.mark.asyncio
    async def test_request_task_cancellation(self, db, on_demand_task_executor, task_executor, task_manager):
        task = TaskDef(
            name="sleep",
            type="Sleep",
            desc="Sleeping task",
            parameters={"time": 20},
        )
        task_submission = TaskSubmission.from_def(task, None)

        await on_demand_task_executor.submit_task(db, task_submission)

        # First wait for RUNNING state
        iterations = 0
        while True:
            await on_demand_task_executor.process_tasks()
            await task_executor.process_tasks()
            task = await task_manager.get_task(db, None, "sleep")
            if task and task.status == TaskStatus.RUNNING:
                break
            await asyncio.sleep(0.5)
            iterations += 1
            if iterations > 20:
                raise Exception("Task never reached RUNNING state")

        # Then test cancellation
        await on_demand_task_executor.cancel_task("sleep")

        iterations = 0
        while True:
            await on_demand_task_executor.process_tasks()
            await task_executor.process_tasks()
            task = await task_manager.get_task(db, None, "sleep")
            if task and task.status == TaskStatus.CANCELLED:
                break
            await asyncio.sleep(0.5)
            iterations += 1
            if iterations > 20:
                raise Exception("Task did not cancel in time")

        assert task.status == TaskStatus.CANCELLED
