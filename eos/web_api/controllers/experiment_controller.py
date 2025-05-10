from typing import Any

from litestar import get, post, put, Controller, Response
from pydantic import BaseModel

from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.experiments.entities.experiment import ExperimentDefinition, Experiment
from eos.orchestration.orchestrator import Orchestrator
from eos.web_api.exception_handling import APIError


class ExperimentTypes(BaseModel):
    experiment_types: list[str]


class ExperimentTypesResponse(BaseModel):
    experiment_types: list[str]


class ExperimentController(Controller):
    """Controller for experiment-related endpoints."""

    path = "/experiments"

    @post("/")
    async def submit_experiment(
        self, data: ExperimentDefinition, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> Response:
        """Submit a new experiment for execution."""
        await orchestrator.experiments.submit_experiment(db, data)
        return Response(content="Submitted", status_code=201)

    @post("/{experiment_id:str}/cancel")
    async def cancel_experiment(self, experiment_id: str, orchestrator: Orchestrator) -> Response:
        """Cancel a running experiment."""
        await orchestrator.experiments.cancel_experiment(experiment_id)
        return Response(content="Cancellation request submitted.", status_code=202)

    @get("/{experiment_id:str}")
    async def get_experiment(self, experiment_id: str, db: AsyncDbSession, orchestrator: Orchestrator) -> Experiment:
        """Get an experiment by ID."""
        experiment = await orchestrator.experiments.get_experiment(db, experiment_id)

        if experiment is None:
            raise APIError(status_code=404, detail="Experiment not found")

        return experiment

    @get("/types")
    async def get_experiment_types(self, orchestrator: Orchestrator) -> dict[str, bool]:
        """List experiment types."""
        return await orchestrator.loading.list_experiments()

    @post("/load")
    async def load_experiments(self, data: ExperimentTypes, orchestrator: Orchestrator) -> Response:
        """Load experiment configurations."""
        await orchestrator.loading.load_experiments(set(data.experiment_types))
        return Response(content="OK", status_code=200)

    @post("/unload")
    async def unload_experiments(
        self, data: ExperimentTypes, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> Response:
        """Unload experiment configurations."""
        await orchestrator.loading.unload_experiments(db, set(data.experiment_types))
        return Response(content="OK", status_code=200)

    @put("/reload")
    async def reload_experiments(
        self, data: ExperimentTypes, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> Response:
        """Reload experiment configurations."""
        await orchestrator.loading.reload_experiments(db, set(data.experiment_types))
        return Response(content="OK", status_code=200)

    @get("/{experiment_type:str}/dynamic_params_template")
    async def get_dynamic_params_template(self, experiment_type: str, orchestrator: Orchestrator) -> dict[str, Any]:
        """Get dynamic parameters template for an experiment type."""
        return await orchestrator.experiments.get_experiment_dynamic_params_template(experiment_type)
