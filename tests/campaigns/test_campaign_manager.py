from eos.campaigns.entities.campaign import CampaignStatus, CampaignSubmission
from eos.campaigns.exceptions import EosCampaignStateError
from eos.protocols.entities.protocol_run import ProtocolRunSubmission
from tests.fixtures import *

PROTOCOL = "water_purification"


def create_campaign_submission(campaign_name: str, max_protocol_runs: int = 2) -> CampaignSubmission:
    """Helper function to create a non-optimized campaign submission."""
    return CampaignSubmission(
        name=campaign_name,
        protocol=PROTOCOL,
        owner="test",
        max_protocol_runs=max_protocol_runs,
        max_concurrent_protocol_runs=1,
        optimize=False,
        optimizer_ip="127.0.0.1",
        protocol_run_parameters=[{"param1": {"value": 0}}] * max_protocol_runs,
        meta={"test": "metadata"},
    )


@pytest.mark.parametrize("setup_lab_protocol", [("small_lab", PROTOCOL)], indirect=True)
class TestCampaignManager:
    @pytest.mark.asyncio
    async def test_create_campaign(self, db, campaign_manager):
        await campaign_manager.create_campaign(db, create_campaign_submission("test_campaign"))

        campaign = await campaign_manager.get_campaign(db, "test_campaign")
        assert campaign.name == "test_campaign"
        assert len(campaign.protocol_run_parameters) == 2
        assert campaign.meta == {"test": "metadata"}

    @pytest.mark.asyncio
    async def test_create_campaign_validation_errors(self, db, campaign_manager):
        # Test missing dynamic parameters
        with pytest.raises(ValueError, match="protocol_run_parameters or global_parameters must be provided"):
            invalid_submission = CampaignSubmission(
                name="test_campaign",
                protocol=PROTOCOL,
                owner="test",
                max_protocol_runs=2,
                max_concurrent_protocol_runs=1,
                optimize=False,
                optimizer_ip="127.0.0.1",
                protocol_run_parameters=None,
            )
            await campaign_manager.create_campaign(db, invalid_submission)

        # Test incorrect number of dynamic parameters
        with pytest.raises(ValueError, match="protocol_run_parameters must be provided for all protocols"):
            invalid_submission = create_campaign_submission("test_campaign", max_protocol_runs=3)
            invalid_submission.protocol_run_parameters = [{"param1": {"value": 0}}]  # Only one set
            await campaign_manager.create_campaign(db, invalid_submission)

    @pytest.mark.asyncio
    async def test_create_campaign_nonexistent_type(self, db, campaign_manager):
        with pytest.raises(EosCampaignStateError):
            submission = create_campaign_submission("test_campaign")
            submission.protocol = "nonexistent"
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
    async def test_campaign_protocol_runs(self, db, campaign_manager, protocol_run_manager):
        await campaign_manager.create_campaign(db, create_campaign_submission("test_campaign"))

        # Create protocol runs linked to the campaign
        run1_def = ProtocolRunSubmission(name="run1", type=PROTOCOL, owner="test")
        run2_def = ProtocolRunSubmission(name="run2", type=PROTOCOL, owner="test")

        await protocol_run_manager.create_protocol_run(db, run1_def, campaign="test_campaign")
        await protocol_run_manager.create_protocol_run(db, run2_def, campaign="test_campaign")

        # Verify protocol runs are linked to the campaign
        protocol_run_names = await campaign_manager.get_campaign_protocol_run_names(db, "test_campaign")
        assert len(protocol_run_names) == 2
        assert "run1" in protocol_run_names
        assert "run2" in protocol_run_names

        # Test deleting non-completed protocol runs
        await campaign_manager.delete_non_completed_campaign_protocol_runs(db, "test_campaign")
        protocol_run_names = await campaign_manager.get_campaign_protocol_run_names(db, "test_campaign")
        assert len(protocol_run_names) == 0
