import asyncio

from eos.campaigns.campaign_executor import CampaignExecutor
from eos.campaigns.entities.campaign import CampaignStatus, CampaignDefinition
from eos.campaigns.exceptions import EosCampaignExecutionError
from eos.experiments.exceptions import EosExperimentExecutionError
from tests.fixtures import *

LAB_ID = "multiplication_lab"
CAMPAIGN_ID = "optimize_multiplication_campaign"
EXPERIMENT_TYPE = "optimize_multiplication"
MAX_EXPERIMENTS = 30
OPTIMIZE = True


@pytest.mark.parametrize(
    "setup_lab_experiment",
    [(LAB_ID, EXPERIMENT_TYPE)],
    indirect=True,
)
@pytest.mark.parametrize(
    "campaign_executor",
    [(CAMPAIGN_ID, EXPERIMENT_TYPE, MAX_EXPERIMENTS, OPTIMIZE)],
    indirect=True,
)
class TestCampaignExecutor:
    @pytest.fixture
    def campaign_executor(
        self,
        configuration_manager,
        campaign_manager,
        campaign_optimizer_manager,
        task_manager,
        experiment_executor_factory,
    ):
        optimizer_computer_ip = "127.0.0.1"

        campaign_definition = CampaignDefinition(
            id=CAMPAIGN_ID,
            experiment_type=EXPERIMENT_TYPE,
            max_experiments=MAX_EXPERIMENTS,
            max_concurrent_experiments=1,
            optimize=OPTIMIZE,
            optimizer_computer_ip=optimizer_computer_ip,
        )

        return CampaignExecutor(
            campaign_definition=campaign_definition,
            campaign_manager=campaign_manager,
            campaign_optimizer_manager=campaign_optimizer_manager,
            task_manager=task_manager,
            experiment_executor_factory=experiment_executor_factory,
        )

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_start_campaign(self, campaign_executor, campaign_manager):
        await campaign_executor.start_campaign()

        campaign = await campaign_manager.get_campaign(CAMPAIGN_ID)
        assert campaign is not None
        assert campaign.id == CAMPAIGN_ID
        assert campaign.status == CampaignStatus.RUNNING

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_progress_campaign(self, campaign_executor, campaign_manager, campaign_optimizer_manager):
        await campaign_executor.start_campaign()

        campaign_finished = False
        while not campaign_finished:
            campaign_finished = await campaign_executor.progress_campaign()
            await asyncio.sleep(0.1)

        solutions = await campaign_executor.optimizer.get_optimal_solutions.remote()
        assert not solutions.empty
        assert len(solutions) == 1
        assert solutions["compute_multiplication_objective.objective"].iloc[0] / 100 <= 120

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_progress_campaign_failure(self, campaign_executor, campaign_manager, monkeypatch):
        await campaign_executor.start_campaign()
        await campaign_executor.progress_campaign()

        async def mock_progress_experiment(*args, **kwargs):
            raise EosExperimentExecutionError("Simulated experiment execution error")

        monkeypatch.setattr(
            "eos.experiments.experiment_executor.ExperimentExecutor.progress_experiment", mock_progress_experiment
        )

        # Attempt to progress the campaign
        with pytest.raises(EosCampaignExecutionError) as exc_info:
            await campaign_executor.progress_campaign()
        assert f"Error executing campaign '{CAMPAIGN_ID}'" in str(exc_info.value)
        assert campaign_executor._campaign_status == CampaignStatus.FAILED

        # Verify that the campaign manager has marked the campaign as failed
        campaign = await campaign_manager.get_campaign(CAMPAIGN_ID)
        assert campaign.status == CampaignStatus.FAILED

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_campaign_cancellation(self, campaign_executor, campaign_manager):
        await campaign_executor.start_campaign()

        # Run until two experiments are complete
        completed_experiments = 0
        while completed_experiments < 2:
            await campaign_executor.progress_campaign()
            campaign = await campaign_manager.get_campaign(CAMPAIGN_ID)
            completed_experiments = campaign.experiments_completed
            await asyncio.sleep(0.1)

        # Ensure we have at least one running experiment
        assert len(campaign_executor._experiment_executors) > 0

        await campaign_executor.cancel_campaign()

        campaign = await campaign_manager.get_campaign(CAMPAIGN_ID)
        assert campaign.status == CampaignStatus.CANCELLED

        # Try to progress the campaign after cancellation
        campaign_finished = await campaign_executor.progress_campaign()
        assert campaign_finished
        assert len(campaign_executor._experiment_executors) == 0

        with pytest.raises(EosCampaignExecutionError):
            await campaign_executor.start_campaign()

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_campaign_resuming(
        self, campaign_executor, campaign_manager, campaign_optimizer_manager, task_manager, experiment_executor_factory
    ):
        await campaign_executor.start_campaign()

        # Run until three experiments are complete
        completed_experiments = 0
        while completed_experiments < 3:
            await campaign_executor.progress_campaign()
            campaign = await campaign_manager.get_campaign(CAMPAIGN_ID)
            completed_experiments = campaign.experiments_completed
            await asyncio.sleep(0.1)

        initial_campaign = await campaign_manager.get_campaign(CAMPAIGN_ID)
        num_initial_reported_samples = ray.get(campaign_executor.optimizer.get_num_samples_reported.remote())

        await campaign_executor.cancel_campaign()
        campaign = await campaign_manager.get_campaign(CAMPAIGN_ID)
        assert campaign.status == CampaignStatus.CANCELLED
        campaign_executor.cleanup()

        # Create a new campaign executor to resume the campaign
        campaign_definition = CampaignDefinition(
            id=CAMPAIGN_ID,
            experiment_type=EXPERIMENT_TYPE,
            max_experiments=MAX_EXPERIMENTS,
            optimize=OPTIMIZE,
            resume=True,
        )
        new_campaign_executor = CampaignExecutor(
            campaign_definition,
            campaign_manager,
            campaign_optimizer_manager,
            task_manager,
            experiment_executor_factory,
        )
        await new_campaign_executor.start_campaign()
        resumed_campaign = await campaign_manager.get_campaign(CAMPAIGN_ID)
        assert resumed_campaign.status == CampaignStatus.RUNNING

        # Verify that the number of completed experiments is preserved
        assert resumed_campaign.experiments_completed == initial_campaign.experiments_completed

        # Check that the reported samples to the optimizer are preserved
        num_restored_reported_samples = ray.get(new_campaign_executor.optimizer.get_num_samples_reported.remote())
        print(num_restored_reported_samples)
        assert num_restored_reported_samples == num_initial_reported_samples

        # Run a few more iterations to ensure the campaign continues properly
        for _ in range(5):
            await new_campaign_executor.progress_campaign()

        await new_campaign_executor.cancel_campaign()
        new_campaign_executor.cleanup()

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_campaign_cancellation_timeout(self, campaign_executor, campaign_manager):
        await campaign_executor.start_campaign()

        # Run until one experiment is complete
        while (await campaign_manager.get_campaign(CAMPAIGN_ID)).experiments_completed < 1 or len(
            campaign_executor._experiment_executors
        ) < 1:
            await campaign_executor.progress_campaign()
            await asyncio.sleep(0.1)

        class SlowCancelExperimentExecutor:
            async def cancel_experiment(self):
                await asyncio.sleep(16)  # Sleep for longer than the timeout

        # Replace the experiment executors with the slow version
        campaign_executor._experiment_executors = {
            "exp1": SlowCancelExperimentExecutor(),
            "exp2": SlowCancelExperimentExecutor(),
        }

        # Try to cancel the campaign, expect a timeout
        with pytest.raises(EosCampaignExecutionError) as exc_info:
            await campaign_executor.cancel_campaign()
        assert "Timed out while cancelling experiments" in str(exc_info.value)

        campaign = await campaign_manager.get_campaign(CAMPAIGN_ID)
        assert campaign.status == CampaignStatus.CANCELLED
