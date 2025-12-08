import asyncio

import pandas as pd
import ray
from ray.actor import ActorHandle
from sqlalchemy import delete, select

from eos.campaigns.entities.campaign import CampaignSample, CampaignSampleModel
from eos.campaigns.exceptions import EosCampaignExecutionError
from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log
from eos.optimization.sequential_optimizer_actor import SequentialOptimizerActor
from eos.database.abstract_sql_db_interface import AsyncDbSession

import warnings

from eos.utils.di.di_container import inject

# Ignore warnings from bofire
warnings.filterwarnings("ignore", category=UserWarning, module="bofire.utils.cheminformatics")
warnings.filterwarnings("ignore", category=UserWarning, module="bofire.surrogates.xgb")
warnings.filterwarnings("ignore", category=UserWarning, module="bofire.strategies.predictives.enting")


class CampaignOptimizerManager:
    """
    Responsible for managing the optimizers associated with experiment campaigns.
    """

    @inject
    def __init__(self, configuration_manager: ConfigurationManager):
        self._campaign_optimizer_plugin_registry = configuration_manager.campaign_optimizers
        self._optimizer_actors: dict[str, ActorHandle] = {}
        log.debug("Campaign optimizer manager initialized.")

    async def create_campaign_optimizer_actor(
        self, experiment_type: str, campaign_name: str, computer_ip: str
    ) -> ActorHandle:
        """
        Create a new campaign optimizer Ray actor with status check.

        :param experiment_type: The type of the experiment.
        :param campaign_name: The name of the campaign.
        :param computer_ip: The IP address of the optimizer computer on which the actor will run.
        :raises TimeoutError: If the actor fails to respond within timeout
        :raises RuntimeError: If the actor creation or initialization fails
        :return: The initialized optimizer actor
        """
        try:
            constructor_args, optimizer_type = (
                self._campaign_optimizer_plugin_registry.get_campaign_optimizer_creation_parameters(experiment_type)
            )
        except Exception as e:
            log.error(f"Failed to load optimizer configuration for experiment type '{experiment_type}': {e}")
            raise EosCampaignExecutionError(
                f"Failed to load optimizer configuration for experiment type '{experiment_type}': {e}"
            ) from e

        resources = {"eos": 0.01} if computer_ip in ["localhost", "127.0.0.1"] else {f"node:{computer_ip}": 0.01}

        optimizer_actor = SequentialOptimizerActor.options(
            name=f"{campaign_name}_optimizer", resources=resources
        ).remote(constructor_args, optimizer_type)

        await self._validate_optimizer_health(optimizer_actor)

        self._optimizer_actors[campaign_name] = optimizer_actor
        return optimizer_actor

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

    async def get_input_and_output_names(self, campaign_name: str) -> tuple[list[str], list[str]]:
        """
        Get the input and output names from an optimizer associated with a campaign.

        :param campaign_name: The name of the campaign associated with the optimizer.
        :return: A tuple containing the input and output names.
        """
        optimizer_actor = self._optimizer_actors[campaign_name]

        input_names, output_names = await asyncio.gather(
            optimizer_actor.get_input_names.remote(), optimizer_actor.get_output_names.remote()
        )

        return input_names, output_names

    async def record_campaign_samples(
        self,
        db: AsyncDbSession,
        campaign_name: str,
        experiment_names: list[str],
        inputs: pd.DataFrame,
        outputs: pd.DataFrame,
    ) -> None:
        """
        Record one or more campaign samples (experiment results) for the given campaign.
        Each sample is a data point for the optimizer to learn from.

        :param db: The database session
        :param campaign_name: The name of the campaign.
        :param experiment_names: The names of the experiments.
        :param inputs: The input data.
        :param outputs: The output data.
        """
        inputs_dict = inputs.to_dict(orient="records")
        outputs_dict = outputs.to_dict(orient="records")

        campaign_samples = [
            CampaignSample(
                campaign_name=campaign_name,
                experiment_name=experiment_name,
                inputs=inputs_dict[i],
                outputs=outputs_dict[i],
            )
            for i, experiment_name in enumerate(experiment_names)
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
        self, db: AsyncDbSession, campaign_name: str, experiment_name: str | None = None
    ) -> list[CampaignSample]:
        """Get samples for a campaign, optionally filtered by experiment."""
        stmt = select(CampaignSampleModel).where(CampaignSampleModel.campaign_name == campaign_name)
        if experiment_name:
            stmt = stmt.where(CampaignSampleModel.experiment_name == experiment_name)

        result = await db.execute(stmt)
        return [CampaignSample.model_validate(model) for model in result.scalars()]

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
