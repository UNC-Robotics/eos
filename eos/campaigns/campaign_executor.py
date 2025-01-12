import asyncio
from typing import Any, TYPE_CHECKING

import pandas as pd
from ray.actor import ActorHandle

from eos.campaigns.campaign_manager import CampaignManager
from eos.campaigns.campaign_optimizer_manager import CampaignOptimizerManager
from eos.campaigns.entities.campaign import CampaignStatus, Campaign, CampaignDefinition
from eos.campaigns.exceptions import EosCampaignExecutionError
from eos.experiments.entities.experiment import ExperimentStatus, ExperimentDefinition
from eos.experiments.exceptions import EosExperimentCancellationError, EosExperimentExecutionError
from eos.experiments.experiment_executor_factory import ExperimentExecutorFactory
from eos.logging.logger import log
from eos.database.abstract_sql_db_interface import AsyncDbSession, AbstractSqlDbInterface
from eos.tasks.task_manager import TaskManager
from eos.utils import dict_utils

if TYPE_CHECKING:
    from eos.experiments.experiment_executor import ExperimentExecutor


class CampaignExecutor:
    def __init__(
        self,
        campaign_definition: CampaignDefinition,
        campaign_manager: CampaignManager,
        campaign_optimizer_manager: CampaignOptimizerManager,
        task_manager: TaskManager,
        experiment_executor_factory: ExperimentExecutorFactory,
        db_interface: AbstractSqlDbInterface,
    ):
        self._campaign_definition = campaign_definition
        self._campaign_manager = campaign_manager
        self._campaign_optimizer_manager = campaign_optimizer_manager
        self._task_manager = task_manager
        self._experiment_executor_factory = experiment_executor_factory
        self._db_interface = db_interface

        # Campaign state
        self._campaign_id = campaign_definition.id
        self._experiment_type = campaign_definition.experiment_type
        self._campaign_status: CampaignStatus | None = None
        self._experiment_executors: dict[str, ExperimentExecutor] = {}

        # Optimizer state
        self._optimizer: ActorHandle | None = None
        self._optimizer_input_names: list[str] = []
        self._optimizer_output_names: list[str] = []

    async def start_campaign(self, db: AsyncDbSession) -> None:
        """Initialize and start a new campaign or resume an existing one."""
        campaign = await self._campaign_manager.get_campaign(db, self._campaign_id)

        if campaign:
            await self._handle_existing_campaign(db, campaign)
        else:
            await self._initialize_new_campaign(db)

        await self._campaign_manager.start_campaign(db, self._campaign_id)
        await db.flush()

        self._campaign_status = CampaignStatus.RUNNING
        log.info(f"Started campaign '{self._campaign_id}'")

    async def _initialize_new_campaign(self, db: AsyncDbSession) -> None:
        """Create and initialize a new campaign."""
        await self._campaign_manager.create_campaign(db, self._campaign_definition)

        if self._campaign_definition.optimize:
            await self._initialize_optimizer()

    async def _handle_existing_campaign(self, db: AsyncDbSession, campaign: Campaign) -> None:
        """Handle resuming or rejecting an existing campaign based on its state."""
        self._campaign_status = campaign.status

        if not self._campaign_definition.resume:
            self._validate_campaign_resumption(campaign.status)

        await self._resume_campaign(db)

    def _validate_campaign_resumption(self, status: CampaignStatus) -> None:
        """Validate if a campaign can be resumed based on its status."""
        invalid_statuses = {
            CampaignStatus.COMPLETED: "completed",
            CampaignStatus.SUSPENDED: "suspended",
            CampaignStatus.CANCELLED: "cancelled",
            CampaignStatus.FAILED: "failed",
        }

        if status in invalid_statuses:
            raise EosCampaignExecutionError(
                f"Cannot start campaign '{self._campaign_id}' as it already exists and is "
                f"'{invalid_statuses[status]}'. Please create a new campaign or re-submit "
                f"with 'resume=True'."
            )

    async def _resume_campaign(self, db: AsyncDbSession) -> None:
        """Resume an existing campaign by restoring its state."""
        await self._campaign_manager.delete_current_campaign_experiments(db, self._campaign_id)

        if self._campaign_definition.optimize:
            await self._initialize_optimizer()
            await self._restore_optimizer_state(db)

        log.info(f"Campaign '{self._campaign_id}' resumed")

    async def _initialize_optimizer(self) -> None:
        """Initialize the campaign optimizer if not already initialized."""
        if self._optimizer:
            return

        log.info(f"Creating optimizer for campaign '{self._campaign_id}'...")
        self._optimizer = await self._campaign_optimizer_manager.create_campaign_optimizer_actor(
            self._experiment_type,
            self._campaign_id,
            self._campaign_definition.optimizer_computer_ip,
        )

        self._optimizer_input_names, self._optimizer_output_names = (
            await self._campaign_optimizer_manager.get_input_and_output_names(self._campaign_id)
        )

    async def progress_campaign(self) -> bool:
        """
        Progress the campaign by executing experiments and managing campaign state.

        :return: True if the campaign is completed, False otherwise.
        """
        try:
            if self._campaign_status != CampaignStatus.RUNNING:
                return self._campaign_status == CampaignStatus.CANCELLED

            # Progress existing experiments
            await self._progress_experiments()

            async with self._db_interface.get_async_session() as db:
                # Check campaign completion
                campaign = await self._campaign_manager.get_campaign(db, self._campaign_id)
                if self._is_campaign_completed(campaign):
                    await self._complete_campaign(db)
                    return True

                # Create new experiments if possible
                await self._create_experiments(db, campaign)
                return False

        except EosExperimentExecutionError as e:
            await self._handle_campaign_failure(e)
            return False

    async def _progress_experiments(self) -> None:
        """Progress all running experiments and process completed ones."""
        completed_experiments = []
        for exp_id, executor in self._experiment_executors.items():
            async with self._db_interface.get_async_session() as db:
                complete = await executor.progress_experiment(db)
                if complete:
                    completed_experiments.append(exp_id)

        if completed_experiments:
            if self._campaign_definition.optimize:
                async with self._db_interface.get_async_session() as db:
                    await self._process_results_for_optimization(db, completed_experiments)

            await self._cleanup_completed_experiments(completed_experiments)

    async def _process_completed_experiments(self, db: AsyncDbSession, completed_experiments: list[str]) -> None:
        """Process results from completed experiments to update the optimization."""
        inputs_df, outputs_df = await self._collect_experiment_results(db, completed_experiments)
        await self._optimizer.report.remote(inputs_df, outputs_df)
        await self._campaign_optimizer_manager.record_campaign_samples(
            db, self._campaign_id, completed_experiments, inputs_df, outputs_df
        )

    async def _cleanup_completed_experiments(self, completed_experiments: list[str]) -> None:
        """Clean up completed experiments and update campaign state."""
        for exp_id in completed_experiments:
            async with self._db_interface.get_async_session() as db:
                await self._campaign_manager.delete_campaign_experiment(db, self._campaign_id, exp_id)
                await self._campaign_manager.increment_iteration(db, self._campaign_id)
            del self._experiment_executors[exp_id]

    async def cancel_campaign(self) -> None:
        """Cancel the campaign and all running experiments."""
        async with self._db_interface.get_async_session() as db:
            campaign = await self._campaign_manager.get_campaign(db, self._campaign_id)
            if not campaign or campaign.status != CampaignStatus.RUNNING:
                raise EosCampaignExecutionError(
                    f"Cannot cancel campaign '{self._campaign_id}' with status "
                    f"'{campaign.status if campaign else 'None'}'. It must be running."
                )

            log.warning(f"Cancelling campaign '{self._campaign_id}'...")
            await self._campaign_manager.cancel_campaign(db, self._campaign_id)
            self._campaign_status = CampaignStatus.CANCELLED

        await self._cancel_running_experiments()

        self._experiment_executors.clear()

        log.warning(f"Cancelled campaign '{self._campaign_id}'")

    async def _cancel_running_experiments(self) -> None:
        """Cancel all running experiments sequentially with individual timeouts."""
        failed_cancellations = []

        for exp_id, executor in self._experiment_executors.items():
            try:
                await asyncio.wait_for(executor.cancel_experiment(), timeout=15)
            except asyncio.TimeoutError:
                failed_cancellations.append((exp_id, "timeout"))
                log.warning(f"CMP '{self._campaign_id}' - Timeout while cancelling experiment '{exp_id}'")
            except EosExperimentCancellationError as e:
                failed_cancellations.append((exp_id, str(e)))
                log.warning(f"CMP '{self._campaign_id}' - Error cancelling experiment '{exp_id}': {e}")

        if failed_cancellations:
            failed_details = "\n".join(f"- {exp_id}: {reason}" for exp_id, reason in failed_cancellations)
            raise EosCampaignExecutionError(
                f"CMP '{self._campaign_id}' - Failed to cancel {len(failed_cancellations)} "
                f"experiments:\n{failed_details}"
            )

    def cleanup(self) -> None:
        """Clean up resources when campaign executor is no longer needed."""
        if self._campaign_definition.optimize:
            self._campaign_optimizer_manager.terminate_campaign_optimizer_actor(self._campaign_id)

    async def _create_experiments(self, db: AsyncDbSession, campaign: Campaign) -> None:
        """Create new experiments up to the maximum allowed concurrent experiments."""
        while self._can_create_more_experiments(campaign):
            iteration = campaign.experiments_completed + len(self._experiment_executors)
            experiment_id = f"{self._campaign_id}_exp_{iteration + 1}"

            parameters = await self._get_experiment_parameters(iteration)
            await self._create_single_experiment(db, experiment_id, parameters)

    async def _create_single_experiment(
        self, db: AsyncDbSession, experiment_id: str, parameters: dict[str, Any]
    ) -> None:
        """Create and start a single experiment."""
        experiment_definition = ExperimentDefinition(
            id=experiment_id,
            type=self._experiment_type,
            owner=self._campaign_id,
            priority=self._campaign_definition.priority,
            dynamic_parameters=parameters,
        )

        experiment_executor = self._experiment_executor_factory.create(experiment_definition)
        await self._campaign_manager.add_campaign_experiment(db, self._campaign_id, experiment_id)
        self._experiment_executors[experiment_id] = experiment_executor
        await experiment_executor.start_experiment(db)

    def _can_create_more_experiments(self, campaign: Campaign) -> bool:
        """Check if more experiments can be created based on campaign constraints."""
        num_executors = len(self._experiment_executors)
        max_concurrent = self._campaign_definition.max_concurrent_experiments
        max_total = self._campaign_definition.max_experiments
        current_total = campaign.experiments_completed + num_executors

        return num_executors < max_concurrent and (max_total == 0 or current_total < max_total)

    async def _get_experiment_parameters(self, iteration: int) -> dict[str, Any]:
        """Get parameters for a new experiment from campaign definition or optimizer."""
        if self._campaign_definition.dynamic_parameters and iteration < len(
            self._campaign_definition.dynamic_parameters
        ):
            return self._campaign_definition.dynamic_parameters[iteration]

        if self._campaign_definition.optimize:
            log.info(f"CMP '{self._campaign_id}' - Sampling new parameters...")
            new_parameters = await self._optimizer.sample.remote(1)
            new_parameters = new_parameters.to_dict(orient="records")[0]
            log.debug(f"CMP '{self._campaign_id}' - Sampled parameters: {new_parameters}")
            return dict_utils.unflatten_dict(new_parameters)

        raise EosCampaignExecutionError(
            f"CMP '{self._campaign_id}' - No dynamic parameters provided for iteration {iteration}"
        )

    def _is_campaign_completed(self, campaign: Campaign) -> bool:
        """Check if campaign has completed all experiments."""
        max_experiments = self._campaign_definition.max_experiments
        return (
            max_experiments > 0
            and campaign.experiments_completed >= max_experiments
            and len(self._experiment_executors) == 0
        )

    async def _complete_campaign(self, db: AsyncDbSession) -> None:
        """Complete the campaign and compute final results."""
        if self._campaign_definition.optimize:
            await self._compute_pareto_solutions(db)
        await self._campaign_manager.complete_campaign(db, self._campaign_id)

    async def _handle_campaign_failure(self, error: Exception) -> None:
        """Handle campaign failure by updating status and raising error."""
        async with self._db_interface.get_async_session() as db:
            await self._campaign_manager.fail_campaign(db, self._campaign_id)
        self._campaign_status = CampaignStatus.FAILED
        raise EosCampaignExecutionError(f"Error executing campaign '{self._campaign_id}'") from error

    async def _compute_pareto_solutions(self, db: AsyncDbSession) -> None:
        """Compute and store Pareto optimal solutions."""
        log.info(f"Computing Pareto solutions for campaign '{self._campaign_id}'...")
        try:
            pareto_solutions_df = await self._optimizer.get_optimal_solutions.remote()
            pareto_solutions = pareto_solutions_df.to_dict(orient="records")
            await self._campaign_manager.set_pareto_solutions(db, self._campaign_id, pareto_solutions)
        except Exception as e:
            raise EosCampaignExecutionError(f"CMP '{self._campaign_id}' - Error computing Pareto solutions") from e

    async def _restore_optimizer_state(self, db: AsyncDbSession) -> None:
        """
        Restore the optimizer state for a resumed campaign.
        """
        completed_experiment_ids = await self._campaign_manager.get_campaign_experiment_ids(
            db, self._campaign_id, status=ExperimentStatus.COMPLETED
        )

        inputs_df, outputs_df = await self._collect_experiment_results(db, completed_experiment_ids)

        await self._optimizer.report.remote(inputs_df, outputs_df)

        log.info(
            f"CMP '{self._campaign_id}' - Restored optimizer state from {len(completed_experiment_ids)} "
            f"completed experiments."
        )

    async def _collect_experiment_results(
        self, db: AsyncDbSession, experiment_ids: list[str]
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Collect the results of completed experiments.
        """
        inputs = {input_name: [] for input_name in self._optimizer_input_names}
        outputs = {output_name: [] for output_name in self._optimizer_output_names}

        for experiment_id in experiment_ids:
            for input_name in self._optimizer_input_names:
                reference_task_id, parameter_name = input_name.split(".")
                task = await self._task_manager.get_task(db, experiment_id, reference_task_id)
                inputs[input_name].append(float(task.input_parameters[parameter_name]))
            for output_name in self._optimizer_output_names:
                reference_task_id, parameter_name = output_name.split(".")
                task = await self._task_manager.get_task(db, experiment_id, reference_task_id)
                outputs[output_name].append(float(task.output_parameters[parameter_name]))

        return pd.DataFrame(inputs), pd.DataFrame(outputs)

    async def _process_results_for_optimization(self, db: AsyncDbSession, completed_experiments: list[str]) -> None:
        """
        Process the results of completed experiments.
        """
        inputs_df, outputs_df = await self._collect_experiment_results(db, completed_experiments)
        await self._optimizer.report.remote(inputs_df, outputs_df)
        await self._campaign_optimizer_manager.record_campaign_samples(
            db, self._campaign_id, completed_experiments, inputs_df, outputs_df
        )

    @property
    def optimizer(self) -> ActorHandle | None:
        """Get the campaign optimizer actor handle."""
        return self._optimizer

    @property
    def campaign_definition(self) -> CampaignDefinition:
        """Get the campaign definition."""
        return self._campaign_definition
