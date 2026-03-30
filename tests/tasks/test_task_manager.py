from eos.protocols.entities.protocol_run import ProtocolRunSubmission
from eos.tasks.entities.task import TaskStatus, TaskSubmission
from eos.tasks.exceptions import EosTaskStateError, EosTaskExistsError
from tests.fixtures import *

PROTOCOL = "water_purification"


@pytest.fixture
async def protocol_run_manager(db, configuration_manager):
    protocol_run_manager = ProtocolRunManager(configuration_manager)
    await protocol_run_manager.create_protocol_run(
        db, ProtocolRunSubmission(type=PROTOCOL, name=PROTOCOL, owner="test")
    )
    return protocol_run_manager


@pytest.mark.parametrize("setup_lab_protocol", [("small_lab", "water_purification")], indirect=True)
class TestTaskManager:
    @pytest.mark.asyncio
    async def test_create_task(self, db, task_manager, protocol_run_manager):
        await task_manager.create_task(
            db, TaskSubmission(name="mixing", type="Magnetic Mixing", protocol_run_name=PROTOCOL)
        )

        task = await task_manager.get_task(db, PROTOCOL, "mixing")
        assert task.name == "mixing"
        assert task.type == "Magnetic Mixing"

    @pytest.mark.asyncio
    async def test_create_task_nonexistent_type(self, db, task_manager, protocol_run_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.create_task(
                db, TaskSubmission(name="nonexistent_task", type="Nonexistent", protocol_run_name=PROTOCOL)
            )

    @pytest.mark.asyncio
    async def test_create_existing_task(self, db, task_manager, protocol_run_manager):
        task_def = TaskSubmission(name="mixing", type="Magnetic Mixing", protocol_run_name=PROTOCOL)
        await task_manager.create_task(db, task_def)

        with pytest.raises(EosTaskExistsError):
            await task_manager.create_task(db, task_def)

    @pytest.mark.asyncio
    async def test_delete_task(self, db, task_manager, protocol_run_manager):
        await task_manager.create_task(
            db, TaskSubmission(name="mixing", type="Magnetic Mixing", protocol_run_name=PROTOCOL)
        )
        await task_manager.delete_task(db, PROTOCOL, "mixing")
        assert await task_manager.get_task(db, PROTOCOL, "mixing") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_task(self, db, task_manager, protocol_run_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.create_task(
                db, TaskSubmission(name="nonexistent_task", type="Nonexistent", protocol_run_name=PROTOCOL)
            )
            await task_manager.delete_task(db, PROTOCOL, "nonexistent_task")

    @pytest.mark.asyncio
    async def test_get_all_tasks_by_status(self, db, task_manager, protocol_run_manager):
        await task_manager.create_task(
            db, TaskSubmission(name="mixing", type="Magnetic Mixing", protocol_run_name=PROTOCOL)
        )
        await task_manager.create_task(
            db, TaskSubmission(name="purification", type="Purification", protocol_run_name=PROTOCOL)
        )

        await task_manager.start_task(db, PROTOCOL, "mixing")
        await task_manager.complete_task(db, PROTOCOL, "purification")

        assert len(await task_manager.get_tasks(db, protocol_run_name=PROTOCOL, status=TaskStatus.RUNNING.value)) == 1
        assert len(await task_manager.get_tasks(db, protocol_run_name=PROTOCOL, status=TaskStatus.COMPLETED.value)) == 1

    @pytest.mark.asyncio
    async def test_set_task_status(self, db, task_manager, protocol_run_manager):
        await task_manager.create_task(
            db, TaskSubmission(name="mixing", type="Magnetic Mixing", protocol_run_name=PROTOCOL)
        )
        task = await task_manager.get_task(db, PROTOCOL, "mixing")
        assert task.status == TaskStatus.CREATED

        await task_manager.start_task(db, PROTOCOL, "mixing")
        task = await task_manager.get_task(db, PROTOCOL, "mixing")
        assert task.status == TaskStatus.RUNNING

        await task_manager.complete_task(db, PROTOCOL, "mixing")
        task = await task_manager.get_task(db, PROTOCOL, "mixing")
        assert task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_set_task_status_nonexistent_task(self, db, task_manager, protocol_run_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.start_task(db, PROTOCOL, "nonexistent_task")

    @pytest.mark.asyncio
    async def test_start_task(self, db, task_manager, protocol_run_manager):
        await task_manager.create_task(
            db, TaskSubmission(name="mixing", type="Magnetic Mixing", protocol_run_name=PROTOCOL)
        )

        await task_manager.start_task(db, PROTOCOL, "mixing")
        assert "mixing" in await protocol_run_manager.get_running_tasks(db, PROTOCOL)

    @pytest.mark.asyncio
    async def test_start_task_nonexistent_protocol_run(self, db, task_manager, protocol_run_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.start_task(db, PROTOCOL, "nonexistent_task")

    @pytest.mark.asyncio
    async def test_complete_task(self, db, task_manager, protocol_run_manager):
        await task_manager.create_task(
            db, TaskSubmission(name="mixing", type="Magnetic Mixing", protocol_run_name=PROTOCOL)
        )
        await task_manager.start_task(db, PROTOCOL, "mixing")
        await task_manager.complete_task(db, PROTOCOL, "mixing")
        assert "mixing" not in await protocol_run_manager.get_running_tasks(db, PROTOCOL)
        assert "mixing" in await protocol_run_manager.get_completed_tasks(db, PROTOCOL)

    @pytest.mark.asyncio
    async def test_complete_task_nonexistent_protocol_run(self, db, task_manager, protocol_run_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.complete_task(db, PROTOCOL, "nonexistent_task")

    @pytest.mark.asyncio
    async def test_add_task_output(self, db, task_manager, protocol_run_manager):
        await task_manager.create_task(
            db, TaskSubmission(name="mixing", type="Magnetic Mixing", protocol_run_name=PROTOCOL)
        )

        task_output_parameters = {"x": 5}
        task_output_file_names = ["file"]

        await task_manager.add_task_output(db, PROTOCOL, "mixing", task_output_parameters, None, task_output_file_names)
        await task_manager.add_task_output_file(PROTOCOL, "mixing", "file", b"file_data")

        task = await task_manager.get_task(db, PROTOCOL, "mixing")
        assert task.output_parameters == {"x": 5}
        assert task.output_file_names == ["file"]

        output_file = await task_manager.get_task_output_file(
            protocol_run_name=PROTOCOL, task_name="mixing", file_name="file"
        )
        assert output_file == b"file_data"
