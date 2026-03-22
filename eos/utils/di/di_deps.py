from eos.campaigns.campaign_executor_factory import CampaignExecutorFactory
from eos.campaigns.campaign_manager import CampaignManager
from eos.campaigns.campaign_optimizer_manager import CampaignOptimizerManager
from eos.configuration.configuration_manager import ConfigurationManager
from eos.resources.resource_manager import ResourceManager
from eos.devices.device_manager import DeviceManager
from eos.experiments.experiment_executor_factory import ExperimentExecutorFactory
from eos.experiments.experiment_manager import ExperimentManager
from eos.database.abstract_sql_db_interface import AbstractSqlDbInterface
from eos.database.file_db_interface import FileDbInterface
from eos.allocation.allocation_manager import AllocationManager
from eos.scheduling.abstract_scheduler import AbstractScheduler
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import get_di_container


def get_configuration_manager() -> ConfigurationManager:
    return get_di_container().get(ConfigurationManager)


def get_db_interface() -> AbstractSqlDbInterface:
    return get_di_container().get(AbstractSqlDbInterface)


def get_file_db_interface() -> FileDbInterface:
    return get_di_container().get(FileDbInterface)


def get_device_manager() -> DeviceManager:
    return get_di_container().get(DeviceManager)


def get_resource_manager() -> ResourceManager:
    return get_di_container().get(ResourceManager)


def get_allocation_manager() -> AllocationManager:
    return get_di_container().get(AllocationManager)


def get_task_manager() -> TaskManager:
    return get_di_container().get(TaskManager)


def get_experiment_manager() -> ExperimentManager:
    return get_di_container().get(ExperimentManager)


def get_campaign_manager() -> CampaignManager:
    return get_di_container().get(CampaignManager)


def get_campaign_optimizer_manager() -> CampaignOptimizerManager:
    return get_di_container().get(CampaignOptimizerManager)


def get_task_executor() -> TaskExecutor:
    return get_di_container().get(TaskExecutor)


def get_scheduler() -> AbstractScheduler:
    return get_di_container().get(AbstractScheduler)


def get_experiment_executor_factory() -> ExperimentExecutorFactory:
    return get_di_container().get(ExperimentExecutorFactory)


def get_campaign_executor_factory() -> CampaignExecutorFactory:
    return get_di_container().get(CampaignExecutorFactory)
