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
    ):
        self._campaign_definition = campaign_definition

        self._campaign_id = campaign_definition.id
        self._experiment_type = campaign_definition.experiment_type

        self._campaign_manager = campaign_manager
        self._campaign_optimizer_manager = campaign_optimizer_manager
        self._task_manager = task_manager
        self._experiment_executor_factory = experiment_executor_factory

        self._optimizer: ActorHandle | None = None
        self._optimizer_input_names: list[str] = []
        self._optimizer_output_names: list[str] = []

        self._experiment_executors: dict[str, ExperimentExecutor] = {}

        self._campaign_status: CampaignStatus | None = None

    async def _setup_optimizer(self) -> None:
        if self._optimizer:
            return

        self._optimizer = self._campaign_optimizer_manager.create_campaign_optimizer_actor(
            self._experiment_type,
            self._campaign_id,
            self._campaign_definition.optimizer_computer_ip,
        )
        self._optimizer_input_names, self._optimizer_output_names = (
            await self._campaign_optimizer_manager.get_input_and_output_names(self._campaign_id)
        )

    def cleanup(self) -> None:
        """
        Clean up resources when the campaign executor is no longer needed.
        """
        if self._campaign_definition.optimize:
            self._campaign_optimizer_manager.terminate_campaign_optimizer_actor(self._campaign_id)

    async def start_campaign(self) -> None:
        """
        Start the campaign or handle an existing campaign.
        """
        campaign = await self._campaign_manager.get_campaign(self._campaign_id)
        if campaign:
            await self._handle_existing_campaign(campaign)
        else:
            await self._create_new_campaign()

        await self._campaign_manager.start_campaign(self._campaign_id)
        self._campaign_status = CampaignStatus.RUNNING
        log.info(f"Started campaign '{self._campaign_id}'.")

    async def _handle_existing_campaign(self, campaign: Campaign) -> None:
        """
        Handle cases when the campaign already exists.
        """
        self._campaign_status = campaign.status

        if not self._campaign_definition.resume:

            def _raise_error(status: str) -> None:
                raise EosCampaignExecutionError(
                    f"Cannot start campaign '{self._campaign_id}' as it already exists and is '{status}'. "
                    f"Please create a new campaign or re-submit with 'resume=True'."
                )

            status_handlers = {
                CampaignStatus.COMPLETED: lambda: _raise_error("completed"),
                CampaignStatus.SUSPENDED: lambda: _raise_error("suspended"),
                CampaignStatus.CANCELLED: lambda: _raise_error("cancelled"),
                CampaignStatus.FAILED: lambda: _raise_error("failed"),
            }
            status_handlers.get(self._campaign_status, lambda: None)()

        await self._resume_campaign()

    async def _create_new_campaign(self) -> None:
        """
        Create a new campaign.
        """
        await self._campaign_manager.create_campaign(self._campaign_definition)

        if self._campaign_definition.optimize:
            await self._setup_optimizer()

    async def _resume_campaign(self) -> None:
        """
        Resume an existing campaign.
        """
        await self._campaign_manager.delete_current_campaign_experiments(self._campaign_id)

        if self._campaign_definition.optimize:
            await self._setup_optimizer()
            await self._restore_optimizer_state()

        log.info(f"Campaign '{self._campaign_id}' resumed.")

    async def _restore_optimizer_state(self) -> None:
        """
        Restore the optimizer state for a resumed campaign.
        """
        completed_experiment_ids = await self._campaign_manager.get_campaign_experiment_ids(
            self._campaign_id, status=ExperimentStatus.COMPLETED
        )

        inputs_df, outputs_df = await self._collect_experiment_results(completed_experiment_ids)

        await self._optimizer.report.remote(inputs_df, outputs_df)

        log.info(
            f"CMP '{self._campaign_id}' - Restored optimizer state with {len(completed_experiment_ids)} "
            f"completed experiments."
        )

    async def cancel_campaign(self) -> None:
        """
        Cancel the campaign and all running experiments.
        """
        campaign = await self._campaign_manager.get_campaign(self._campaign_id)
        if not campaign or campaign.status != CampaignStatus.RUNNING:
            raise EosCampaignExecutionError(
                f"Cannot cancel campaign '{self._campaign_id}' with status "
                f"'{campaign.status if campaign else 'None'}'. It must be running."
            )

        log.warning(f"Cancelling campaign '{self._campaign_id}'...")
        await self._campaign_manager.cancel_campaign(self._campaign_id)
        self._campaign_status = CampaignStatus.CANCELLED

        await self._cancel_running_experiments()
        self._experiment_executors.clear()

        log.warning(f"Cancelled campaign '{self._campaign_id}'.")

    async def _cancel_running_experiments(self) -> None:
        """
        Cancel all running experiments in the campaign.
        """
        cancellation_tasks = [executor.cancel_experiment() for executor in self._experiment_executors.values()]
        try:
            await asyncio.wait_for(asyncio.gather(*cancellation_tasks, return_exceptions=True), timeout=15)
        except asyncio.TimeoutError as e:
            raise EosCampaignExecutionError(
                f"CMP '{self._campaign_id}' - Timed out while cancelling experiments. "
                f"Some experiments may still be running."
            ) from e
        except EosExperimentCancellationError as e:
            raise EosCampaignExecutionError(
                f"CMP '{self._campaign_id}' - Error cancelling experiments. Some experiments may still be running."
            ) from e

    async def progress_campaign(self) -> bool:
        """
        Progress the campaign by executing experiments.
        Returns True if the campaign is completed, False otherwise.
        """
        try:
            if self._campaign_status != CampaignStatus.RUNNING:
                return self._campaign_status == CampaignStatus.CANCELLED

            await self._progress_experiments()

            campaign = await self._campaign_manager.get_campaign(self._campaign_id)
            if self._is_campaign_completed(campaign):
                if self._campaign_definition.optimize:
                    await self._compute_pareto_solutions()
                await self._campaign_manager.complete_campaign(self._campaign_id)
                return True

            await self._create_experiments(campaign)

            return False
        except EosExperimentExecutionError as e:
            await self._campaign_manager.fail_campaign(self._campaign_id)
            self._campaign_status = CampaignStatus.FAILED
            raise EosCampaignExecutionError(f"Error executing campaign '{self._campaign_id}'") from e

    async def _progress_experiments(self) -> None:
        """
        Progress all running experiments sequentially and process completed ones.
        """
        completed_experiments = []

        for experiment_id, executor in self._experiment_executors.items():
            is_completed = await executor.progress_experiment()
            if is_completed:
                completed_experiments.append(experiment_id)

        if self._campaign_definition.optimize and completed_experiments:
            await self._process_completed_experiments(completed_experiments)

        for experiment_id in completed_experiments:
            del self._experiment_executors[experiment_id]
            await self._campaign_manager.delete_campaign_experiment(self._campaign_id, experiment_id)
            await self._campaign_manager.increment_iteration(self._campaign_id)

    async def _process_completed_experiments(self, completed_experiments: list[str]) -> None:
        """
        Process the results of completed experiments.
        """
        inputs_df, outputs_df = await self._collect_experiment_results(completed_experiments)
        await self._optimizer.report.remote(inputs_df, outputs_df)
        await self._campaign_optimizer_manager.record_campaign_samples(
            self._campaign_id, completed_experiments, inputs_df, outputs_df
        )

    async def _collect_experiment_results(self, experiment_ids: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Collect the results of completed experiments.
        """
        inputs = {input_name: [] for input_name in self._optimizer_input_names}
        outputs = {output_name: [] for output_name in self._optimizer_output_names}

        for experiment_id in experiment_ids:
            for input_name in self._optimizer_input_names:
                reference_task_id, parameter_name = input_name.split(".")
                task = await self._task_manager.get_task(experiment_id, reference_task_id)
                inputs[input_name].append(float(task.input.parameters[parameter_name]))
            for output_name in self._optimizer_output_names:
                reference_task_id, parameter_name = output_name.split(".")
                task_output = await self._task_manager.get_task_output(experiment_id, reference_task_id)
                output_parameters = task_output.parameters
                outputs[output_name].append(float(output_parameters[parameter_name]))

        return pd.DataFrame(inputs), pd.DataFrame(outputs)

    async def _create_experiments(self, campaign: Campaign) -> None:
        """
        Create new experiments if possible.
        """
        while self._can_create_more_experiments(campaign):
            iteration = campaign.experiments_completed + len(self._experiment_executors)
            new_experiment_id = f"{self._campaign_id}_exp_{iteration + 1}"

            experiment_dynamic_parameters = await self._get_experiment_parameters(iteration)

            experiment_definition = ExperimentDefinition(
                id=new_experiment_id,
                type=self._experiment_type,
                dynamic_parameters=experiment_dynamic_parameters,
            )
            experiment_executor = self._experiment_executor_factory.create(experiment_definition)

            await self._campaign_manager.add_campaign_experiment(self._campaign_id, new_experiment_id)
            self._experiment_executors[new_experiment_id] = experiment_executor
            await experiment_executor.start_experiment()

    async def _get_experiment_parameters(self, iteration: int) -> dict[str, Any]:
        """
        Get parameters for a new experiment.
        """
        campaign_dynamic_parameters = self._campaign_definition.dynamic_parameters

        if campaign_dynamic_parameters and len(campaign_dynamic_parameters) > iteration:
            return campaign_dynamic_parameters[iteration]
        if self._campaign_definition.optimize:
            log.info(f"CMP '{self._campaign_id}' - Sampling new parameters from the optimizer...")
            new_parameters = await self._optimizer.sample.remote(1)
            new_parameters = new_parameters.to_dict(orient="records")[0]
            log.debug(f"CMP '{self._campaign_id}' - Sampled parameters: {new_parameters}")
            return dict_utils.unflatten_dict(new_parameters)

        raise EosCampaignExecutionError(
            f"CMP '{self._campaign_id}' - No dynamic parameters provided for iteration {iteration}."
        )

    def _can_create_more_experiments(self, campaign: Campaign) -> bool:
        """
        Check if more experiments can be created.
        """
        num_executors = len(self._experiment_executors)
        max_concurrent = self._campaign_definition.max_concurrent_experiments
        max_total = self._campaign_definition.max_experiments
        current_total = campaign.experiments_completed + num_executors

        return num_executors < max_concurrent and (max_total == 0 or current_total < max_total)

    def _is_campaign_completed(self, campaign: Campaign) -> bool:
        """
        Check if the campaign is completed.
        """
        max_experiments = self._campaign_definition.max_experiments
        return (
            max_experiments > 0
            and campaign.experiments_completed >= max_experiments
            and len(self._experiment_executors) == 0
        )

    async def _compute_pareto_solutions(self) -> None:
        """
        Compute and store Pareto solutions for the campaign.
        """
        log.info(f"Computing Pareto solutions for campaign '{self._campaign_id}'...")
        try:
            pareto_solutions_df = await self._optimizer.get_optimal_solutions.remote()
            pareto_solutions = pareto_solutions_df.to_dict(orient="records")
            await self._campaign_manager.set_pareto_solutions(self._campaign_id, pareto_solutions)
        except Exception as e:
            raise EosCampaignExecutionError(f"CMP '{self._campaign_id}' - Error computing Pareto solutions.") from e

    @property
    def optimizer(self) -> ActorHandle | None:
        return self._optimizer
