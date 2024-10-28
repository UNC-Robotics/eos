from eos.experiments.entities.experiment import ExperimentStatus, ExperimentDefinition
from eos.experiments.exceptions import EosExperimentStateError
from tests.fixtures import *

EXPERIMENT_TYPE = "water_purification"


@pytest.mark.parametrize("setup_lab_experiment", [("small_lab", EXPERIMENT_TYPE)], indirect=True)
class TestExperimentManager:
    @pytest.mark.asyncio
    async def test_create_experiment(self, experiment_manager):
        await experiment_manager.create_experiment(ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment"))
        await experiment_manager.create_experiment(ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment_2"))

        experiment1 = await experiment_manager.get_experiment("test_experiment")
        assert experiment1.id == "test_experiment"
        experiment2 = await experiment_manager.get_experiment("test_experiment_2")
        assert experiment2.id == "test_experiment_2"

    @pytest.mark.asyncio
    async def test_create_experiment_nonexistent_type(self, experiment_manager):
        with pytest.raises(EosExperimentStateError):
            await experiment_manager.create_experiment(ExperimentDefinition(type="nonexistent", id="test_experiment"))

    @pytest.mark.asyncio
    async def test_create_existing_experiment(self, experiment_manager):
        await experiment_manager.create_experiment(ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment"))

        with pytest.raises(EosExperimentStateError):
            await experiment_manager.create_experiment(ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment"))

    @pytest.mark.asyncio
    async def test_delete_experiment(self, experiment_manager):
        await experiment_manager.create_experiment(ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment"))

        experiment = await experiment_manager.get_experiment("test_experiment")
        assert experiment.id == "test_experiment"

        await experiment_manager.delete_experiment("test_experiment")

        experiment = await experiment_manager.get_experiment("test_experiment")
        assert experiment is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_experiment(self, experiment_manager):
        with pytest.raises(EosExperimentStateError):
            await experiment_manager.delete_experiment("non_existing_experiment")

    @pytest.mark.asyncio
    async def test_get_experiments_by_status(self, experiment_manager):
        await experiment_manager.create_experiment(ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment"))
        await experiment_manager.create_experiment(ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment_2"))
        await experiment_manager.create_experiment(ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment_3"))

        await experiment_manager.start_experiment("test_experiment")
        await experiment_manager.start_experiment("test_experiment_2")
        await experiment_manager.complete_experiment("test_experiment_3")

        running_experiments = await experiment_manager.get_experiments(status=ExperimentStatus.RUNNING.value)
        completed_experiments = await experiment_manager.get_experiments(status=ExperimentStatus.COMPLETED.value)

        assert running_experiments == [
            await experiment_manager.get_experiment("test_experiment"),
            await experiment_manager.get_experiment("test_experiment_2"),
        ]

        assert completed_experiments == [await experiment_manager.get_experiment("test_experiment_3")]

    @pytest.mark.asyncio
    async def test_set_experiment_status(self, experiment_manager):
        await experiment_manager.create_experiment(ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment"))
        experiment = await experiment_manager.get_experiment("test_experiment")
        assert experiment.status == ExperimentStatus.CREATED

        await experiment_manager.start_experiment("test_experiment")
        experiment = await experiment_manager.get_experiment("test_experiment")
        assert experiment.status == ExperimentStatus.RUNNING

        await experiment_manager.complete_experiment("test_experiment")
        experiment = await experiment_manager.get_experiment("test_experiment")
        assert experiment.status == ExperimentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_set_experiment_status_nonexistent_experiment(self, experiment_manager):
        with pytest.raises(EosExperimentStateError):
            await experiment_manager.start_experiment("nonexistent_experiment")

    @pytest.mark.asyncio
    async def test_get_all_experiments(self, experiment_manager):
        await experiment_manager.create_experiment(ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment"))
        await experiment_manager.create_experiment(ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment_2"))
        await experiment_manager.create_experiment(ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment_3"))

        experiments = await experiment_manager.get_experiments()
        assert experiments == [
            await experiment_manager.get_experiment("test_experiment"),
            await experiment_manager.get_experiment("test_experiment_2"),
            await experiment_manager.get_experiment("test_experiment_3"),
        ]
