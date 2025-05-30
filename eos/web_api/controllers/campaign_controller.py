from litestar import get, post, Controller, Response

from eos.campaigns.entities.campaign import CampaignDefinition, Campaign
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.orchestration.orchestrator import Orchestrator
from eos.web_api.exception_handling import APIError


class CampaignController(Controller):
    """Controller for campaign-related endpoints."""

    path = "/campaigns"

    @get("/{campaign_id:str}")
    async def get_campaign(self, campaign_id: str, db: AsyncDbSession, orchestrator: Orchestrator) -> Campaign:
        """Get a campaign by ID."""
        campaign = await orchestrator.campaigns.get_campaign(db, campaign_id)

        if campaign is None:
            raise APIError(status_code=404, detail="Campaign not found")

        return campaign

    @post("/")
    async def submit_campaign(
        self, data: CampaignDefinition, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> Response:
        """Submit a new campaign for execution."""
        await orchestrator.campaigns.submit_campaign(db, data)
        return Response(content="Submitted", status_code=201)

    @post("/{campaign_id:str}/cancel")
    async def cancel_campaign(self, campaign_id: str, orchestrator: Orchestrator) -> Response:
        """Cancel a running campaign."""
        await orchestrator.campaigns.cancel_campaign(campaign_id)
        return Response(content="Cancellation request submitted.", status_code=202)
