from eos.campaigns.entities.campaign import CampaignStatus, CampaignDefinition
from eos.campaigns.exceptions import EosCampaignStateError
from tests.fixtures import *

EXPERIMENT_TYPE = "water_purification"


def create_campaign_definition(campaign_id: str, max_experiments: int = 2) -> CampaignDefinition:
    """Helper function to create a non-optimized campaign definition."""
    return CampaignDefinition(
        id=campaign_id,
        experiment_type=EXPERIMENT_TYPE,
        owner="test",
        max_experiments=max_experiments,
        max_concurrent_experiments=1,
        optimize=False,
        optimizer_computer_ip="127.0.0.1",
        dynamic_parameters=[{"param1": {"value": 0}}] * max_experiments,  # Simplified params
        meta={"test": "metadata"},
    )


@pytest.mark.parametrize("setup_lab_experiment", [("small_lab", EXPERIMENT_TYPE)], indirect=True)
class TestCampaignManager:
    @pytest.mark.asyncio
    async def test_create_campaign(self, db, campaign_manager):
        await campaign_manager.create_campaign(db, create_campaign_definition("test_campaign"))

        campaign = await campaign_manager.get_campaign(db, "test_campaign")
        assert campaign.id == "test_campaign"
        assert len(campaign.dynamic_parameters) == 2
        assert campaign.meta == {"test": "metadata"}

    @pytest.mark.asyncio
    async def test_create_campaign_validation_errors(self, db, campaign_manager):
        # Test missing dynamic parameters
        with pytest.raises(ValueError, match="Campaign dynamic parameters must be provided"):
            invalid_definition = CampaignDefinition(
                id="test_campaign",
                experiment_type=EXPERIMENT_TYPE,
                owner="test",
                max_experiments=2,
                max_concurrent_experiments=1,
                optimize=False,
                optimizer_computer_ip="127.0.0.1",
                dynamic_parameters=None,
            )
            await campaign_manager.create_campaign(db, invalid_definition)

        # Test incorrect number of dynamic parameters
        with pytest.raises(ValueError, match="Dynamic parameters must be provided for all experiments"):
            invalid_definition = create_campaign_definition("test_campaign", max_experiments=3)
            invalid_definition.dynamic_parameters = [{"param1": {"value": 0}}]  # Only one set
            await campaign_manager.create_campaign(db, invalid_definition)

    @pytest.mark.asyncio
    async def test_create_campaign_nonexistent_type(self, db, campaign_manager):
        with pytest.raises(EosCampaignStateError):
            definition = create_campaign_definition("test_campaign")
            definition.experiment_type = "nonexistent"
            await campaign_manager.create_campaign(db, definition)

    @pytest.mark.asyncio
    async def test_create_existing_campaign(self, db, campaign_manager):
        definition = create_campaign_definition("test_campaign")
        await campaign_manager.create_campaign(db, definition)

        with pytest.raises(EosCampaignStateError):
            await campaign_manager.create_campaign(db, definition)

    @pytest.mark.asyncio
    async def test_delete_campaign(self, db, campaign_manager):
        await campaign_manager.create_campaign(db, create_campaign_definition("test_campaign"))

        campaign = await campaign_manager.get_campaign(db, "test_campaign")
        assert campaign is not None

        await campaign_manager.delete_campaign(db, "test_campaign")

        campaign = await campaign_manager.get_campaign(db, "test_campaign")
        assert campaign is None

    @pytest.mark.asyncio
    async def test_get_campaigns_by_status(self, db, campaign_manager):
        # Create and set different statuses for campaigns
        for campaign_id in ["campaign1", "campaign2", "campaign3"]:
            await campaign_manager.create_campaign(db, create_campaign_definition(campaign_id))

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
        await campaign_manager.create_campaign(db, create_campaign_definition("test_campaign"))

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
    async def test_campaign_experiments(self, db, campaign_manager):
        await campaign_manager.create_campaign(db, create_campaign_definition("test_campaign"))

        # Test adding experiments
        await campaign_manager.add_campaign_experiment(db, "test_campaign", "exp1")
        await campaign_manager.add_campaign_experiment(db, "test_campaign", "exp2")

        campaign = await campaign_manager.get_campaign(db, "test_campaign")
        assert len(campaign.current_experiment_ids) == 2
        assert "exp1" in campaign.current_experiment_ids
        assert "exp2" in campaign.current_experiment_ids

        # Test removing single experiment
        await campaign_manager.delete_campaign_experiment(db, "test_campaign", "exp1")
        campaign = await campaign_manager.get_campaign(db, "test_campaign")
        assert len(campaign.current_experiment_ids) == 1
        assert "exp2" in campaign.current_experiment_ids

        # Test clearing all experiments
        await campaign_manager.delete_current_campaign_experiments(db, "test_campaign")
        campaign = await campaign_manager.get_campaign(db, "test_campaign")
        assert len(campaign.current_experiment_ids) == 0
