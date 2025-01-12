from eos.experiments.entities.experiment import ExperimentStatus, ExperimentDefinition
from eos.experiments.exceptions import EosExperimentStateError
from tests.fixtures import *

EXPERIMENT_TYPE = "water_purification"


@pytest.mark.parametrize("setup_lab_experiment", [("small_lab", EXPERIMENT_TYPE)], indirect=True)
class TestExperimentManager:
    @pytest.mark.asyncio
    async def test_create_experiment(self, db, experiment_manager):
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment", owner="test")
        )
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment_2", owner="test")
        )

        experiment1 = await experiment_manager.get_experiment(db, "test_experiment")
        assert experiment1.id == "test_experiment"
        experiment2 = await experiment_manager.get_experiment(db, "test_experiment_2")
        assert experiment2.id == "test_experiment_2"

    @pytest.mark.asyncio
    async def test_create_experiment_nonexistent_type(self, db, experiment_manager):
        with pytest.raises(EosExperimentStateError):
            await experiment_manager.create_experiment(
                db, ExperimentDefinition(type="nonexistent", id="test_experiment", owner="test")
            )

    @pytest.mark.asyncio
    async def test_create_existing_experiment(self, db, experiment_manager):
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment", owner="test")
        )

        with pytest.raises(EosExperimentStateError):
            await experiment_manager.create_experiment(
                db, ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment", owner="test")
            )

    @pytest.mark.asyncio
    async def test_delete_experiment(self, db, experiment_manager):
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment", owner="test")
        )

        experiment = await experiment_manager.get_experiment(db, "test_experiment")
        assert experiment.id == "test_experiment"

        await experiment_manager.delete_experiment(db, "test_experiment")

        experiment = await experiment_manager.get_experiment(db, "test_experiment")
        assert experiment is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_experiment(self, db, experiment_manager):
        with pytest.raises(EosExperimentStateError):
            await experiment_manager.delete_experiment(db, "non_existing_experiment")

    @pytest.mark.asyncio
    async def test_get_experiments_by_status(self, db, experiment_manager):
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment", owner="test")
        )
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment_2", owner="test")
        )
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment_3", owner="test")
        )

        await experiment_manager.start_experiment(db, "test_experiment")
        await experiment_manager.start_experiment(db, "test_experiment_2")
        await experiment_manager.complete_experiment(db, "test_experiment_3")

        running_experiments = await experiment_manager.get_experiments(db, status=ExperimentStatus.RUNNING.value)
        completed_experiments = await experiment_manager.get_experiments(db, status=ExperimentStatus.COMPLETED.value)

        assert running_experiments == [
            await experiment_manager.get_experiment(db, "test_experiment"),
            await experiment_manager.get_experiment(db, "test_experiment_2"),
        ]

        assert completed_experiments == [await experiment_manager.get_experiment(db, "test_experiment_3")]

    @pytest.mark.asyncio
    async def test_set_experiment_status(self, db, experiment_manager):
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment", owner="test")
        )
        experiment = await experiment_manager.get_experiment(db, "test_experiment")
        assert experiment.status == ExperimentStatus.CREATED

        await experiment_manager.start_experiment(db, "test_experiment")
        experiment = await experiment_manager.get_experiment(db, "test_experiment")
        assert experiment.status == ExperimentStatus.RUNNING

        await experiment_manager.complete_experiment(db, "test_experiment")
        experiment = await experiment_manager.get_experiment(db, "test_experiment")
        assert experiment.status == ExperimentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_set_experiment_status_nonexistent_experiment(self, db, experiment_manager):
        with pytest.raises(EosExperimentStateError):
            await experiment_manager.start_experiment(db, "nonexistent_experiment")

    @pytest.mark.asyncio
    async def test_get_all_experiments(self, db, experiment_manager):
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment", owner="test")
        )
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment_2", owner="test")
        )
        await experiment_manager.create_experiment(
            db, ExperimentDefinition(type=EXPERIMENT_TYPE, id="test_experiment_3", owner="test")
        )

        experiments = await experiment_manager.get_experiments(db)
        assert experiments == [
            await experiment_manager.get_experiment(db, "test_experiment"),
            await experiment_manager.get_experiment(db, "test_experiment_2"),
            await experiment_manager.get_experiment(db, "test_experiment_3"),
        ]
