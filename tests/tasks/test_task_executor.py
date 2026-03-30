import asyncio
from asyncio import CancelledError

from eos.configuration.entities.task_def import TaskDef, DeviceAssignmentDef
from eos.protocols.entities.protocol_run import ProtocolRunSubmission
from eos.scheduling.entities.scheduled_task import ScheduledTask
from eos.tasks.entities.task import TaskSubmission
from tests.fixtures import *


@pytest.mark.parametrize(
    "setup_lab_protocol",
    [("small_lab", "water_purification")],
    indirect=True,
)
class TestTaskExecutor:
    async def _setup_protocol_run(self, db, protocol_run_manager):
        await protocol_run_manager.create_protocol_run(
            db, ProtocolRunSubmission(type="water_purification", name="water_purification", owner="test")
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
        protocol_run_manager,
        protocol_graph,
        db_interface,
    ):
        async with db_interface.get_async_session() as db:
            await self._setup_protocol_run(db, protocol_run_manager)

        task = protocol_graph.get_task("mixing")
        task.parameters["time"] = 5
        devices = {"magnetic_mixer": DeviceAssignmentDef(lab_name="small_lab", name="magnetic_mixer")}
        task.devices = devices

        # Test multiple executions
        for task_name in ["mixing", "mixing2", "mixing3"]:
            task_submission = TaskSubmission.from_def(task, "water_purification")
            task_submission.name = task_name

            scheduled_task = ScheduledTask(
                name=task_name,
                protocol_run_name="water_purification",
                devices=devices,
                resources={},
            )

            future = asyncio.create_task(task_executor.request_task_execution(task_submission, scheduled_task))
            await self._process_until_done(task_executor, future)

            task_output_parameters, _, _ = await future
            assert task_output_parameters["mixing_time"] == 5

    @pytest.mark.asyncio
    async def test_cancel_task(self, task_executor, protocol_run_manager, db_interface):
        async with db_interface.get_async_session() as db:
            await self._setup_protocol_run(db, protocol_run_manager)

        devices = {"device_1": DeviceAssignmentDef(lab_name="small_lab", name="general_computer")}
        sleep_config = TaskDef(
            name="sleep_task",
            type="Sleep",
            devices=devices,
            parameters={"time": 5},
        )
        task_submission = TaskSubmission.from_def(sleep_config, "water_purification")

        scheduled_task = ScheduledTask(
            name="sleep_task",
            protocol_run_name="water_purification",
            devices=devices,
            resources={},
        )

        future = asyncio.create_task(task_executor.request_task_execution(task_submission, scheduled_task))

        # Give task time to start
        for _ in range(5):
            await task_executor.process_tasks()
            await asyncio.sleep(0.1)

        await task_executor.cancel_task(task_submission.protocol_run_name, task_submission.name)
        await self._process_until_done(task_executor, future, timeout_seconds=2)

        with pytest.raises(CancelledError):
            await future

        assert not task_executor._pending_tasks
