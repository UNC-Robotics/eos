from eos.experiments.entities.experiment import ExperimentDefinition
from eos.tasks.entities.task import TaskStatus, TaskDefinition
from eos.tasks.exceptions import EosTaskStateError, EosTaskExistsError
from tests.fixtures import *

EXPERIMENT_TYPE = "water_purification"


@pytest.fixture
async def experiment_manager(db, configuration_manager):
    experiment_manager = ExperimentManager(configuration_manager)
    await experiment_manager.create_experiment(
        db, ExperimentDefinition(type=EXPERIMENT_TYPE, id=EXPERIMENT_TYPE, owner="test")
    )
    return experiment_manager


@pytest.mark.parametrize("setup_lab_experiment", [("small_lab", "water_purification")], indirect=True)
class TestTaskManager:
    @pytest.mark.asyncio
    async def test_create_task(self, db, task_manager, experiment_manager):
        await task_manager.create_task(
            db, TaskDefinition(id="mixing", type="Magnetic Mixing", experiment_id=EXPERIMENT_TYPE)
        )

        task = await task_manager.get_task(db, EXPERIMENT_TYPE, "mixing")
        assert task.id == "mixing"
        assert task.type == "Magnetic Mixing"

    @pytest.mark.asyncio
    async def test_create_task_nonexistent_type(self, db, task_manager, experiment_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.create_task(
                db, TaskDefinition(id="nonexistent_task", type="Nonexistent", experiment_id=EXPERIMENT_TYPE)
            )

    @pytest.mark.asyncio
    async def test_create_existing_task(self, db, task_manager, experiment_manager):
        task_def = TaskDefinition(id="mixing", type="Magnetic Mixing", experiment_id=EXPERIMENT_TYPE)
        await task_manager.create_task(db, task_def)

        with pytest.raises(EosTaskExistsError):
            await task_manager.create_task(db, task_def)

    @pytest.mark.asyncio
    async def test_delete_task(self, db, task_manager):
        await task_manager.create_task(
            db, TaskDefinition(id="mixing", type="Magnetic Mixing", experiment_id=EXPERIMENT_TYPE)
        )
        await task_manager.delete_task(db, EXPERIMENT_TYPE, "mixing")
        assert await task_manager.get_task(db, EXPERIMENT_TYPE, "mixing") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_task(self, db, task_manager, experiment_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.create_task(
                db, TaskDefinition(id="nonexistent_task", type="Nonexistent", experiment_id=EXPERIMENT_TYPE)
            )
            await task_manager.delete_task(db, EXPERIMENT_TYPE, "nonexistent_task")

    @pytest.mark.asyncio
    async def test_get_all_tasks_by_status(self, db, task_manager, experiment_manager):
        await task_manager.create_task(
            db, TaskDefinition(id="mixing", type="Magnetic Mixing", experiment_id=EXPERIMENT_TYPE)
        )
        await task_manager.create_task(
            db, TaskDefinition(id="purification", type="Purification", experiment_id=EXPERIMENT_TYPE)
        )

        await task_manager.start_task(db, EXPERIMENT_TYPE, "mixing")
        await task_manager.complete_task(db, EXPERIMENT_TYPE, "purification")

        assert (
            len(await task_manager.get_tasks(db, experiment_id=EXPERIMENT_TYPE, status=TaskStatus.RUNNING.value)) == 1
        )
        assert (
            len(await task_manager.get_tasks(db, experiment_id=EXPERIMENT_TYPE, status=TaskStatus.COMPLETED.value)) == 1
        )

    @pytest.mark.asyncio
    async def test_set_task_status(self, db, task_manager, experiment_manager):
        await task_manager.create_task(
            db, TaskDefinition(id="mixing", type="Magnetic Mixing", experiment_id=EXPERIMENT_TYPE)
        )
        task = await task_manager.get_task(db, EXPERIMENT_TYPE, "mixing")
        assert task.status == TaskStatus.CREATED

        await task_manager.start_task(db, EXPERIMENT_TYPE, "mixing")
        task = await task_manager.get_task(db, EXPERIMENT_TYPE, "mixing")
        assert task.status == TaskStatus.RUNNING

        await task_manager.complete_task(db, EXPERIMENT_TYPE, "mixing")
        task = await task_manager.get_task(db, EXPERIMENT_TYPE, "mixing")
        assert task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_set_task_status_nonexistent_task(self, db, task_manager, experiment_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.start_task(db, EXPERIMENT_TYPE, "nonexistent_task")

    @pytest.mark.asyncio
    async def test_start_task(self, db, task_manager, experiment_manager):
        await task_manager.create_task(
            db, TaskDefinition(id="mixing", type="Magnetic Mixing", experiment_id=EXPERIMENT_TYPE)
        )

        await task_manager.start_task(db, EXPERIMENT_TYPE, "mixing")
        assert "mixing" in await experiment_manager.get_running_tasks(db, EXPERIMENT_TYPE)

    @pytest.mark.asyncio
    async def test_start_task_nonexistent_experiment(self, db, task_manager, experiment_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.start_task(db, EXPERIMENT_TYPE, "nonexistent_task")

    @pytest.mark.asyncio
    async def test_complete_task(self, db, task_manager, experiment_manager):
        await task_manager.create_task(
            db, TaskDefinition(id="mixing", type="Magnetic Mixing", experiment_id=EXPERIMENT_TYPE)
        )
        await task_manager.start_task(db, EXPERIMENT_TYPE, "mixing")
        await task_manager.complete_task(db, EXPERIMENT_TYPE, "mixing")
        assert "mixing" not in await experiment_manager.get_running_tasks(db, EXPERIMENT_TYPE)
        assert "mixing" in await experiment_manager.get_completed_tasks(db, EXPERIMENT_TYPE)

    @pytest.mark.asyncio
    async def test_complete_task_nonexistent_experiment(self, db, task_manager, experiment_manager):
        with pytest.raises(EosTaskStateError):
            await task_manager.complete_task(db, EXPERIMENT_TYPE, "nonexistent_task")

    @pytest.mark.asyncio
    async def test_add_task_output(self, db, task_manager):
        await task_manager.create_task(
            db, TaskDefinition(id="mixing", type="Magnetic Mixing", experiment_id=EXPERIMENT_TYPE)
        )

        task_output_parameters = {"x": 5}
        task_output_file_names = ["file"]

        await task_manager.add_task_output(
            db, EXPERIMENT_TYPE, "mixing", task_output_parameters, None, task_output_file_names
        )
        task_manager.add_task_output_file(EXPERIMENT_TYPE, "mixing", "file", b"file_data")

        task = await task_manager.get_task(db, EXPERIMENT_TYPE, "mixing")
        assert task.output_parameters == {"x": 5}
        assert task.output_file_names == ["file"]

        output_file = task_manager.get_task_output_file(
            experiment_id=EXPERIMENT_TYPE, task_id="mixing", file_name="file"
        )
        assert output_file == b"file_data"
