from eos.campaigns.campaign_executor import CampaignExecutor
from eos.campaigns.campaign_manager import CampaignManager
from eos.campaigns.campaign_optimizer_manager import CampaignOptimizerManager
from eos.campaigns.entities.campaign import CampaignDefinition
from eos.configuration.configuration_manager import ConfigurationManager

from eos.experiments.experiment_executor_factory import ExperimentExecutorFactory

from eos.tasks.task_manager import TaskManager


class CampaignExecutorFactory:
    """
    Factory class to create CampaignExecutor instances.
    """

    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        campaign_manager: CampaignManager,
        campaign_optimizer_manager: CampaignOptimizerManager,
        task_manager: TaskManager,
        experiment_executor_factory: ExperimentExecutorFactory,
    ):
        self._configuration_manager = configuration_manager
        self._campaign_manager = campaign_manager
        self._campaign_optimizer_manager = campaign_optimizer_manager
        self._task_manager = task_manager
        self._experiment_executor_factory = experiment_executor_factory

    def create(
        self,
        campaign_definition: CampaignDefinition,
    ) -> CampaignExecutor:
        return CampaignExecutor(
            campaign_definition,
            self._campaign_manager,
            self._campaign_optimizer_manager,
            self._task_manager,
            self._experiment_executor_factory,
        )
