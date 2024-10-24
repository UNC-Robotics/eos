from eos.tasks.entities.task import TaskStatus, TaskOutput
from eos.tasks.exceptions import EosTaskStateError, EosTaskExistsError
from tests.fixtures import *

EXPERIMENT_ID = "water_purification"


@pytest.fixture
async def experiment_manager(configuration_manager, db_interface):
    experiment_manager = ExperimentManager(configuration_manager, db_interface)
    await experiment_manager.initialize(db_interface)
    await experiment_manager.create_experiment(EXPERIMENT_ID, "water_purification")
    return experiment_manager


@pytest.mark.parametrize("setup_lab_experiment", [("small_lab", "water_purification")], indirect=True)
class TestTaskManager:
    @pytest.mark.asyncio
    async def test_create_task(self, task_manager, experiment_manager):
        await task_manager.create_task(EXPERIMENT_ID, "mixing", "Magnetic Mixing", [])

        task = await task_manager.get_task(EXPERIMENT_ID, "mixing")
        assert task.id == "mixing"
        assert task.type == "Magnetic Mixing"

    @pytest.mark.asyncio
    async def test_create_task_nonexistent(self, task_manager, experiment_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.create_task(EXPERIMENT_ID, "nonexistent", "nonexistent", [])

    @pytest.mark.asyncio
    async def test_create_task_nonexistent_task_type(self, task_manager, experiment_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.create_task(EXPERIMENT_ID, "nonexistent_task", "Nonexistent", [])

    @pytest.mark.asyncio
    async def test_create_existing_task(self, task_manager, experiment_manager):
        await task_manager.create_task(EXPERIMENT_ID, "mixing", "Magnetic Mixing", [])

        with pytest.raises(EosTaskExistsError):
            await task_manager.create_task(EXPERIMENT_ID, "mixing", "Magnetic Mixing", [])

    @pytest.mark.asyncio
    async def test_delete_task(self, task_manager):
        await task_manager.create_task(EXPERIMENT_ID, "mixing", "Magnetic Mixing", [])

        await task_manager.delete_task(EXPERIMENT_ID, "mixing")

        assert await task_manager.get_task(EXPERIMENT_ID, "mixing") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_task(self, task_manager, experiment_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.delete_task(EXPERIMENT_ID, "nonexistent_task")

    @pytest.mark.asyncio
    async def test_get_all_tasks_by_status(self, task_manager, experiment_manager):
        await task_manager.create_task(EXPERIMENT_ID, "mixing", "Magnetic Mixing", [])
        await task_manager.create_task(EXPERIMENT_ID, "purification", "Purification", [])

        await task_manager.start_task(EXPERIMENT_ID, "mixing")
        await task_manager.complete_task(EXPERIMENT_ID, "purification")

        assert len(await task_manager.get_tasks(experiment_id=EXPERIMENT_ID, status=TaskStatus.RUNNING.value)) == 1
        assert len(await task_manager.get_tasks(experiment_id=EXPERIMENT_ID, status=TaskStatus.COMPLETED.value)) == 1

    @pytest.mark.asyncio
    async def test_set_task_status(self, task_manager, experiment_manager):
        await task_manager.create_task(EXPERIMENT_ID, "mixing", "Magnetic Mixing", [])
        task = await task_manager.get_task(EXPERIMENT_ID, "mixing")
        assert task.status == TaskStatus.CREATED

        await task_manager.start_task(EXPERIMENT_ID, "mixing")
        task = await task_manager.get_task(EXPERIMENT_ID, "mixing")
        assert task.status == TaskStatus.RUNNING

        await task_manager.complete_task(EXPERIMENT_ID, "mixing")
        task = await task_manager.get_task(EXPERIMENT_ID, "mixing")
        assert task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_set_task_status_nonexistent_task(self, task_manager, experiment_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.start_task(EXPERIMENT_ID, "nonexistent_task")

    @pytest.mark.asyncio
    async def test_start_task(self, task_manager, experiment_manager):
        await task_manager.create_task(EXPERIMENT_ID, "mixing", "Magnetic Mixing", [])

        await task_manager.start_task(EXPERIMENT_ID, "mixing")
        assert "mixing" in await experiment_manager.get_running_tasks(EXPERIMENT_ID)

    @pytest.mark.asyncio
    async def test_start_task_nonexistent_experiment(self, task_manager, experiment_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.start_task(EXPERIMENT_ID, "nonexistent_task")

    @pytest.mark.asyncio
    async def test_complete_task(self, task_manager, experiment_manager):
        await task_manager.create_task(EXPERIMENT_ID, "mixing", "Magnetic Mixing", [])
        await task_manager.start_task(EXPERIMENT_ID, "mixing")
        await task_manager.complete_task(EXPERIMENT_ID, "mixing")
        assert "mixing" not in await experiment_manager.get_running_tasks(EXPERIMENT_ID)
        assert "mixing" in await experiment_manager.get_completed_tasks(EXPERIMENT_ID)

    @pytest.mark.asyncio
    async def test_complete_task_nonexistent_experiment(self, task_manager, experiment_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.complete_task(EXPERIMENT_ID, "nonexistent_task")

    @pytest.mark.asyncio
    async def test_add_task_output(self, task_manager):
        await task_manager.create_task(EXPERIMENT_ID, "mixing", "Magnetic Mixing", [])

        task_output = TaskOutput(
            experiment_id=EXPERIMENT_ID,
            task_id="mixing",
            parameters={"x": 5},
            file_names=["file"],
        )
        await task_manager.add_task_output(EXPERIMENT_ID, "mixing", task_output)
        task_manager.add_task_output_file(EXPERIMENT_ID, "mixing", "file", b"file_data")

        output = await task_manager.get_task_output(experiment_id=EXPERIMENT_ID, task_id="mixing")
        assert output.parameters == {"x": 5}
        assert output.file_names == ["file"]

        output_file = task_manager.get_task_output_file(experiment_id=EXPERIMENT_ID, task_id="mixing", file_name="file")
        assert output_file == b"file_data"
