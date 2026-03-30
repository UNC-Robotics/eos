import asyncio

from eos.campaigns.campaign_executor import CampaignExecutor
from eos.campaigns.entities.campaign import CampaignStatus, CampaignSubmission
from eos.campaigns.exceptions import EosCampaignExecutionError
from eos.protocols.exceptions import EosProtocolRunExecutionError
from tests.fixtures import *

CAMPAIGN_CONFIG = {
    "LAB_NAME": "multiplication_lab",
    "CAMPAIGN_NAME": "optimize_multiplication_campaign",
    "PROTOCOL": "optimize_multiplication",
    "OWNER": "test",
    "MAX_PROTOCOL_RUNS": 30,
    "MAX_CONCURRENT_PROTOCOL_RUNS": 1,
    "OPTIMIZE": True,
    "OPTIMIZER_IP": "127.0.0.1",
}


@pytest.fixture
def campaign_submission():
    """Create a standard campaign submission for testing."""
    return CampaignSubmission(
        name=CAMPAIGN_CONFIG["CAMPAIGN_NAME"],
        protocol=CAMPAIGN_CONFIG["PROTOCOL"],
        owner=CAMPAIGN_CONFIG["OWNER"],
        max_protocol_runs=CAMPAIGN_CONFIG["MAX_PROTOCOL_RUNS"],
        max_concurrent_protocol_runs=CAMPAIGN_CONFIG["MAX_CONCURRENT_PROTOCOL_RUNS"],
        optimize=CAMPAIGN_CONFIG["OPTIMIZE"],
        optimizer_ip=CAMPAIGN_CONFIG["OPTIMIZER_IP"],
    )


@pytest.fixture
def campaign_executor_setup(
    configuration_manager,
    campaign_manager,
    campaign_optimizer_manager,
    task_manager,
    protocol_run_manager,
    protocol_executor_factory,
    db_interface,
    campaign_submission,
):
    """Create and configure a campaign executor for testing."""
    return CampaignExecutor(
        campaign_submission=campaign_submission,
        campaign_manager=campaign_manager,
        campaign_optimizer_manager=campaign_optimizer_manager,
        task_manager=task_manager,
        protocol_executor_factory=protocol_executor_factory,
        protocol_run_manager=protocol_run_manager,
        db_interface=db_interface,
    )


