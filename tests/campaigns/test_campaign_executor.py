import asyncio

from eos.campaigns.campaign_executor import CampaignExecutor
from eos.campaigns.entities.campaign import CampaignStatus, CampaignDefinition
from eos.campaigns.exceptions import EosCampaignExecutionError
from eos.experiments.exceptions import EosExperimentExecutionError
from tests.fixtures import *

CAMPAIGN_CONFIG = {
    "LAB_ID": "multiplication_lab",
    "CAMPAIGN_ID": "optimize_multiplication_campaign",
    "EXPERIMENT_TYPE": "optimize_multiplication",
    "OWNER": "test",
    "MAX_EXPERIMENTS": 30,
    "MAX_CONCURRENT_EXPERIMENTS": 1,
    "OPTIMIZE": True,
    "OPTIMIZER_IP": "127.0.0.1",
}


@pytest.fixture
def campaign_definition():
    """Create a standard campaign definition for testing."""
    return CampaignDefinition(
        id=CAMPAIGN_CONFIG["CAMPAIGN_ID"],
        experiment_type=CAMPAIGN_CONFIG["EXPERIMENT_TYPE"],
        owner=CAMPAIGN_CONFIG["OWNER"],
        max_experiments=CAMPAIGN_CONFIG["MAX_EXPERIMENTS"],
        max_concurrent_experiments=CAMPAIGN_CONFIG["MAX_CONCURRENT_EXPERIMENTS"],
        optimize=CAMPAIGN_CONFIG["OPTIMIZE"],
        optimizer_computer_ip=CAMPAIGN_CONFIG["OPTIMIZER_IP"],
    )


@pytest.fixture
def campaign_executor_setup(
    configuration_manager,
    campaign_manager,
    campaign_optimizer_manager,
    task_manager,
    experiment_executor_factory,
    db_interface,
    campaign_definition,
):
    """Create and configure a campaign executor for testing."""
    return CampaignExecutor(
        campaign_definition=campaign_definition,
        campaign_manager=campaign_manager,
        campaign_optimizer_manager=campaign_optimizer_manager,
        task_manager=task_manager,
        experiment_executor_factory=experiment_executor_factory,
        db_interface=db_interface,
    )


