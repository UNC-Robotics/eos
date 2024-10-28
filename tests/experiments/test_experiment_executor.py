import asyncio
from unittest.mock import patch

from eos.experiments.entities.experiment import ExperimentStatus, ExperimentDefinition
from eos.experiments.exceptions import EosExperimentExecutionError
from eos.experiments.experiment_executor import ExperimentExecutor
from eos.tasks.entities.task import TaskStatus
from tests.fixtures import *

LAB_ID = "small_lab"
EXPERIMENT_TYPE = "water_purification"
EXPERIMENT_ID = "water_purification_#1"

DYNAMIC_PARAMETERS = {
    "mixing": {
        "time": 120,
    },
    "evaporation": {
        "evaporation_temperature": 120,
        "evaporation_rotation_speed": 200,
        "evaporation_sparging_flow": 5,
    },
}


@pytest.mark.parametrize(
    "setup_lab_experiment",
    [(LAB_ID, EXPERIMENT_TYPE)],
    indirect=True,
)
class TestExperimentExecutor:
    @pytest.fixture
    def experiment_executor(
        self,
        experiment_manager,
        task_manager,
        container_manager,
        task_executor,
        greedy_scheduler,
        experiment_graph,
    ):
        return ExperimentExecutor(
            experiment_definition=ExperimentDefinition(
                id=EXPERIMENT_ID, type=EXPERIMENT_TYPE, dynamic_parameters=DYNAMIC_PARAMETERS
            ),
            experiment_graph=experiment_graph,
            experiment_manager=experiment_manager,
            task_manager=task_manager,
            container_manager=container_manager,
            task_executor=task_executor,
            scheduler=greedy_scheduler,
        )

    @pytest.mark.asyncio
    async def test_start_experiment(self, experiment_executor, experiment_manager):
        await experiment_executor.start_experiment()

        experiment = await experiment_manager.get_experiment(EXPERIMENT_ID)
        assert experiment is not None
        assert experiment.id == EXPERIMENT_ID
        assert experiment.status == ExperimentStatus.RUNNING

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_progress_experiment(self, experiment_executor, experiment_manager, task_manager):
        await experiment_executor.start_experiment()

        experiment_completed = await experiment_executor.progress_experiment()
        assert not experiment_completed
        await experiment_executor._task_output_futures["mixing"]

        experiment_completed = await experiment_executor.progress_experiment()
        assert not experiment_completed
        task = await task_manager.get_task(EXPERIMENT_ID, "mixing")
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        await experiment_executor._task_output_futures["evaporation"]

        experiment_completed = await experiment_executor.progress_experiment()
        task = await task_manager.get_task(EXPERIMENT_ID, "evaporation")
        assert task.status == TaskStatus.COMPLETED
        assert not experiment_completed

        # Final progress
        experiment_completed = await experiment_executor.progress_experiment()
        assert experiment_completed
        experiment = await experiment_manager.get_experiment(EXPERIMENT_ID)
        assert experiment.status == ExperimentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_task_output_registration(self, experiment_executor, task_manager):
        await experiment_executor.start_experiment()

        experiment_completed = False
        while not experiment_completed:
            experiment_completed = await experiment_executor.progress_experiment()
            await asyncio.sleep(0.1)

        mixing_output = await task_manager.get_task_output(EXPERIMENT_ID, "mixing")
        assert mixing_output is not None
        assert mixing_output.parameters["mixing_time"] == DYNAMIC_PARAMETERS["mixing"]["time"]

    @pytest.mark.asyncio
    async def test_resolve_input_parameter_references_and_dynamic_parameters(self, experiment_executor, task_manager):
        await experiment_executor.start_experiment()

        experiment_completed = False
        while not experiment_completed:
            experiment_completed = await experiment_executor.progress_experiment()
            await asyncio.sleep(0.1)

        mixing_task = await task_manager.get_task(EXPERIMENT_ID, "mixing")
        mixing_result = await task_manager.get_task_output(EXPERIMENT_ID, "mixing")

        evaporation_task = await task_manager.get_task(EXPERIMENT_ID, "evaporation")
        # Check the dynamic parameter for input mixing time
        assert mixing_task.input.parameters["time"] == DYNAMIC_PARAMETERS["mixing"]["time"]

        # Check that the output parameter mixing time was assigned to the input parameter evaporation time
        assert evaporation_task.input.parameters["evaporation_time"] == mixing_result.parameters["mixing_time"]

    @pytest.mark.parametrize(
        "experiment_status",
        [
            ExperimentStatus.COMPLETED,
            ExperimentStatus.SUSPENDED,
            ExperimentStatus.CANCELLED,
            ExperimentStatus.FAILED,
            ExperimentStatus.RUNNING,
        ],
    )
    @pytest.mark.asyncio
    async def test_handle_existing_experiment(self, experiment_executor, experiment_manager, experiment_status):
        await experiment_manager.create_experiment(experiment_executor._experiment_definition)
        await experiment_manager._set_experiment_status(EXPERIMENT_ID, experiment_status)

        experiment_executor._experiment_definition.resume = False
        with patch.object(experiment_executor, "_resume_experiment") as mock_resume:
            if experiment_status in [
                ExperimentStatus.COMPLETED,
                ExperimentStatus.SUSPENDED,
                ExperimentStatus.CANCELLED,
                ExperimentStatus.FAILED,
            ]:
                with pytest.raises(EosExperimentExecutionError) as exc_info:
                    experiment = await experiment_manager.get_experiment(EXPERIMENT_ID)
                    await experiment_executor._handle_existing_experiment(experiment)
                assert experiment_status.name.lower() in str(exc_info.value)
                mock_resume.assert_not_called()
            else:
                experiment = await experiment_manager.get_experiment(EXPERIMENT_ID)
                await experiment_executor._handle_existing_experiment(experiment)
                mock_resume.assert_not_called()

        experiment_executor._experiment_definition.resume = True
        with patch.object(experiment_executor, "_resume_experiment") as mock_resume:
            experiment = await experiment_manager.get_experiment(EXPERIMENT_ID)
            await experiment_executor._handle_existing_experiment(experiment)
            mock_resume.assert_called_once()

        assert experiment_executor._experiment_status == experiment_status
