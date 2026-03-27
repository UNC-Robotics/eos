import asyncio
from typing import Any, ClassVar

import yaml

import pandas as pd
import ray
from ray.actor import ActorHandle
from sqlalchemy import delete, select

from eos.campaigns.entities.campaign import CampaignSample, CampaignSampleModel
from eos.campaigns.exceptions import EosCampaignExecutionError
from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.packages import EntityType
from eos.logging.logger import log
from eos.optimization.sequential_optimizer_actor import SequentialOptimizerActor
from eos.database.abstract_sql_db_interface import AsyncDbSession

import warnings

from eos.utils.di.di_container import inject

# Ignore warnings from bofire
warnings.filterwarnings("ignore", category=UserWarning, module="bofire.utils.cheminformatics")
warnings.filterwarnings("ignore", category=UserWarning, module="bofire.surrogates.xgb")
warnings.filterwarnings("ignore", category=UserWarning, module="bofire.strategies.predictives.enting")

_SNAPSHOT_SKIP_KEYS = {"ai_api_key", "protocol_context"}  # "protocol_context" is the optimizer constructor key


def serialize_value(v: Any) -> Any:
    """Recursively serialize a value for JSON storage."""
    if v is None or isinstance(v, str | int | float | bool):
        return v
    if hasattr(v, "model_dump"):
        return v.model_dump()
    if isinstance(v, list):
        return [serialize_value(item) for item in v]
    if isinstance(v, dict):
        return {k: serialize_value(val) for k, val in v.items()}
    if isinstance(v, set):
        return list(v)
    return v.value if hasattr(v, "value") else str(v)


