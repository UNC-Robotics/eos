from typing import Any, ClassVar

from litestar import get, post, put, Controller
from pydantic import BaseModel, ConfigDict, Field

from eos.auth.authorization import require_role
from eos.auth.entities.user_role import Role
from eos.campaigns.campaign_optimizer_manager import serialize_value
from eos.campaigns.exceptions import EosCampaignExecutionError
from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer
from eos.optimization.beacon_optimizer import BeaconOptimizer
from eos.orchestration.orchestrator import Orchestrator
from eos.web_api.exception_handling import APIError


class InsightRequest(BaseModel):
    insight: str


class RuntimeParamsRequest(BaseModel):
    """
    Runtime-safe optimizer parameters. p_ai is derived as 1 - p_bayesian.

    Extra fields are allowed so custom optimizers can expose their own runtime parameters. They are
    validated against the running optimizer's actual runtime parameters.
    """

    model_config = ConfigDict(extra="allow")

    p_bayesian: float | None = Field(None, ge=0, le=1, description="Bayesian probability (p_ai = 1 - p_bayesian)")
    ai_history_size: int | None = Field(None, ge=1, description="Number of history entries for AI context")
    ai_additional_context: str | None = None


def _serialize_optimizer_defaults(
    optimizer_type_name: str,
    constructor_args: dict[str, Any],
    optimizer_type: type[AbstractSequentialOptimizer],
) -> dict[str, Any]:
    """Serialize optimizer defaults including BoFire domain objects to JSON-safe dicts."""
    param_schema = optimizer_type.eos_param_schema()
    params = {
        "p_bayesian": constructor_args.get("p_bayesian", 0.5),
        "p_ai": constructor_args.get("p_ai", 0.5),
        "ai_model": constructor_args.get("ai_model", ""),
        "ai_retries": constructor_args.get("ai_retries", 3),
        "ai_history_size": constructor_args.get("ai_history_size", 50),
        "ai_additional_context": constructor_args.get("ai_additional_context"),
        "num_initial_samples": constructor_args.get("num_initial_samples", 1),
        "initial_sampling_method": str(constructor_args.get("initial_sampling_method", "SOBOL")),
        "ai_model_settings": constructor_args.get("ai_model_settings"),
        "ai_additional_parameters": constructor_args.get("ai_additional_parameters"),
        "acquisition_function": serialize_value(constructor_args.get("acquisition_function")),
        "surrogate_specs": serialize_value(constructor_args.get("surrogate_specs")),
    }
    for field in param_schema:
        key = field["key"]
        params[key] = serialize_value(constructor_args.get(key, field.get("default")))

    return {
        "optimizer_type": optimizer_type_name,
        "is_beacon": issubclass(optimizer_type, BeaconOptimizer),
        "param_schema": param_schema,
        "inputs": [serialize_value(f) for f in constructor_args.get("inputs", [])],
        "outputs": [serialize_value(f) for f in constructor_args.get("outputs", [])],
        "constraints": [serialize_value(c) for c in constructor_args.get("constraints", [])],
        "params": params,
    }


class OptimizerController(Controller):
    """Controller for optimizer-related endpoints."""

    path = "/campaigns"
    guards: ClassVar = [require_role(Role.VIEWER)]

    @get("/optimizer/defaults/{protocol:str}")
    async def get_optimizer_defaults(
        self,
        protocol: str,
        orchestrator: Orchestrator,
    ) -> dict[str, Any]:
        """Get default optimizer parameters for a protocol type."""
        result = orchestrator.campaigns.get_optimizer_defaults(protocol)
        if result is None:
            raise APIError(status_code=404, detail=f"No optimizer found for protocol type '{protocol}'")
        optimizer_type_name, constructor_args, optimizer_type = result
        return _serialize_optimizer_defaults(optimizer_type_name, constructor_args, optimizer_type)

    @get("/{campaign_name:str}/optimizer/info")
    async def get_optimizer_info(
        self,
        campaign_name: str,
        orchestrator: Orchestrator,
    ) -> dict[str, Any]:
        """Get current optimizer state for a running campaign."""
        try:
            return await orchestrator.campaigns.get_optimizer_info(campaign_name)
        except EosCampaignExecutionError as e:
            raise APIError(status_code=404, detail=str(e)) from None

    @put("/{campaign_name:str}/optimizer/params", guards=[require_role(Role.SUBMITTER)])
    async def update_optimizer_params(
        self,
        campaign_name: str,
        data: RuntimeParamsRequest,
        orchestrator: Orchestrator,
    ) -> dict[str, str]:
        """Update runtime-safe optimizer parameters for a running campaign."""
        params = {k: v for k, v in data.model_dump().items() if v is not None}
        if not params:
            raise APIError(status_code=400, detail="No parameters provided")
        try:
            await orchestrator.campaigns.update_optimizer_params(campaign_name, params)
        except EosCampaignExecutionError as e:
            raise APIError(status_code=404, detail=str(e)) from None
        except ValueError as e:
            raise APIError(status_code=400, detail=str(e)) from None
        return {"message": "Parameters updated successfully"}

    @post("/{campaign_name:str}/optimizer/insight", guards=[require_role(Role.SUBMITTER)])
    async def add_insight(
        self,
        campaign_name: str,
        data: InsightRequest,
        orchestrator: Orchestrator,
    ) -> dict[str, str]:
        """Add an expert insight to a campaign's optimizer."""
        try:
            await orchestrator.campaigns.add_optimizer_insight(campaign_name, data.insight)
        except EosCampaignExecutionError as e:
            raise APIError(status_code=404, detail=str(e)) from None
        return {"message": "Insight added successfully"}
