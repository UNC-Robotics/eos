from litestar import get, post, Controller

from eos.campaigns.entities.campaign import CampaignSubmission, Campaign
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.orchestration.orchestrator import Orchestrator
from eos.web_api.exception_handling import APIError


class CampaignController(Controller):
    """Controller for campaign-related endpoints."""

    path = "/campaigns"

    @get("/{campaign_name:str}")
    async def get_campaign(self, campaign_name: str, db: AsyncDbSession, orchestrator: Orchestrator) -> Campaign:
        """Get a campaign by name."""
        campaign = await orchestrator.campaigns.get_campaign(db, campaign_name)

        if campaign is None:
            raise APIError(status_code=404, detail="Campaign not found")

        return campaign

    @post("/")
    async def submit_campaign(
        self, data: CampaignSubmission, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> dict[str, str]:
        """Submit a new campaign for execution."""
        await orchestrator.campaigns.submit_campaign(db, data)
        return {"message": "Campaign submitted"}

    @post("/{campaign_name:str}/cancel")
    async def cancel_campaign(self, campaign_name: str, orchestrator: Orchestrator) -> dict[str, str]:
        """Cancel a running campaign."""
        await orchestrator.campaigns.cancel_campaign(campaign_name)
        return {"message": "Campaign cancellation requested"}