@pytest.mark.parametrize(
    "setup_lab_experiment",
    [(CAMPAIGN_CONFIG["LAB_ID"], CAMPAIGN_CONFIG["EXPERIMENT_TYPE"])],
    indirect=True,
)
class TestCampaignExecutor:
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_campaign_initialization(self, campaign_executor_setup, campaign_manager, db_interface):
        """Test campaign initialization and status."""
        async with db_interface.get_async_session() as db:
            await campaign_executor_setup.start_campaign(db)

            campaign = await campaign_manager.get_campaign(db, CAMPAIGN_CONFIG["CAMPAIGN_ID"])
            assert campaign is not None
            assert campaign.id == CAMPAIGN_CONFIG["CAMPAIGN_ID"]
            assert campaign.status == CampaignStatus.RUNNING

        await campaign_executor_setup.cancel_campaign()
        campaign_executor_setup.cleanup()

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_progress_campaign(self, campaign_executor_setup, task_executor, db_interface):
        """Test full campaign optimization process."""
        async with db_interface.get_async_session() as db:
            await campaign_executor_setup.start_campaign(db)

        campaign_finished = False
        while not campaign_finished:
            campaign_finished = await campaign_executor_setup.progress_campaign()
            await task_executor.process_tasks()
            await asyncio.sleep(0.01)

        solutions = await campaign_executor_setup.optimizer.get_optimal_solutions.remote()
        assert not solutions.empty
        assert len(solutions) == 1
        assert solutions["compute_multiplication_objective.objective"].iloc[0] / 100 <= 120

        campaign_executor_setup.cleanup()

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_campaign_failure_handling(
        self, campaign_executor_setup, campaign_manager, task_executor, monkeypatch, db_interface
    ):
        """Test proper handling of campaign execution failures."""
        async with db_interface.get_async_session() as db:
            await campaign_executor_setup.start_campaign(db)

        await campaign_executor_setup.progress_campaign()
        await task_executor.process_tasks()

        async def mock_progress_experiment(*args, **kwargs):
            raise EosExperimentExecutionError("Simulated experiment execution error")

        monkeypatch.setattr(
            "eos.experiments.experiment_executor.ExperimentExecutor.progress_experiment", mock_progress_experiment
        )

        with pytest.raises(EosCampaignExecutionError) as exc_info:
            await campaign_executor_setup.progress_campaign()

            assert f"Error executing campaign '{CAMPAIGN_CONFIG['CAMPAIGN_ID']}'" in str(exc_info.value)
            assert campaign_executor_setup._campaign_status == CampaignStatus.FAILED

            async with db_interface.get_async_session() as db:
                campaign = await campaign_manager.get_campaign(db, CAMPAIGN_CONFIG["CAMPAIGN_ID"])
                assert campaign.status == CampaignStatus.FAILED

        campaign_executor_setup.cleanup()

    async def wait_for_campaign_progress(
        self, campaign_executor, campaign_manager, task_executor, db_interface, num_experiments=1
    ):
        """Helper method to wait for campaign to complete specified number of experiments."""
        completed_experiments = 0
        while completed_experiments < num_experiments:
            campaign_finished = await campaign_executor.progress_campaign()
            if campaign_finished:
                break
            await task_executor.process_tasks()
            await asyncio.sleep(0.01)

            async with db_interface.get_async_session() as db:
                campaign = await campaign_manager.get_campaign(db, CAMPAIGN_CONFIG["CAMPAIGN_ID"])
            completed_experiments = campaign.experiments_completed

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_campaign_resumption(
        self,
        campaign_executor_setup,
        campaign_manager,
        campaign_optimizer_manager,
        task_manager,
        experiment_executor_factory,
        db_interface,
        task_executor,
    ):
        """Test campaign can be properly resumed after cancellation."""
        async with db_interface.get_async_session() as db:
            await campaign_executor_setup.start_campaign(db)

        await self.wait_for_campaign_progress(
            campaign_executor_setup, campaign_manager, task_executor, db_interface, num_experiments=3
        )

        async with db_interface.get_async_session() as db:
            initial_campaign = await campaign_manager.get_campaign(db, CAMPAIGN_CONFIG["CAMPAIGN_ID"])
        initial_samples = ray.get(campaign_executor_setup.optimizer.get_num_samples_reported.remote())

        await campaign_executor_setup.cancel_campaign()
        campaign_executor_setup.cleanup()

        resume_definition = CampaignDefinition(
            id=CAMPAIGN_CONFIG["CAMPAIGN_ID"],
            experiment_type=CAMPAIGN_CONFIG["EXPERIMENT_TYPE"],
            owner=CAMPAIGN_CONFIG["OWNER"],
            max_experiments=CAMPAIGN_CONFIG["MAX_EXPERIMENTS"],
            optimize=CAMPAIGN_CONFIG["OPTIMIZE"],
            resume=True,
        )
        resumed_executor = CampaignExecutor(
            resume_definition,
            campaign_manager,
            campaign_optimizer_manager,
            task_manager,
            experiment_executor_factory,
            db_interface,
        )

        async with db_interface.get_async_session() as db:
            await resumed_executor.start_campaign(db)
            resumed_campaign = await campaign_manager.get_campaign(db, CAMPAIGN_CONFIG["CAMPAIGN_ID"])

        assert resumed_campaign.status == CampaignStatus.RUNNING
        assert resumed_campaign.experiments_completed == initial_campaign.experiments_completed

        resumed_samples = ray.get(resumed_executor.optimizer.get_num_samples_reported.remote())
        assert resumed_samples == initial_samples

        await self.wait_for_campaign_progress(
            resumed_executor, campaign_manager, task_executor, db_interface, num_experiments=5
        )

        await resumed_executor.cancel_campaign()
        resumed_executor.cleanup()

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_campaign_cancellation_timeout(self, campaign_executor_setup, campaign_manager, db_interface):
        """Test handling of timeouts during campaign cancellation."""
        async with db_interface.get_async_session() as db:
            await campaign_executor_setup.start_campaign(db)

        # Mock slow experiment cancellation
        class SlowCancelExperimentExecutor:
            async def cancel_experiment(self):
                await asyncio.sleep(16)

        campaign_executor_setup._experiment_executors = {
            "exp1": SlowCancelExperimentExecutor(),
            "exp2": SlowCancelExperimentExecutor(),
        }

        with pytest.raises(EosCampaignExecutionError):
            await campaign_executor_setup.cancel_campaign()

        campaign_executor_setup.cleanup()
