from typing import TYPE_CHECKING

from eos.configuration.exceptions import (
    EosConfigurationError,
)
from eos.configuration.packages.entities import EntityType
from eos.configuration.packages.package_manager import PackageManager
from eos.configuration.plugin_registries.campaign_optimizer_plugin_registry import CampaignOptimizerPluginRegistry
from eos.configuration.plugin_registries.device_plugin_registry import DevicePluginRegistry
from eos.configuration.plugin_registries.task_plugin_registry import TaskPluginRegistry
from eos.configuration.spec_registries.device_spec_registry import DeviceSpecRegistry
from eos.configuration.spec_registries.task_spec_registry import (
    TaskSpecRegistry,
)
from eos.configuration.validation.experiment_validator import ExperimentValidator
from eos.configuration.validation.lab_validator import LabValidator
from eos.configuration.validation.multi_lab_validator import MultiLabValidator
from eos.logging.logger import log

if TYPE_CHECKING:
    from eos.configuration.entities.lab import LabConfig
    from eos.configuration.entities.experiment import ExperimentConfig


class ConfigurationManager:
    """
    The configuration manager is responsible for the data-driven configuration layer of EOS.
    It allows loading and managing configurations for labs, experiments, tasks, and devices.
    It also invokes the validation of the loaded configurations.
    """

    def __init__(self, user_dir: str):
        self._user_dir = user_dir
        self.package_manager = PackageManager(user_dir)

        task_configs, task_dirs_to_task_types = self.package_manager.read_task_configs()
        self.task_specs = TaskSpecRegistry(task_configs, task_dirs_to_task_types)
        self.tasks = TaskPluginRegistry(self.package_manager, self.task_specs)

        device_configs, device_dirs_to_device_types = self.package_manager.read_device_configs()
        self.device_specs = DeviceSpecRegistry(device_configs, device_dirs_to_device_types)
        self.devices = DevicePluginRegistry(self.package_manager, self.device_specs)

        self.labs: dict[str, LabConfig] = {}
        self.experiments: dict[str, ExperimentConfig] = {}

        self.campaign_optimizers = CampaignOptimizerPluginRegistry(self.package_manager)

        log.debug("Configuration manager initialized")

    def get_lab_loaded_statuses(self) -> dict[str, bool]:
        """
        Returns a dictionary where the lab type (name of directory) is associated
        with a boolean value indicating if it's currently loaded.
        """
        all_labs = set()

        for package in self.package_manager.get_all_packages():
            package_labs = self.package_manager.get_entities_in_package(package.name, EntityType.LAB)
            all_labs.update(package_labs)

        return {lab: lab in self.labs for lab in all_labs}

    def load_lab(self, lab_type: str, validate_multi_lab=True) -> None:
        """
        Load a new laboratory to the configuration manager.

        :param lab_type: The type of the lab. This should match the name of the lab's directory in the
        user directory.
        :param validate_multi_lab: Whether to validate the multi-lab configuration after adding the lab.
        """
        lab_config = self.package_manager.read_lab_config(lab_type)

        lab_validator = LabValidator(self._user_dir, lab_config, self.task_specs, self.device_specs)
        lab_validator.validate()

        self.labs[lab_type] = lab_config

        if validate_multi_lab:
            multi_lab_validator = MultiLabValidator(list(self.labs.values()))
            multi_lab_validator.validate()

        log.info(f"Loaded lab '{lab_type}'")
        log.debug(f"Lab configuration: {lab_config}")

    def load_labs(self, lab_types: set[str]) -> None:
        """
        Load multiple laboratories to the configuration manager.

        :param lab_types: A list of lab types (names). Each type should match the name of the lab's directory in the
        user directory.
        """
        for lab_name in lab_types:
            self.load_lab(lab_name, validate_multi_lab=False)

        multi_lab_validator = MultiLabValidator(list(self.labs.values()))
        multi_lab_validator.validate()

    def unload_labs(self, lab_types: set[str]) -> None:
        """
        Unload multiple labs from the configuration manager. Also unloads all experiments associated with the labs.

        :param lab_types: A list of lab types (names) to remove.
        """
        for lab_type in lab_types:
            self.unload_lab(lab_type)

    def unload_lab(self, lab_type: str) -> None:
        """
        Unload a lab from the configuration manager. Also unloads all experiments associated with the lab.

        :param lab_type: The type (name) of the lab to remove.
        """
        if lab_type not in self.labs:
            raise EosConfigurationError(
                f"Lab '{lab_type}' that was requested to be unloaded does not exist in the configuration manager"
            )

        self._unload_experiments_associated_with_labs({lab_type})

        self.labs.pop(lab_type)
        log.info(f"Unloaded lab '{lab_type}'")

    def get_experiment_loaded_statuses(self) -> dict[str, bool]:
        """
        Returns a dictionary where the experiment type (name of directory) is associated
        with a boolean value indicating if it's currently loaded.
        """
        all_experiments = set()

        for package in self.package_manager.get_all_packages():
            package_experiments = self.package_manager.get_entities_in_package(package.name, EntityType.EXPERIMENT)
            all_experiments.update(package_experiments)

        return {exp: exp in self.experiments for exp in all_experiments}

    def load_experiment(self, experiment_type: str) -> None:
        """
        Load a new experiment, making it available for execution.

        :param experiment_type: The name of the experiment. This should match the name of the experiment
        configuration file in the lab's directory.
        """
        if experiment_type in self.experiments:
            raise EosConfigurationError(
                f"Experiment '{experiment_type}' that was requested to be loaded is already loaded."
            )

        try:
            experiment_config = self.package_manager.read_experiment_config(experiment_type)

            experiment_validator = ExperimentValidator(experiment_config, list(self.labs.values()))
            experiment_validator.validate()

            self.campaign_optimizers.load_campaign_optimizer(experiment_type)
            self.experiments[experiment_type] = experiment_config

            log.info(f"Loaded experiment '{experiment_type}'")
            log.debug(f"Experiment configuration: {experiment_config}")
        except Exception:
            self._cleanup_experiment_resources(experiment_type)
            raise

    def unload_experiment(self, experiment_name: str) -> None:
        """
        Unload an experiment from the configuration manager.

        :param experiment_name: The name of the experiment to remove.
        """
        if experiment_name not in self.experiments:
            raise EosConfigurationError(
                f"Experiment '{experiment_name}' that was requested to be unloaded is not loaded."
            )

        self._cleanup_experiment_resources(experiment_name)
        self.experiments.pop(experiment_name)
        log.info(f"Unloaded experiment '{experiment_name}'")

    def load_experiments(self, experiment_types: set[str]) -> None:
        """
        Load multiple experiments to the configuration manager.

        :param experiment_types: A list of experiment names. Each name should match the name of the experiment's
        configuration file in the 'experiments' directory.
        """
        for experiment_type in experiment_types:
            self.load_experiment(experiment_type)

    def unload_experiments(self, experiment_types: set[str]) -> None:
        """
        Unload multiple experiments from the configuration manager.

        :param experiment_types: A list of experiment names to remove.
        """
        for experiment_type in experiment_types:
            self.unload_experiment(experiment_type)

    def _cleanup_experiment_resources(self, experiment_name: str) -> None:
        """
        Clean up resources associated with an experiment.

        :param experiment_name: The name of the experiment to clean up.
        """
        try:
            self.campaign_optimizers.unload_campaign_optimizer(experiment_name)
        except Exception as e:
            raise EosConfigurationError(
                f"Error unloading campaign optimizer for experiment '{experiment_name}': {e!s}"
            ) from e

    def _unload_experiments_associated_with_labs(self, lab_names: set[str]) -> None:
        """
        Unload all experiments associated with a list of labs from the configuration manager.

        :param lab_names: A list of lab names.
        """
        experiments_to_remove = []
        for experiment_name in self.experiments:
            for lab_name in lab_names:
                if lab_name in self.experiments[experiment_name].labs:
                    experiments_to_remove.append(experiment_name)

        for experiment_name in experiments_to_remove:
            self.unload_experiment(experiment_name)
            log.debug(f"Unloaded experiment '{experiment_name}' as it was associated with lab(s) {lab_names}")
