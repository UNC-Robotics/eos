from litestar import Controller, get, put, Response
from litestar.datastructures import State
from litestar.exceptions import HTTPException
from litestar.handlers import post
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED, HTTP_404_NOT_FOUND

from eos.experiments.entities.experiment import ExperimentDefinition
from eos.web_api.common.entities import (
    ExperimentTypesResponse,
    ExperimentTypes,
)
from eos.web_api.public.exception_handling import handle_exceptions


class ExperimentController(Controller):
    path = "/experiments"

    @get("/{experiment_id:str}")
    async def get_experiment(self, experiment_id: str, state: State) -> Response:
        orchestrator_client = state.orchestrator_client
        async with orchestrator_client.get(f"/api/experiments/{experiment_id}") as response:
            if response.status == HTTP_200_OK:
                experiment = await response.json()
                return Response(content=experiment, status_code=HTTP_200_OK)
            if response.status == HTTP_404_NOT_FOUND:
                return Response(content={"error": "Experiment not found"}, status_code=HTTP_404_NOT_FOUND)

            raise HTTPException(status_code=response.status, detail="Error fetching experiment")

    @post("/submit")
    @handle_exceptions("Failed to submit experiment")
    async def submit_experiment(self, data: ExperimentDefinition, state: State) -> Response:
        orchestrator_client = state.orchestrator_client
        async with orchestrator_client.post("/api/experiments/submit", json=data.model_dump()) as response:
            if response.status == HTTP_201_CREATED:
                return Response(content=None, status_code=HTTP_201_CREATED)

            raise HTTPException(status_code=response.status, detail="Error submitting experiment")

    @post("/{experiment_id:str}/cancel")
    @handle_exceptions("Failed to cancel experiment")
    async def cancel_experiment(self, experiment_id: str, state: State) -> Response:
        orchestrator_client = state.orchestrator_client
        async with orchestrator_client.post(f"/api/experiments/{experiment_id}/cancel") as response:
            if response.status == HTTP_200_OK:
                return Response(content={"message": "Experiment cancelled successfully"}, status_code=HTTP_200_OK)
            if response.status == HTTP_404_NOT_FOUND:
                return Response(content={"error": "Experiment not found"}, status_code=HTTP_404_NOT_FOUND)

            raise HTTPException(status_code=response.status, detail="Error cancelling experiment")

    @put("/update_loaded")
    @handle_exceptions("Failed to update loaded experiments")
    async def update_loaded_experiments(self, data: ExperimentTypes, state: State) -> Response:
        orchestrator_client = state.orchestrator_client
        if isinstance(data.experiment_types, str):
            if data.experiment_types in ["", "[]"]:
                data.experiment_types = []
            else:
                data.experiment_types = [data.experiment_types]
        async with orchestrator_client.put(
            "/api/experiments/update_loaded", json={"experiment_types": data.experiment_types}
        ) as response:
            if response.status == HTTP_200_OK:
                return Response(content={"message": "Experiments updated successfully"}, status_code=HTTP_200_OK)

            raise HTTPException(status_code=response.status, detail="Error updating loaded experiments")

    @put("/reload")
    @handle_exceptions("Failed to reload experiments")
    async def reload_experiments(self, data: ExperimentTypes, state: State) -> Response:
        orchestrator_client = state.orchestrator_client
        if isinstance(data.experiment_types, str):
            if data.experiment_types in ["", "[]"]:
                data.experiment_types = []
            else:
                data.experiment_types = [data.experiment_types]
        async with orchestrator_client.put(
            "/api/experiments/reload", json={"experiment_types": data.experiment_types}
        ) as response:
            if response.status == HTTP_200_OK:
                return Response(content={"message": "Experiments reloaded successfully"}, status_code=HTTP_200_OK)

            raise HTTPException(status_code=response.status, detail="Error reloading experiments")

    @get("/types")
    @handle_exceptions("Failed to get experiment types")
    async def get_experiment_types(self, state: State) -> ExperimentTypesResponse:
        orchestrator_client = state.orchestrator_client
        async with orchestrator_client.get("/api/experiments/types") as response:
            if response.status == HTTP_200_OK:
                return ExperimentTypesResponse(**await response.json())

            raise HTTPException(status_code=response.status, detail="Error fetching experiment types")

    @get("/loaded")
    @handle_exceptions("Failed to get loaded experiments")
    async def get_loaded_experiments(self, state: State) -> dict:
        orchestrator_client = state.orchestrator_client
        async with orchestrator_client.get("/api/experiments/loaded") as response:
            if response.status == HTTP_200_OK:
                return await response.json()

            raise HTTPException(status_code=response.status, detail="Error fetching experiment loaded statuses")

    @get("/{experiment_type:str}/dynamic_params_template")
    @handle_exceptions("Failed to get dynamic parameters template")
    async def get_experiment_dynamic_params_template(self, experiment_type: str, state: State) -> dict:
        orchestrator_client = state.orchestrator_client
        async with orchestrator_client.get(f"/api/experiments/{experiment_type}/dynamic_params_template") as response:
            if response.status == HTTP_200_OK:
                return await response.json()

            raise HTTPException(status_code=response.status, detail="Error fetching dynamic parameters template")
