from litestar import Controller, get, put, Response
from litestar.handlers import post
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED, HTTP_404_NOT_FOUND

from eos.experiments.entities.experiment import ExperimentDefinition
from eos.orchestration.orchestrator import Orchestrator
from eos.web_api.common.entities import (
    ExperimentTypesResponse,
    ExperimentTypes,
)
from eos.web_api.public.exception_handling import handle_exceptions


class ExperimentController(Controller):
    path = "/experiments"

    @get("/{experiment_id:str}")
    async def get_experiment(self, experiment_id: str, orchestrator: Orchestrator) -> Response:
        experiment = await orchestrator.experiments.get_experiment(experiment_id)

        if experiment is None:
            return Response(content={"error": "Experiment not found"}, status_code=HTTP_404_NOT_FOUND)

        return Response(content=experiment.model_dump_json(), status_code=HTTP_200_OK)

    @post("/submit")
    @handle_exceptions("Failed to submit experiment")
    async def submit_experiment(self, data: ExperimentDefinition, orchestrator: Orchestrator) -> Response:
        await orchestrator.experiments.submit_experiment(data)
        return Response(content=None, status_code=HTTP_201_CREATED)

    @post("/{experiment_id:str}/cancel")
    @handle_exceptions("Failed to cancel experiment")
    async def cancel_experiment(self, experiment_id: str, orchestrator: Orchestrator) -> Response:
        await orchestrator.experiments.cancel_experiment(experiment_id)
        return Response(content=None, status_code=HTTP_200_OK)

    @put("/update_loaded")
    @handle_exceptions("Failed to update loaded experiments")
    async def update_loaded_experiments(self, data: ExperimentTypes, orchestrator: Orchestrator) -> Response:
        await orchestrator.loading.update_loaded_experiments(set(data.experiment_types))
        return Response(content=None, status_code=HTTP_200_OK)

    @put("/reload")
    @handle_exceptions("Failed to reload experiments")
    async def reload_experiments(self, data: ExperimentTypes, orchestrator: Orchestrator) -> Response:
        await orchestrator.loading.reload_experiments(set(data.experiment_types))
        return Response(content=None, status_code=HTTP_200_OK)

    @get("/types")
    @handle_exceptions("Failed to get experiment types")
    async def get_experiment_types(self, orchestrator: Orchestrator) -> ExperimentTypesResponse:
        experiment_types = await orchestrator.experiments.get_experiment_types()
        return ExperimentTypesResponse(experiment_types=experiment_types)

    @get("/loaded")
    @handle_exceptions("Failed to get loaded experiments")
    async def get_loaded_experiments(self, orchestrator: Orchestrator) -> dict:
        return await orchestrator.loading.get_loaded()

    @get("/{experiment_type:str}/dynamic_params_template")
    @handle_exceptions("Failed to get dynamic parameters template")
    async def get_experiment_dynamic_params_template(self, experiment_type: str, orchestrator: Orchestrator) -> dict:
        return await orchestrator.experiments.get_experiment_dynamic_params_template(experiment_type)