@pytest.mark.parametrize(
    "setup_lab_protocol",
    [(CAMPAIGN_CONFIG["LAB_NAME"], CAMPAIGN_CONFIG["PROTOCOL"])],
    indirect=True,
)
class TestCampaignExecutor:
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_campaign_initialization(self, campaign_executor_setup, campaign_manager, db_interface):
        """Test campaign initialization and status."""
        async with db_interface.get_async_session() as db:
            await campaign_executor_setup.start_campaign(db)

            campaign = await campaign_manager.get_campaign(db, CAMPAIGN_CONFIG["CAMPAIGN_NAME"])
            assert campaign is not None
            assert campaign.name == CAMPAIGN_CONFIG["CAMPAIGN_NAME"]
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

        while not campaign_executor_setup._protocol_executors:
            await campaign_executor_setup.progress_campaign()
            await task_executor.process_tasks()
            await asyncio.sleep(0.01)

        async def mock_progress_protocol_run(*args, **kwargs):
            raise EosProtocolRunExecutionError("Simulated protocol run execution error")

        monkeypatch.setattr(
            "eos.protocols.protocol_executor.ProtocolExecutor.progress_protocol_run", mock_progress_protocol_run
        )

        with pytest.raises(EosCampaignExecutionError):
            await campaign_executor_setup.progress_campaign()

        assert (
            f"Error executing campaign '{CAMPAIGN_CONFIG['CAMPAIGN_NAME']}'"
            in str(campaign_executor_setup._campaign_status)
            or campaign_executor_setup._campaign_status == CampaignStatus.FAILED
        )

        async with db_interface.get_async_session() as db:
            campaign = await campaign_manager.get_campaign(db, CAMPAIGN_CONFIG["CAMPAIGN_NAME"])
            assert campaign.status == CampaignStatus.FAILED

        campaign_executor_setup.cleanup()

    async def wait_for_campaign_progress(
        self, campaign_executor, campaign_manager, task_executor, db_interface, num_protocol_runs=1
    ):
        """Helper method to wait for campaign to complete specified number of protocols."""
        completed_protocol_runs = 0
        while completed_protocol_runs < num_protocol_runs:
            campaign_finished = await campaign_executor.progress_campaign()
            if campaign_finished:
                break
            await task_executor.process_tasks()
            await asyncio.sleep(0.01)

            async with db_interface.get_async_session() as db:
                campaign = await campaign_manager.get_campaign(db, CAMPAIGN_CONFIG["CAMPAIGN_NAME"])
            completed_protocol_runs = campaign.protocol_runs_completed

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_campaign_resumption(
        self,
        campaign_executor_setup,
        campaign_manager,
        campaign_optimizer_manager,
        task_manager,
        protocol_run_manager,
        protocol_executor_factory,
        db_interface,
        task_executor,
    ):
        """Test campaign can be properly resumed after cancellation."""
        async with db_interface.get_async_session() as db:
            await campaign_executor_setup.start_campaign(db)

        await self.wait_for_campaign_progress(
            campaign_executor_setup, campaign_manager, task_executor, db_interface, num_protocol_runs=3
        )

        async with db_interface.get_async_session() as db:
            initial_campaign = await campaign_manager.get_campaign(db, CAMPAIGN_CONFIG["CAMPAIGN_NAME"])

        await campaign_executor_setup.cancel_campaign()
        campaign_executor_setup.cleanup()

        resume_submission = CampaignSubmission(
            name=CAMPAIGN_CONFIG["CAMPAIGN_NAME"],
            protocol=CAMPAIGN_CONFIG["PROTOCOL"],
            owner=CAMPAIGN_CONFIG["OWNER"],
            max_protocol_runs=CAMPAIGN_CONFIG["MAX_PROTOCOL_RUNS"],
            optimize=CAMPAIGN_CONFIG["OPTIMIZE"],
            resume=True,
        )
        resumed_executor = CampaignExecutor(
            resume_submission,
            campaign_manager,
            campaign_optimizer_manager,
            task_manager,
            protocol_executor_factory,
            protocol_run_manager,
            db_interface,
        )

        async with db_interface.get_async_session() as db:
            await resumed_executor.start_campaign(db)
            resumed_campaign = await campaign_manager.get_campaign(db, CAMPAIGN_CONFIG["CAMPAIGN_NAME"])

        assert resumed_campaign.status == CampaignStatus.RUNNING
        assert resumed_campaign.protocol_runs_completed == initial_campaign.protocol_runs_completed

        while resumed_executor.optimizer is None:
            await resumed_executor.progress_campaign()
            await asyncio.sleep(0.01)

        resumed_samples = ray.get(resumed_executor.optimizer.get_num_samples_reported.remote())
        assert resumed_samples == initial_campaign.protocol_runs_completed

        await self.wait_for_campaign_progress(
            resumed_executor, campaign_manager, task_executor, db_interface, num_protocol_runs=5
        )

        await resumed_executor.cancel_campaign()
        resumed_executor.cleanup()

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_campaign_cancellation_timeout(self, campaign_executor_setup, campaign_manager, db_interface):
        """Test handling of timeouts during campaign cancellation."""
        async with db_interface.get_async_session() as db:
            await campaign_executor_setup.start_campaign(db)

        # Mock slow protocol run cancellation
        class SlowCancelProtocolRunExecutor:
            async def cancel_protocol_run(self):
                await asyncio.sleep(16)

        campaign_executor_setup._protocol_executors = {
            "run1": SlowCancelProtocolRunExecutor(),
            "run2": SlowCancelProtocolRunExecutor(),
        }

        with pytest.raises(EosCampaignExecutionError):
            await campaign_executor_setup.cancel_campaign()

        campaign_executor_setup.cleanup()
