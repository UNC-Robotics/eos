import asyncio
from unittest.mock import patch

from eos.protocols.entities.protocol_run import ProtocolRunStatus, ProtocolRunSubmission
from eos.protocols.exceptions import EosProtocolRunExecutionError
from eos.protocols.protocol_executor import ProtocolExecutor
from eos.tasks.base_task import BaseTask
from tests.fixtures import *

LAB_NAME = "small_lab"
PROTOCOL = "water_purification"
PROTOCOL_RUN_NAME = "water_purification_#1"

PARAMETERS = {
    "mixing": {
        "speed": 50,
        "time": 120,
    },
    "evaporation": {
        "evaporation_temperature": 120,
        "evaporation_rotation_speed": 200,
        "evaporation_sparging_flow": 5,
    },
}


@pytest.mark.parametrize(
    "setup_lab_protocol",
    [(LAB_NAME, PROTOCOL)],
    indirect=True,
)
class TestProtocolExecutor:
    @pytest.fixture
    def protocol_executor(
        self,
        protocol_run_manager,
        task_manager,
        task_executor,
        greedy_scheduler,
        protocol_graph,
        db_interface,
    ):
        return ProtocolExecutor(
            protocol_run_submission=ProtocolRunSubmission(
                name=PROTOCOL_RUN_NAME, type=PROTOCOL, owner="test", parameters=PARAMETERS
            ),
            protocol_graph=protocol_graph,
            protocol_run_manager=protocol_run_manager,
            task_manager=task_manager,
            task_executor=task_executor,
            scheduler=greedy_scheduler,
            db_interface=db_interface,
        )

    async def test_start_protocol_run(self, db, protocol_executor, protocol_run_manager):
        await protocol_executor.start_protocol_run(db)

        protocol_run = await protocol_run_manager.get_protocol_run(db, PROTOCOL_RUN_NAME)
        assert protocol_run is not None
        assert protocol_run.name == PROTOCOL_RUN_NAME
        assert protocol_run.status == ProtocolRunStatus.RUNNING

    async def test_task_output_registration(
        self, protocol_executor, allocation_manager, task_executor, task_manager, db_interface
    ):
        async with db_interface.get_async_session() as db:
            await protocol_executor.start_protocol_run(db)

        protocol_run_completed = False
        while not protocol_run_completed:
            async with db_interface.get_async_session() as db:
                protocol_run_completed = await protocol_executor.progress_protocol_run(db)
            await task_executor.process_tasks()
            await asyncio.sleep(0.1)

        async with db_interface.get_async_session() as db:
            task = await task_manager.get_task(db, PROTOCOL_RUN_NAME, "mixing")
        assert task.output_parameters["mixing_time"] == PARAMETERS["mixing"]["time"]

    async def test_resolve_input_parameter_references_and_dynamic_parameters(
        self, protocol_executor, allocation_manager, task_executor, task_manager, db_interface
    ):
        async with db_interface.get_async_session() as db:
            await protocol_executor.start_protocol_run(db)

        protocol_run_completed = False
        while not protocol_run_completed:
            async with db_interface.get_async_session() as db:
                protocol_run_completed = await protocol_executor.progress_protocol_run(db)
            await task_executor.process_tasks()
            await asyncio.sleep(0.1)

        async with db_interface.get_async_session() as db:
            mixing_task = await task_manager.get_task(db, PROTOCOL_RUN_NAME, "mixing")
            evaporation_task = await task_manager.get_task(db, PROTOCOL_RUN_NAME, "evaporation")

        # Check the dynamic parameter for input mixing time
        assert mixing_task.input_parameters["speed"] == PARAMETERS["mixing"]["speed"]
        assert mixing_task.input_parameters["time"] == PARAMETERS["mixing"]["time"]

        # Check that the output parameter mixing time was assigned to the input parameter evaporation time
        assert evaporation_task.input_parameters["evaporation_time"] == mixing_task.output_parameters["mixing_time"]

    @pytest.mark.parametrize(
        "protocol_run_status",
        [
            ProtocolRunStatus.COMPLETED,
            ProtocolRunStatus.SUSPENDED,
            ProtocolRunStatus.CANCELLED,
            ProtocolRunStatus.FAILED,
            ProtocolRunStatus.RUNNING,
        ],
    )
    async def test_handle_existing_protocol_run(self, db, protocol_executor, protocol_run_manager, protocol_run_status):
        await protocol_run_manager.create_protocol_run(db, protocol_executor._protocol_run_submission)
        await protocol_run_manager._set_protocol_run_status(db, PROTOCOL_RUN_NAME, protocol_run_status)

        protocol_executor._protocol_run_submission.resume = False
        with patch.object(protocol_executor, "_resume_protocol_run") as mock_resume:
            if protocol_run_status in [
                ProtocolRunStatus.COMPLETED,
                ProtocolRunStatus.SUSPENDED,
                ProtocolRunStatus.CANCELLED,
                ProtocolRunStatus.FAILED,
            ]:
                with pytest.raises(EosProtocolRunExecutionError) as exc_info:
                    protocol_run = await protocol_run_manager.get_protocol_run(db, PROTOCOL_RUN_NAME)
                    await protocol_executor._handle_existing_protocol_run(db, protocol_run)
                assert protocol_run_status.value in str(exc_info.value)
                mock_resume.assert_not_called()
            else:
                protocol_run = await protocol_run_manager.get_protocol_run(db, PROTOCOL_RUN_NAME)
                await protocol_executor._handle_existing_protocol_run(db, protocol_run)
                mock_resume.assert_not_called()

        protocol_executor._protocol_run_submission.resume = True
        with patch.object(protocol_executor, "_resume_protocol_run") as mock_resume:
            protocol_run = await protocol_run_manager.get_protocol_run(db, PROTOCOL_RUN_NAME)
            await protocol_executor._handle_existing_protocol_run(db, protocol_run)
            mock_resume.assert_called_once()

        assert protocol_executor._protocol_run_status == protocol_run_status

    async def test_failed_task_marks_protocol_run_failed_in_db(
        self, protocol_executor, protocol_run_manager, task_executor, task_manager, db_interface, configuration_manager
    ):
        """When a task fails, the protocol run should be marked FAILED in the database."""
        async with db_interface.get_async_session() as db:
            await protocol_executor.start_protocol_run(db)

        class FailingTask(BaseTask):
            async def _execute(self, devices, parameters, resources):
                raise RuntimeError("Simulated task failure")

        task_registry = configuration_manager.tasks
        with (
            patch.dict(task_registry.plugin_types, {"Magnetic Mixing": FailingTask}),
            pytest.raises(EosProtocolRunExecutionError),
        ):
            while True:
                async with db_interface.get_async_session() as db:
                    await protocol_executor.progress_protocol_run(db)
                await task_executor.process_tasks()
                await asyncio.sleep(0.1)

        async with db_interface.get_async_session() as db:
            protocol_run = await protocol_run_manager.get_protocol_run(db, PROTOCOL_RUN_NAME)
            assert protocol_run.status == ProtocolRunStatus.FAILED
            assert protocol_run.error_message is not None
