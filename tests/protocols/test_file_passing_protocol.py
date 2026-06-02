import asyncio

from eos.protocols.entities.protocol_run import ProtocolRunSubmission
from eos.protocols.protocol_executor import ProtocolExecutor
from eos.tasks.base_task import build_task_output_file_path
from tests.fixtures import *

LAB_NAME = "small_lab"
PROTOCOL = "file_passing"
PROTOCOL_RUN_NAME = "file_passing_#1"


@pytest.mark.parametrize("setup_lab_protocol", [(LAB_NAME, PROTOCOL)], indirect=True)
class TestFilePassingProtocol:
    @pytest.fixture
    def protocol_executor(
        self, protocol_run_manager, task_manager, task_executor, greedy_scheduler, protocol_graph, db_interface
    ):
        return ProtocolExecutor(
            protocol_run_submission=ProtocolRunSubmission(name=PROTOCOL_RUN_NAME, type=PROTOCOL, owner="test"),
            protocol_graph=protocol_graph,
            protocol_run_manager=protocol_run_manager,
            task_manager=task_manager,
            task_executor=task_executor,
            scheduler=greedy_scheduler,
            db_interface=db_interface,
        )

    async def test_output_file_is_referenced_and_read_by_next_task(
        self, protocol_executor, allocation_manager, task_executor, task_manager, file_db_interface, db_interface
    ):
        async with db_interface.get_async_session() as db:
            await protocol_executor.start_protocol_run(db)

        completed = False
        for _ in range(200):
            async with db_interface.get_async_session() as db:
                completed = await protocol_executor.progress_protocol_run(db)
            await task_executor.process_tasks()
            if completed:
                break
            await asyncio.sleep(0.1)
        assert completed, "Protocol run did not complete in time"

        async with db_interface.get_async_session() as db:
            gen = await task_manager.get_task(db, PROTOCOL_RUN_NAME, "gen")
            consume = await task_manager.get_task(db, PROTOCOL_RUN_NAME, "consume")

        # The producer's file was uploaded by the worker; only its name is recorded.
        assert gen.output_file_names == ["file.txt"]

        # The file actually exists in SeaweedFS at the conventional key.
        key = build_task_output_file_path(PROTOCOL_RUN_NAME, "gen", "file.txt")
        assert len(await file_db_interface.get_file(key)) == 10

        # The consumer's reference resolved to that key and the task read the file's contents.
        assert consume.input_files == {"input": key}
        assert consume.output_parameters["length"] == 10
