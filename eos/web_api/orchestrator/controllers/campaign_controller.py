from litestar import Controller, Response, get
from litestar.handlers import post
from litestar.status_codes import HTTP_200_OK, HTTP_404_NOT_FOUND, HTTP_201_CREATED

from eos.orchestration.orchestrator import Orchestrator
from eos.web_api.common.entities import SubmitCampaignRequest
from eos.web_api.public.exception_handling import handle_exceptions


class CampaignController(Controller):
    path = "/campaigns"

    @get("/{campaign_id:str}")
    @handle_exceptions("Failed to get campaign")
    async def get_campaign(self, campaign_id: str, orchestrator: Orchestrator) -> Response:
        campaign = await orchestrator.get_campaign(campaign_id)

        if campaign is None:
            return Response(content={"error": "Campaign not found"}, status_code=HTTP_404_NOT_FOUND)

        return Response(content=campaign.model_dump_json(), status_code=HTTP_200_OK)

    @post("/submit")
    @handle_exceptions("Failed to submit campaign")
    async def submit_campaign(self, data: SubmitCampaignRequest, orchestrator: Orchestrator) -> Response:
        await orchestrator.submit_campaign(data.campaign_id, data.experiment_type, data.campaign_execution_parameters)
        return Response(content=None, status_code=HTTP_201_CREATED)

    @post("/{campaign_id:str}/cancel")
    @handle_exceptions("Failed to cancel campaign")
    async def cancel_campaign(self, campaign_id: str, orchestrator: Orchestrator) -> Response:
        await orchestrator.cancel_campaign(campaign_id)
        return Response(content=None, status_code=HTTP_200_OK)