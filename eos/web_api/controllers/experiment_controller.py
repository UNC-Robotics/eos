from typing import Any

from litestar import get, post, Controller
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
    ) -> dict[str, str]:
        """Submit a new experiment for execution."""
        await orchestrator.experiments.submit_experiment(db, data)
        return {"message": "Experiment submitted"}

    @post("/{experiment_name:str}/cancel")
    async def cancel_experiment(self, experiment_name: str, orchestrator: Orchestrator) -> dict[str, str]:
        """Cancel a running experiment (standalone or part of a campaign)."""
        # First try to cancel as a standalone experiment
        if experiment_name in orchestrator.experiments.submitted_experiments:
            await orchestrator.experiments.cancel_experiment(experiment_name)
            return {"message": "Experiment cancellation requested"}

        # Try to cancel as a campaign experiment (queues for cancellation in campaign's main loop)
        queued = await orchestrator.campaigns.cancel_campaign_experiment(experiment_name)
        if queued:
            return {"message": "Campaign experiment cancellation queued"}

        raise APIError(status_code=404, detail=f"Experiment '{experiment_name}' not found in running experiments")

    @get("/{experiment_name:str}")
    async def get_experiment(self, experiment_name: str, db: AsyncDbSession, orchestrator: Orchestrator) -> Experiment:
        """Get an experiment by name."""
        experiment = await orchestrator.experiments.get_experiment(db, experiment_name)

        if experiment is None:
            raise APIError(status_code=404, detail="Experiment not found")

        return experiment

    @get("/types")
    async def get_experiment_types(self, orchestrator: Orchestrator) -> dict[str, bool]:
        """List experiment types."""
        return await orchestrator.loading.list_experiments()

    @post("/load")
    async def load_experiments(
        self, data: ExperimentTypes, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> dict[str, str]:
        """Load experiment configurations."""
        await orchestrator.loading.load_experiments(db, set(data.experiment_types))
        return {"message": "Experiment configurations loaded"}

    @post("/unload")
    async def unload_experiments(
        self, data: ExperimentTypes, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> dict[str, str]:
        """Unload experiment configurations."""
        await orchestrator.loading.unload_experiments(db, set(data.experiment_types))
        return {"message": "Experiment configurations unloaded"}

    @post("/reload")
    async def reload_experiments(
        self, data: ExperimentTypes, db: AsyncDbSession, orchestrator: Orchestrator
    ) -> dict[str, str]:
        """Reload experiment configurations."""
        await orchestrator.loading.reload_experiments(db, set(data.experiment_types))
        return {"message": "Experiment configurations reloaded"}

    @get("/{experiment_type:str}/dynamic_params_template")
    async def get_dynamic_params_template(self, experiment_type: str, orchestrator: Orchestrator) -> dict[str, Any]:
        """Get dynamic parameters template for an experiment type."""
        return await orchestrator.experiments.get_experiment_dynamic_params_template(experiment_type)
