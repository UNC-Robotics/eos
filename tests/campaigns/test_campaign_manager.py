from eos.campaigns.entities.campaign import CampaignStatus, CampaignSubmission
from eos.campaigns.exceptions import EosCampaignStateError
from tests.fixtures import *

EXPERIMENT_TYPE = "water_purification"


def create_campaign_submission(campaign_name: str, max_experiments: int = 2) -> CampaignSubmission:
    """Helper function to create a non-optimized campaign submission."""
    return CampaignSubmission(
        name=campaign_name,
        experiment_type=EXPERIMENT_TYPE,
        owner="test",
        max_experiments=max_experiments,
        max_concurrent_experiments=1,
        optimize=False,
        optimizer_ip="127.0.0.1",
        experiment_parameters=[{"param1": {"value": 0}}] * max_experiments,
        meta={"test": "metadata"},
    )


@pytest.mark.parametrize("setup_lab_experiment", [("small_lab", EXPERIMENT_TYPE)], indirect=True)
class TestCampaignManager:
    @pytest.mark.asyncio
    async def test_create_campaign(self, db, campaign_manager):
        await campaign_manager.create_campaign(db, create_campaign_submission("test_campaign"))

        campaign = await campaign_manager.get_campaign(db, "test_campaign")
        assert campaign.name == "test_campaign"
        assert len(campaign.experiment_parameters) == 2
        assert campaign.meta == {"test": "metadata"}

    @pytest.mark.asyncio
    async def test_create_campaign_validation_errors(self, db, campaign_manager):
        # Test missing dynamic parameters
        with pytest.raises(ValueError, match="experiment_parameters or global_parameters must be provided"):
            invalid_submission = CampaignSubmission(
                name="test_campaign",
                experiment_type=EXPERIMENT_TYPE,
                owner="test",
                max_experiments=2,
                max_concurrent_experiments=1,
                optimize=False,
                optimizer_ip="127.0.0.1",
                experiment_parameters=None,
            )
            await campaign_manager.create_campaign(db, invalid_submission)

        # Test incorrect number of dynamic parameters
        with pytest.raises(ValueError, match="experiment_parameters must be provided for all experiments"):
            invalid_submission = create_campaign_submission("test_campaign", max_experiments=3)
            invalid_submission.experiment_parameters = [{"param1": {"value": 0}}]  # Only one set
            await campaign_manager.create_campaign(db, invalid_submission)

    @pytest.mark.asyncio
    async def test_create_campaign_nonexistent_type(self, db, campaign_manager):
        with pytest.raises(EosCampaignStateError):
            submission = create_campaign_submission("test_campaign")
            submission.experiment_type = "nonexistent"
            await campaign_manager.create_campaign(db, submission)

    @pytest.mark.asyncio
    async def test_create_existing_campaign(self, db, campaign_manager):
        submission = create_campaign_submission("test_campaign")
        await campaign_manager.create_campaign(db, submission)

        with pytest.raises(EosCampaignStateError):
            await campaign_manager.create_campaign(db, submission)

    @pytest.mark.asyncio
    async def test_delete_campaign(self, db, campaign_manager):
        await campaign_manager.create_campaign(db, create_campaign_submission("test_campaign"))

        campaign = await campaign_manager.get_campaign(db, "test_campaign")
        assert campaign is not None

        await campaign_manager.delete_campaign(db, "test_campaign")

        campaign = await campaign_manager.get_campaign(db, "test_campaign")
        assert campaign is None

    @pytest.mark.asyncio
    async def test_get_campaigns_by_status(self, db, campaign_manager):
        # Create and set different statuses for campaigns
        for campaign_name in ["campaign1", "campaign2", "campaign3"]:
            await campaign_manager.create_campaign(db, create_campaign_submission(campaign_name))

        await campaign_manager.start_campaign(db, "campaign1")
        await campaign_manager.start_campaign(db, "campaign2")
        await campaign_manager.complete_campaign(db, "campaign3")

        running_campaigns = await campaign_manager.get_campaigns(db, status=CampaignStatus.RUNNING.value)
        completed_campaigns = await campaign_manager.get_campaigns(db, status=CampaignStatus.COMPLETED.value)

        assert len(running_campaigns) == 2
        assert len(completed_campaigns) == 1
        assert all(c.status == CampaignStatus.RUNNING for c in running_campaigns)
        assert all(c.status == CampaignStatus.COMPLETED for c in completed_campaigns)

    @pytest.mark.asyncio
    async def test_campaign_lifecycle(self, db, campaign_manager):
        await campaign_manager.create_campaign(db, create_campaign_submission("test_campaign"))

        # Test status transitions
        campaign = await campaign_manager.get_campaign(db, "test_campaign")
        assert campaign.status == CampaignStatus.CREATED
        assert campaign.start_time is None
        assert campaign.end_time is None

        await campaign_manager.start_campaign(db, "test_campaign")
        campaign = await campaign_manager.get_campaign(db, "test_campaign")
        assert campaign.status == CampaignStatus.RUNNING
        assert campaign.start_time is not None
        assert campaign.end_time is None

        await campaign_manager.complete_campaign(db, "test_campaign")
        campaign = await campaign_manager.get_campaign(db, "test_campaign")
        assert campaign.status == CampaignStatus.COMPLETED
        assert campaign.start_time is not None
        assert campaign.end_time is not None

    @pytest.mark.asyncio
    async def test_campaign_experiments(self, db, campaign_manager, experiment_manager):
        await campaign_manager.create_campaign(db, create_campaign_submission("test_campaign"))

        # Create experiments linked to the campaign
        from eos.experiments.entities.experiment import ExperimentSubmission

        exp1_def = ExperimentSubmission(name="exp1", type=EXPERIMENT_TYPE, owner="test")
        exp2_def = ExperimentSubmission(name="exp2", type=EXPERIMENT_TYPE, owner="test")

        await experiment_manager.create_experiment(db, exp1_def, campaign="test_campaign")
        await experiment_manager.create_experiment(db, exp2_def, campaign="test_campaign")

        # Verify experiments are linked to the campaign
        experiment_names = await campaign_manager.get_campaign_experiment_names(db, "test_campaign")
        assert len(experiment_names) == 2
        assert "exp1" in experiment_names
        assert "exp2" in experiment_names

        # Test deleting non-completed experiments
        await campaign_manager.delete_non_completed_campaign_experiments(db, "test_campaign")
        experiment_names = await campaign_manager.get_campaign_experiment_names(db, "test_campaign")
        assert len(experiment_names) == 0
