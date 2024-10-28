from litestar import Controller, Response, get
from litestar.datastructures import State
from litestar.exceptions import HTTPException
from litestar.handlers import post
from litestar.status_codes import HTTP_200_OK, HTTP_404_NOT_FOUND, HTTP_201_CREATED

from eos.campaigns.entities.campaign import CampaignDefinition
from eos.web_api.public.exception_handling import handle_exceptions


class CampaignController(Controller):
    path = "/campaigns"

    @get("/{campaign_id:str}")
    @handle_exceptions("Failed to get campaign")
    async def get_campaign(self, campaign_id: str, state: State) -> Response:
        orchestrator_client = state.orchestrator_client
        async with orchestrator_client.get(f"/api/campaigns/{campaign_id}") as response:
            if response.status == HTTP_200_OK:
                campaign = await response.json()
                return Response(content=campaign, status_code=HTTP_200_OK)
            if response.status == HTTP_404_NOT_FOUND:
                return Response(content={"error": "Campaign not found"}, status_code=HTTP_404_NOT_FOUND)

            raise HTTPException(status_code=response.status, detail="Error fetching campaign")

    @post("/submit")
    @handle_exceptions("Failed to submit campaign")
    async def submit_campaign(self, data: CampaignDefinition, state: State) -> Response:
        orchestrator_client = state.orchestrator_client
        async with orchestrator_client.post("/api/campaigns/submit", json=data.model_dump()) as response:
            if response.status == HTTP_201_CREATED:
                return Response(content=None, status_code=HTTP_201_CREATED)

            raise HTTPException(status_code=response.status, detail="Error submitting campaign")

    @post("/{campaign_id:str}/cancel")
    @handle_exceptions("Failed to cancel campaign")
    async def cancel_campaign(self, campaign_id: str, state: State) -> Response:
        orchestrator_client = state.orchestrator_client
        async with orchestrator_client.post(f"/api/campaigns/{campaign_id}/cancel") as response:
            if response.status == HTTP_200_OK:
                return Response(content=None, status_code=HTTP_200_OK)
            if response.status == HTTP_404_NOT_FOUND:
                return Response(content={"error": "Campaign not found"}, status_code=HTTP_404_NOT_FOUND)

            raise HTTPException(status_code=response.status, detail="Error cancelling campaign")
