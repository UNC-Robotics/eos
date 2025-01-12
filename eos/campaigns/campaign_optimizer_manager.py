import asyncio

import pandas as pd
import ray
from ray.actor import ActorHandle
from sqlalchemy import delete, select

from eos.campaigns.entities.campaign import CampaignSample, CampaignSampleModel
from eos.campaigns.exceptions import EosCampaignError
from eos.configuration.configuration_manager import ConfigurationManager
from eos.logging.logger import log
from eos.optimization.sequential_optimizer_actor import SequentialOptimizerActor
from eos.database.abstract_sql_db_interface import AsyncDbSession

import warnings

from eos.utils.di.di_container import inject_all

# Ignore warnings from bofire
warnings.filterwarnings("ignore", category=UserWarning, module="bofire.utils.cheminformatics")
warnings.filterwarnings("ignore", category=UserWarning, module="bofire.surrogates.xgb")
warnings.filterwarnings("ignore", category=UserWarning, module="bofire.strategies.predictives.enting")


class CampaignOptimizerManager:
    """
    Responsible for managing the optimizers associated with experiment campaigns.
    """

    @inject_all
    def __init__(self, configuration_manager: ConfigurationManager):
        self._campaign_optimizer_plugin_registry = configuration_manager.campaign_optimizers
        self._optimizer_actors: dict[str, ActorHandle] = {}
        log.debug("Campaign optimizer manager initialized.")

    async def create_campaign_optimizer_actor(
        self, experiment_type: str, campaign_id: str, computer_ip: str
    ) -> ActorHandle:
        """
        Create a new campaign optimizer Ray actor with status check.

        :param experiment_type: The type of the experiment.
        :param campaign_id: The ID of the campaign.
        :param computer_ip: The IP address of the optimizer computer on which the actor will run.
        :raises TimeoutError: If the actor fails to respond within timeout
        :raises RuntimeError: If the actor creation or initialization fails
        :return: The initialized optimizer actor
        """
        constructor_args, optimizer_type = (
            self._campaign_optimizer_plugin_registry.get_campaign_optimizer_creation_parameters(experiment_type)
        )

        resources = {"eos-core": 0.01} if computer_ip in ["localhost", "127.0.0.1"] else {f"node:{computer_ip}": 0.01}

        optimizer_actor = SequentialOptimizerActor.options(name=f"{campaign_id}_optimizer", resources=resources).remote(
            constructor_args, optimizer_type
        )

        await self._validate_optimizer_health(optimizer_actor)

        self._optimizer_actors[campaign_id] = optimizer_actor
        return optimizer_actor

    def terminate_campaign_optimizer_actor(self, campaign_id: str) -> None:
        """
        Terminate the Ray actor associated with the optimizer for a campaign.

        :param campaign_id: The ID of the campaign.
        """
        optimizer_actor = self._optimizer_actors.pop(campaign_id, None)

        if optimizer_actor is not None:
            ray.kill(optimizer_actor)

    def get_campaign_optimizer_actor(self, campaign_id: str) -> ActorHandle:
        """
        Get an existing Ray actor associated with the optimizer for a campaign.

        :param campaign_id: The ID of the campaign.
        :return: The Ray actor associated with the optimizer.
        """
        return self._optimizer_actors[campaign_id]

    async def get_input_and_output_names(self, campaign_id: str) -> tuple[list[str], list[str]]:
        """
        Get the input and output names from an optimizer associated with a campaign.

        :param campaign_id: The ID of the campaign associated with the optimizer.
        :return: A tuple containing the input and output names.
        """
        optimizer_actor = self._optimizer_actors[campaign_id]

        input_names, output_names = await asyncio.gather(
            optimizer_actor.get_input_names.remote(), optimizer_actor.get_output_names.remote()
        )

        return input_names, output_names

    async def record_campaign_samples(
        self,
        db: AsyncDbSession,
        campaign_id: str,
        experiment_ids: list[str],
        inputs: pd.DataFrame,
        outputs: pd.DataFrame,
    ) -> None:
        """
        Record one or more campaign samples (experiment results) for the given campaign.
        Each sample is a data point for the optimizer to learn from.

        :param db: The database session
        :param campaign_id: The ID of the campaign.
        :param experiment_ids: The IDs of the experiments.
        :param inputs: The input data.
        :param outputs: The output data.
        """
        inputs_dict = inputs.to_dict(orient="records")
        outputs_dict = outputs.to_dict(orient="records")

        campaign_samples = [
            CampaignSample(
                campaign_id=campaign_id,
                experiment_id=experiment_id,
                inputs=inputs_dict[i],
                outputs=outputs_dict[i],
            )
            for i, experiment_id in enumerate(experiment_ids)
        ]

        db.add_all([CampaignSampleModel(**sample.model_dump()) for sample in campaign_samples])

    async def delete_campaign_samples(self, db: AsyncDbSession, campaign_id: str) -> None:
        """
        Delete all campaign samples for a campaign.

        :param db: The database session
        :param campaign_id: The ID of the campaign.
        """
        await db.execute(delete(CampaignSampleModel).where(CampaignSampleModel.campaign_id == campaign_id))

    async def get_campaign_samples(
        self, db: AsyncDbSession, campaign_id: str, experiment_id: str | None = None
    ) -> list[CampaignSample]:
        """Get samples for a campaign, optionally filtered by experiment."""
        stmt = select(CampaignSampleModel).where(CampaignSampleModel.campaign_id == campaign_id)
        if experiment_id:
            stmt = stmt.where(CampaignSampleModel.experiment_id == experiment_id)

        result = await db.execute(stmt)
        return [CampaignSample.model_validate(model) for model in result.scalars()]

    async def _validate_optimizer_health(self, actor: ActorHandle, timeout=10.0) -> None:
        """Check the health of an actor by calling a method with a timeout."""
        try:
            await asyncio.wait_for(actor.get_input_names.remote(), timeout=timeout)
        except asyncio.TimeoutError as e:
            ray.kill(actor)
            log.error(f"Optimizer actor initialization timed out after {timeout} seconds.")
            raise EosCampaignError("Optimizer actor initialization timed out.") from e
