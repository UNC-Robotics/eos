from eos.campaigns.campaign_executor import CampaignExecutor
from eos.campaigns.campaign_manager import CampaignManager
from eos.campaigns.campaign_optimizer_manager import CampaignOptimizerManager
from eos.campaigns.entities.campaign import CampaignSubmission
from eos.configuration.configuration_manager import ConfigurationManager

from eos.protocols.protocol_executor_factory import ProtocolExecutorFactory
from eos.protocols.protocol_run_manager import ProtocolRunManager
from eos.database.abstract_sql_db_interface import AbstractSqlDbInterface

from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import inject


class CampaignExecutorFactory:
    """
    Factory class to create CampaignExecutor instances.
    """

    @inject
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        campaign_manager: CampaignManager,
        campaign_optimizer_manager: CampaignOptimizerManager,
        task_manager: TaskManager,
        protocol_executor_factory: ProtocolExecutorFactory,
        protocol_run_manager: ProtocolRunManager,
        db_interface: AbstractSqlDbInterface,
    ):
        self._configuration_manager = configuration_manager
        self._campaign_manager = campaign_manager
        self._campaign_optimizer_manager = campaign_optimizer_manager
        self._task_manager = task_manager
        self._protocol_executor_factory = protocol_executor_factory
        self._protocol_run_manager = protocol_run_manager
        self._db_interface = db_interface

    def create(
        self,
        campaign_submission: CampaignSubmission,
    ) -> CampaignExecutor:
        return CampaignExecutor(
            campaign_submission,
            self._campaign_manager,
            self._campaign_optimizer_manager,
            self._task_manager,
            self._protocol_executor_factory,
            self._protocol_run_manager,
            self._db_interface,
        )
