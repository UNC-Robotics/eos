from eos.configuration.constants import TASK_CONFIG_FILE_NAME, TASK_IMPLEMENTATION_FILE_NAME
from eos.configuration.exceptions import EosTaskImplementationClassNotFoundError
from eos.configuration.packages.entities import EntityType
from eos.configuration.packages.package_manager import PackageManager
from eos.configuration.plugin_registries.plugin_registry import PluginRegistry, PluginRegistryConfig
from eos.configuration.spec_registries.task_spec_registry import TaskSpecRegistry
from eos.tasks.base_task import BaseTask
from eos.utils.di.di_container import inject_all


class TaskPluginRegistry(PluginRegistry[BaseTask, TaskSpecRegistry]):
    @inject_all
    def __init__(self, package_manager: PackageManager, task_specs: TaskSpecRegistry):
        config = PluginRegistryConfig(
            spec_registry=task_specs,
            base_class=BaseTask,
            config_file_name=TASK_CONFIG_FILE_NAME,
            implementation_file_name=TASK_IMPLEMENTATION_FILE_NAME,
            not_found_exception_class=EosTaskImplementationClassNotFoundError,
            entity_type=EntityType.TASK,
        )
        super().__init__(package_manager, config)