def _serialize_config_snapshot(constructor_args: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-safe config snapshot from optimizer constructor args."""
    return {k: serialize_value(v) for k, v in constructor_args.items() if k not in _SNAPSHOT_SKIP_KEYS}


class CampaignOptimizerManager:
    """
    Responsible for managing the optimizers associated with campaign optimization.
    """

    @inject
    def __init__(self, configuration_manager: ConfigurationManager):
        self._configuration_manager = configuration_manager
        self._campaign_optimizer_plugin_registry = configuration_manager.campaign_optimizers
        self._optimizer_actors: dict[str, ActorHandle] = {}
        log.debug("Campaign optimizer manager initialized.")

    # Tier classification for optimizer parameter overrides
    _TIER1_RUNTIME_KEYS: ClassVar[set[str]] = {"p_bayesian", "p_ai", "ai_history_size", "ai_additional_context"}
    _TIER2_INIT_KEYS: ClassVar[set[str]] = {
        "ai_model",
        "ai_api_key",
        "ai_retries",
        "ai_model_settings",
        "num_initial_samples",
        "initial_sampling_method",
        "acquisition_function",
        "surrogate_specs",
    }
    _TIER3_DOMAIN_KEYS: ClassVar[set[str]] = {"inputs", "outputs", "constraints"}

    async def create_campaign_optimizer_actor(
        self,
        protocol: str,
        campaign_name: str,
        computer_ip: str,
        optimizer_overrides: dict[str, Any] | None = None,
        is_resume: bool = False,
        global_parameters: dict[str, dict[str, Any]] | None = None,
        protocol_run_parameters: list[dict[str, dict[str, Any]]] | None = None,
    ) -> tuple[ActorHandle, str, dict[str, Any]]:
        """
        Create a new campaign optimizer Ray actor with status check.

        :param protocol: The type of the protocol.
        :param campaign_name: The name of the campaign.
        :param computer_ip: The IP address of the optimizer computer on which the actor will run.
        :param optimizer_overrides: Optional parameter overrides from the UI.
        :param is_resume: Whether this is a resume (restricts which overrides are allowed).
        :raises TimeoutError: If the actor fails to respond within timeout
        :raises RuntimeError: If the actor creation or initialization fails
        :return: Tuple of (initialized optimizer actor, optimizer type name, final constructor args)
        """
        try:
            constructor_args, optimizer_type = (
                self._campaign_optimizer_plugin_registry.get_campaign_optimizer_creation_parameters(protocol)
            )
        except Exception as e:
            log.error(f"Failed to load optimizer configuration for protocol '{protocol}': {e}")
            raise EosCampaignExecutionError(
                f"Failed to load optimizer configuration for protocol '{protocol}': {e}"
            ) from e

        # Merge overrides into constructor args
        if optimizer_overrides:
            if is_resume:
                allowed_keys = self._TIER1_RUNTIME_KEYS | self._TIER2_INIT_KEYS
            else:
                allowed_keys = self._TIER1_RUNTIME_KEYS | self._TIER2_INIT_KEYS | self._TIER3_DOMAIN_KEYS

            for key, value in optimizer_overrides.items():
                if key in allowed_keys:
                    constructor_args[key] = value
                else:
                    log.warning(
                        f"Ignoring optimizer override '{key}' — not allowed "
                        f"{'on resume' if is_resume else 'at submission'}"
                    )

            # Keep p_bayesian + p_ai in sync
            if "p_bayesian" in optimizer_overrides and "p_ai" not in optimizer_overrides:
                constructor_args["p_ai"] = 1.0 - float(constructor_args["p_bayesian"])
            elif "p_ai" in optimizer_overrides and "p_bayesian" not in optimizer_overrides:
                constructor_args["p_bayesian"] = 1.0 - float(constructor_args["p_ai"])

        protocol_yaml = self._read_protocol_yaml(protocol)
        if protocol_yaml:
            if global_parameters:
                protocol_yaml = self._merge_params_into_yaml(protocol_yaml, global_parameters)
            constructor_args["protocol_context"] = protocol_yaml
        if protocol_run_parameters:
            constructor_args["protocol_run_parameters_schedule"] = protocol_run_parameters

        optimizer_type_name = optimizer_type.__name__

        # Build config snapshot (strip sensitive keys, serialize BoFire objects for JSON persistence)
        config_snapshot = _serialize_config_snapshot(constructor_args)

        resources = {"eos": 0.01} if computer_ip in ["localhost", "127.0.0.1"] else {f"node:{computer_ip}": 0.01}

        optimizer_actor = SequentialOptimizerActor.options(
            name=f"{campaign_name}_optimizer", resources=resources, max_concurrency=4
        ).remote(constructor_args, optimizer_type)

        await self._validate_optimizer_health(optimizer_actor)

        self._optimizer_actors[campaign_name] = optimizer_actor
        return optimizer_actor, optimizer_type_name, config_snapshot

    def get_optimizer_defaults(self, protocol: str) -> tuple[str, dict[str, Any]] | None:
        """Get optimizer type name and default constructor args for a protocol type."""
        try:
            # Ensure the optimizer plugin is loaded
            if protocol not in self._campaign_optimizer_plugin_registry.plugin_types:
                self._campaign_optimizer_plugin_registry.load_campaign_optimizer(protocol)
            result = self._campaign_optimizer_plugin_registry.get_campaign_optimizer_creation_parameters(protocol)
        except Exception:
            return None
        if result is None:
            return None
        constructor_args, optimizer_type = result
        safe_args = {k: v for k, v in constructor_args.items() if k not in _SNAPSHOT_SKIP_KEYS}
        return optimizer_type.__name__, safe_args

    def terminate_campaign_optimizer_actor(self, campaign_name: str) -> None:
        """
        Terminate the Ray actor associated with the optimizer for a campaign.

        :param campaign_name: The name of the campaign.
        """
        optimizer_actor = self._optimizer_actors.pop(campaign_name, None)

        if optimizer_actor is not None:
            ray.kill(optimizer_actor)

    def get_campaign_optimizer_actor(self, campaign_name: str) -> ActorHandle:
        """
        Get an existing Ray actor associated with the optimizer for a campaign.

        :param campaign_name: The name of the campaign.
        :return: The Ray actor associated with the optimizer.
        """
        return self._optimizer_actors[campaign_name]

    async def get_input_and_output_names(self, campaign_name: str) -> tuple[list[str], list[str], list[str]]:
        """
        Get the input, output, and additional parameter names from an optimizer associated with a campaign.

        :param campaign_name: The name of the campaign associated with the optimizer.
        :return: A tuple containing the input names, output names, and additional parameter names.
        """
        optimizer_actor = self._optimizer_actors[campaign_name]

        input_names, output_names, additional_parameters = await asyncio.gather(
            optimizer_actor.get_input_names.remote(),
            optimizer_actor.get_output_names.remote(),
            optimizer_actor.get_additional_parameters.remote(),
        )

        return input_names, output_names, additional_parameters

    async def record_campaign_samples(
        self,
        db: AsyncDbSession,
        campaign_name: str,
        protocol_run_names: list[str],
        inputs: pd.DataFrame,
        outputs: pd.DataFrame,
        meta_list: list[dict[str, Any]] | None = None,
    ) -> None:
        """
        Record one or more campaign samples (protocol run results) for the given campaign.
        Each sample is a data point for the optimizer to learn from.

        :param db: The database session
        :param campaign_name: The name of the campaign.
        :param protocol_run_names: The names of the protocols.
        :param inputs: The input data.
        :param outputs: The output data.
        :param meta_list: Optional per-sample metadata dicts.
        """
        inputs_dict = inputs.to_dict(orient="records")
        outputs_dict = outputs.to_dict(orient="records")

        campaign_samples = [
            CampaignSample(
                campaign_name=campaign_name,
                protocol_run_name=protocol_run_name,
                inputs=inputs_dict[i],
                outputs=outputs_dict[i],
                meta=meta_list[i] if meta_list else {},
            )
            for i, protocol_run_name in enumerate(protocol_run_names)
        ]

        db.add_all([CampaignSampleModel(**sample.model_dump()) for sample in campaign_samples])

    async def delete_campaign_samples(self, db: AsyncDbSession, campaign_name: str) -> None:
        """
        Delete all campaign samples for a campaign.

        :param db: The database session
        :param campaign_name: The name of the campaign.
        """
        await db.execute(delete(CampaignSampleModel).where(CampaignSampleModel.campaign_name == campaign_name))

    async def get_campaign_samples(
        self, db: AsyncDbSession, campaign_name: str, protocol_run_name: str | None = None
    ) -> list[CampaignSample]:
        """Get samples for a campaign, optionally filtered by protocol run."""
        stmt = select(CampaignSampleModel).where(CampaignSampleModel.campaign_name == campaign_name)
        if protocol_run_name:
            stmt = stmt.where(CampaignSampleModel.protocol_run_name == protocol_run_name)

        result = await db.execute(stmt)
        return [CampaignSample.model_validate(model) for model in result.scalars()]

    @staticmethod
    def _merge_params_into_yaml(yaml_str: str, global_parameters: dict[str, dict[str, Any]]) -> str:
        """
        Merge campaign global_parameters into the protocol YAML string.

        Overwrites default parameter values in each task so the AI agent sees
        the actual values that will be used at runtime.
        """
        data = yaml.safe_load(yaml_str)
        if not isinstance(data, dict) or "tasks" not in data:
            return yaml_str
        for task in data["tasks"]:
            task_name = task.get("name")
            if task_name and task_name in global_parameters:
                if "parameters" not in task:
                    task["parameters"] = {}
                task["parameters"].update(global_parameters[task_name])
        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    def _read_protocol_yaml(self, protocol: str) -> str | None:
        """Read the raw protocol YAML file for the given protocol type."""
        try:
            protocol_dir = self._configuration_manager.package_manager.get_entity_dir(protocol, EntityType.PROTOCOL)
            yaml_path = protocol_dir / "protocol.yml"
            if yaml_path.is_file():
                return yaml_path.read_text()
        except Exception:
            log.debug(f"Could not read protocol YAML for '{protocol}'", exc_info=True)
        return None

    async def _validate_optimizer_health(self, actor: ActorHandle) -> None:
        """Check the health of an actor by calling a method with a timeout."""
        try:
            async with asyncio.timeout(10.0):
                await actor.get_input_names.remote()
        except TimeoutError as e:
            ray.kill(actor)
            log.error("Optimizer actor initialization timed out after 10 seconds.")
            raise EosCampaignExecutionError("Optimizer actor initialization timed out.") from e
        except Exception as e:
            ray.kill(actor)
            log.error(f"Optimizer actor initialization failed: {e}")
            raise EosCampaignExecutionError(f"Optimizer actor initialization failed: {e}") from e
