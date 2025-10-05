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
from eos.scheduling.cpsat_scheduler import CpSatScheduler
from eos.tasks.on_demand_task_executor import OnDemandTaskExecutor
from eos.tasks.task_executor import TaskExecutor
from eos.tasks.task_manager import TaskManager
from eos.utils.di.di_container import get_di_container


def get_configuration_manager() -> ConfigurationManager:
    """
    Get the ConfigurationManager instance.

    :return: The ConfigurationManager instance
    """
    return get_di_container().get(ConfigurationManager)


def get_db_interface() -> AbstractSqlDbInterface:
    """
    Get the database interface instance.

    :return: The database interface instance
    """
    return get_di_container().get(AbstractSqlDbInterface)


def get_file_db_interface() -> FileDbInterface:
    """
    Get the file database interface instance.

    :return: The file database interface instance
    """
    return get_di_container().get(FileDbInterface)


def get_device_manager() -> DeviceManager:
    """
    Get the DeviceManager instance.

    :return: The DeviceManager instance
    """
    return get_di_container().get(DeviceManager)


def get_resource_manager() -> ResourceManager:
    """
    Get the ResourceManager instance.

    :return: The ResourceManager instance
    """
    return get_di_container().get(ResourceManager)


def get_allocation_manager() -> AllocationManager:
    """
    Get the AllocationManager instance.

    :return: The AllocationManager instance
    """
    return get_di_container().get(AllocationManager)


def get_task_manager() -> TaskManager:
    """
    Get the TaskManager instance.

    :return: The TaskManager instance
    """
    return get_di_container().get(TaskManager)


def get_experiment_manager() -> ExperimentManager:
    """
    Get the ExperimentManager instance.

    :return: The ExperimentManager instance
    """
    return get_di_container().get(ExperimentManager)


def get_campaign_manager() -> CampaignManager:
    """
    Get the CampaignManager instance.

    :return: The CampaignManager instance
    """
    return get_di_container().get(CampaignManager)


def get_campaign_optimizer_manager() -> CampaignOptimizerManager:
    """
    Get the CampaignOptimizerManager instance.

    :return: The CampaignOptimizerManager instance
    """
    return get_di_container().get(CampaignOptimizerManager)


def get_task_executor() -> TaskExecutor:
    """
    Get the TaskExecutor instance.

    :return: The TaskExecutor instance
    """
    return get_di_container().get(TaskExecutor)


def get_on_demand_task_executor() -> OnDemandTaskExecutor:
    """
    Get the OnDemandTaskExecutor instance.

    :return: The OnDemandTaskExecutor instance
    """
    return get_di_container().get(OnDemandTaskExecutor)


def get_scheduler() -> CpSatScheduler:
    """
    Get the CpSatScheduler instance.

    :return: The CpSatScheduler instance
    """
    return get_di_container().get(CpSatScheduler)


def get_experiment_executor_factory() -> ExperimentExecutorFactory:
    """
    Get the ExperimentExecutorFactory instance.

    :return: The ExperimentExecutorFactory instance
    """
    return get_di_container().get(ExperimentExecutorFactory)


def get_campaign_executor_factory() -> CampaignExecutorFactory:
    """
    Get the CampaignExecutorFactory instance.

    :return: The CampaignExecutorFactory instance
    """
    return get_di_container().get(CampaignExecutorFactory)
