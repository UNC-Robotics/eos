import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any

from eos.configuration.constants import (
    CAMPAIGN_OPTIMIZER_FILE_NAME,
    CAMPAIGN_OPTIMIZER_CREATION_FUNCTION_NAME,
)
from eos.configuration.exceptions import EosCampaignOptimizerImplementationClassNotFoundError
from eos.configuration.packages.entities import EntityType
from eos.configuration.packages.package_manager import PackageManager
from eos.configuration.plugin_registries.plugin_registry import PluginRegistry, PluginRegistryConfig
from eos.logging.logger import log
from eos.optimization.abstract_sequential_optimizer import AbstractSequentialOptimizer

CampaignOptimizerCreationFunction = Callable[[], tuple[dict[str, Any], type[AbstractSequentialOptimizer]]]


class CampaignOptimizerPluginRegistry(PluginRegistry[CampaignOptimizerCreationFunction, Any]):
    """
    Responsible for dynamically loading campaign optimizers from all packages
    and providing references to them for later use.
    """

    def __init__(self, package_manager: PackageManager):
        config = PluginRegistryConfig(
            spec_registry=None,  # Campaign optimizers don't use a specification registry
            base_class=None,  # Campaign optimizers don't have a base class
            config_file_name=None,  # Campaign optimizers don't have a separate config file
            implementation_file_name=CAMPAIGN_OPTIMIZER_FILE_NAME,
            not_found_exception_class=EosCampaignOptimizerImplementationClassNotFoundError,
            entity_type=EntityType.EXPERIMENT,
        )
        super().__init__(package_manager, config)

    def get_campaign_optimizer_creation_parameters(
        self, experiment_type: str
    ) -> tuple[dict[str, Any], type[AbstractSequentialOptimizer]] | None:
        """
        Get a function that can be used to get the constructor arguments and the optimizer type so it can be
        constructed later.

        :param experiment_type: The type of the experiment.
        :return: A tuple containing the constructor arguments and the optimizer type, or None if not found.
        """
        optimizer_function = self.get_plugin_class_type(experiment_type)
        if optimizer_function:
            return optimizer_function()
        return None

    def _load_single_plugin(self, package_name: str, dir_path: str, implementation_path: str) -> None:
        log.info(f"Loading campaign optimizer for experiment '{Path(dir_path).name}' from package '{package_name}'.")
        module = self._import_optimizer_module(dir_path, implementation_path)

        experiment_type = Path(dir_path).name
        if not self._register_optimizer_if_valid(module, experiment_type, package_name, implementation_path):
            log.warning(
                f"Optimizer configuration function '{CAMPAIGN_OPTIMIZER_CREATION_FUNCTION_NAME}' not found in the "
                f"campaign optimizer file '{self._config.implementation_file_name}' of experiment "
                f"'{Path(dir_path).name}' in package '{package_name}'."
            )

    def _import_optimizer_module(self, dir_path: str, implementation_path: str) -> object | None:
        """Import the optimizer module from the given path."""
        module_name = Path(dir_path).name
        spec = importlib.util.spec_from_file_location(module_name, implementation_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _register_optimizer_if_valid(
        self,
        module: object,
        experiment_type: str,
        package_name: str,
        implementation_path: str,
    ) -> bool:
        """Register the optimizer if its module contains the required creation function."""
        if CAMPAIGN_OPTIMIZER_CREATION_FUNCTION_NAME not in module.__dict__:
            return False

        optimizer_creator = module.__dict__[CAMPAIGN_OPTIMIZER_CREATION_FUNCTION_NAME]
        self._plugin_types[experiment_type] = optimizer_creator
        self._plugin_modules[experiment_type] = implementation_path

        log.info(f"Loaded campaign optimizer for experiment '{experiment_type}' from package '{package_name}'.")
        return True

    def load_campaign_optimizer(self, experiment_type: str) -> None:
        """
        Load the optimizer configuration function for the given experiment from the appropriate package.
        If the optimizer doesn't exist, log a warning and return without raising an error.
        """
        experiment_package = self._package_manager.find_package_for_entity(experiment_type, EntityType.EXPERIMENT)
        if not experiment_package:
            log.warning(f"No package found for experiment '{experiment_type}'.")
            return

        optimizer_file = (
            self._package_manager.get_entity_dir(experiment_type, EntityType.EXPERIMENT) / CAMPAIGN_OPTIMIZER_FILE_NAME
        )
        if not optimizer_file.exists():
            log.warning(
                f"No campaign optimizer found for experiment '{experiment_type}' in package "
                f"'{experiment_package.name}'."
            )
            return

        self._load_single_plugin(experiment_package.name, experiment_type, optimizer_file)

    def unload_campaign_optimizer(self, experiment_type: str) -> None:
        """
        Unload the optimizer configuration function for the given experiment.
        """
        if experiment_type in self._plugin_types:
            del self._plugin_types[experiment_type]
            del self._plugin_modules[experiment_type]
            log.info(f"Unloaded campaign optimizer for experiment '{experiment_type}'.")

    def reload_plugin(self, experiment_type: str) -> None:
        """
        Reload a specific campaign optimizer by its experiment type.
        """
        self.unload_campaign_optimizer(experiment_type)
        self.load_campaign_optimizer(experiment_type)
        log.info(f"Reloaded campaign optimizer for experiment '{experiment_type}'.")

    def reload_all_plugins(self) -> None:
        """
        Reload all campaign optimizers.
        """
        experiment_types = list(self._plugin_types.keys())
        for experiment_type in experiment_types:
            self.reload_plugin(experiment_type)
        log.info("Reloaded all campaign optimizers.")
