from typing import TYPE_CHECKING

from eos.configuration.exceptions import (
    EosConfigurationError,
    EosDevicePluginError,
    EosTaskPluginError,
)
from eos.configuration.packages import EntityType, PackageManager
from eos.configuration.registries import (
    CampaignOptimizerPluginRegistry,
    create_device_plugin_registry,
    create_device_spec_registry,
    create_task_plugin_registry,
    create_task_spec_registry,
)
from eos.configuration.def_sync import DefSync
from eos.configuration.validation import (
    ExperimentValidator,
    LabValidator,
    MultiLabValidator,
)
from eos.logging.logger import log

if TYPE_CHECKING:
    from eos.configuration.entities.experiment_def import ExperimentDef
    from eos.configuration.entities.lab_def import LabDef


class ConfigurationManager:
    """Manages the data-driven configuration layer for labs, experiments, tasks, and devices."""

    def __init__(self, user_dir: str, allowed_packages: set[str] | None = None):
        self._user_dir = user_dir
        self.package_manager = PackageManager(user_dir, allowed_packages)

        task_specs, task_dirs_to_types = self.package_manager.read_task_specs()
        self.task_specs = create_task_spec_registry(task_specs, task_dirs_to_types)
        self.tasks = create_task_plugin_registry(self.package_manager, self.task_specs)

        device_specs, device_dirs_to_types = self.package_manager.read_device_specs()
        self.device_specs = create_device_spec_registry(device_specs, device_dirs_to_types)
        self.devices = create_device_plugin_registry(self.package_manager, self.device_specs)

        self.labs: dict[str, LabDef] = {}
        self.experiments: dict[str, ExperimentDef] = {}

        self.campaign_optimizers = CampaignOptimizerPluginRegistry(self.package_manager)
        self.def_sync = DefSync(self.package_manager, self.task_specs, self.device_specs)

        self._initialize_task_plugins()
        log.debug("Configuration manager initialized")

    def get_loaded_labs(self) -> dict[str, bool]:
        """Return all lab types mapped to their loaded status."""
        all_labs = set()
        for package in self.package_manager.get_all_packages():
            all_labs.update(self.package_manager.get_entities_in_package(package.name, EntityType.LAB))
        return {lab: lab in self.labs for lab in all_labs}

    def load_lab(self, lab_type: str, validate_multi_lab: bool = True) -> None:
        """Load a lab configuration and validate it."""
        lab = self.package_manager.read_lab(lab_type)

        lab_validator = LabValidator(self._user_dir, lab, self.task_specs, self.device_specs)
        lab_validator.validate()

        self.labs[lab_type] = lab

        if validate_multi_lab:
            self._initialize_device_plugins()
            MultiLabValidator(list(self.labs.values())).validate()

        log.info(f"Loaded lab '{lab_type}'")

    def load_labs(self, lab_types: set[str]) -> None:
        """Load multiple labs and validate cross-lab configuration."""
        for lab_name in lab_types:
            self.load_lab(lab_name, validate_multi_lab=False)

        self._initialize_device_plugins()
        MultiLabValidator(list(self.labs.values())).validate()

    def unload_lab(self, lab_type: str) -> None:
        """Unload a lab and its associated experiments."""
        if lab_type not in self.labs:
            raise EosConfigurationError(
                f"Lab '{lab_type}' that was requested to be unloaded does not exist in the configuration manager"
            )

        self._unload_experiments_associated_with_labs({lab_type})
        self.labs.pop(lab_type)
        log.info(f"Unloaded lab '{lab_type}'")

    def unload_labs(self, lab_types: set[str]) -> None:
        """Unload multiple labs and their associated experiments."""
        for lab_type in lab_types:
            self.unload_lab(lab_type)

    def get_loaded_experiments(self) -> dict[str, bool]:
        """Return all experiment types mapped to their loaded status."""
        all_experiments = set()
        for package in self.package_manager.get_all_packages():
            all_experiments.update(self.package_manager.get_entities_in_package(package.name, EntityType.EXPERIMENT))
        return {exp: exp in self.experiments for exp in all_experiments}

    def load_experiment(self, experiment_type: str) -> None:
        """Load an experiment configuration and validate it."""
        if experiment_type in self.experiments:
            raise EosConfigurationError(
                f"Experiment '{experiment_type}' that was requested to be loaded is already loaded."
            )

        try:
            experiment = self.package_manager.read_experiment(experiment_type)

            ExperimentValidator(experiment, list(self.labs.values())).validate()

            self.campaign_optimizers.load_campaign_optimizer(experiment_type)
            self.experiments[experiment_type] = experiment

            log.info(f"Loaded experiment '{experiment_type}'")
        except Exception:
            self._cleanup_experiment_resources(experiment_type)
            raise

    def unload_experiment(self, experiment_name: str) -> None:
        """Unload an experiment from the configuration manager."""
        if experiment_name not in self.experiments:
            raise EosConfigurationError(
                f"Experiment '{experiment_name}' that was requested to be unloaded is not loaded."
            )

        self._cleanup_experiment_resources(experiment_name)
        self.experiments.pop(experiment_name)
        log.info(f"Unloaded experiment '{experiment_name}'")

    def load_experiments(self, experiment_types: set[str]) -> None:
        """Load multiple experiments."""
        for experiment_type in experiment_types:
            self.load_experiment(experiment_type)

    def unload_experiments(self, experiment_types: set[str]) -> None:
        """Unload multiple experiments."""
        for experiment_type in experiment_types:
            self.unload_experiment(experiment_type)

    def _cleanup_experiment_resources(self, experiment_name: str) -> None:
        """Clean up resources associated with an experiment."""
        try:
            self.campaign_optimizers.unload_campaign_optimizer(experiment_name)
        except Exception as e:
            raise EosConfigurationError(
                f"Error unloading campaign optimizer for experiment '{experiment_name}': {e!s}"
            ) from e

    def _unload_experiments_associated_with_labs(self, lab_names: set[str]) -> None:
        """Unload all experiments that depend on any of the given labs."""
        experiments_to_remove = [
            exp_name for exp_name, exp in self.experiments.items() if any(lab in exp.labs for lab in lab_names)
        ]

        for experiment_name in experiments_to_remove:
            self.unload_experiment(experiment_name)
            log.debug(f"Unloaded experiment '{experiment_name}' as it was associated with lab(s) {lab_names}")

    def _initialize_task_plugins(self) -> None:
        """Initialize all task plugins to catch errors early."""
        all_task_types = set(self.task_specs.get_all_specs().keys())
        new_task_types = all_task_types - set(self.tasks.plugin_types.keys())

        if not new_task_types:
            return

        try:
            self.tasks.initialize_for_types(new_task_types)
        except EosTaskPluginError as e:
            log.error(f"Failed to initialize task plugins: {e}")
            raise

    def _initialize_device_plugins(self) -> None:
        """Initialize device plugins for all devices in loaded labs."""
        device_types = {device.type for lab in self.labs.values() for device in lab.devices.values()}
        new_device_types = device_types - set(self.devices.plugin_types.keys())

        if not new_device_types:
            return

        try:
            self.devices.initialize_for_types(new_device_types)
        except EosDevicePluginError as e:
            log.error(f"Failed to initialize device plugins: {e}")
            raise
