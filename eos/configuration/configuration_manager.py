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
    ProtocolValidator,
    LabValidator,
    MultiLabValidator,
)
from eos.logging.logger import log

if TYPE_CHECKING:
    from eos.configuration.entities.protocol_def import ProtocolDef
    from eos.configuration.entities.lab_def import LabDef


class ConfigurationManager:
    """Manages the data-driven configuration layer for labs, protocols, tasks, and devices."""

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
        self.protocols: dict[str, ProtocolDef] = {}

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
        """Unload a lab and its associated protocols."""
        if lab_type not in self.labs:
            raise EosConfigurationError(
                f"Lab '{lab_type}' that was requested to be unloaded does not exist in the configuration manager"
            )

        self._unload_protocols_associated_with_labs({lab_type})
        self.labs.pop(lab_type)
        log.info(f"Unloaded lab '{lab_type}'")

    def unload_labs(self, lab_types: set[str]) -> None:
        """Unload multiple labs and their associated protocols."""
        for lab_type in lab_types:
            self.unload_lab(lab_type)

    def get_loaded_protocols(self) -> dict[str, bool]:
        """Return all protocol types mapped to their loaded status."""
        all_protocols = set()
        for package in self.package_manager.get_all_packages():
            all_protocols.update(self.package_manager.get_entities_in_package(package.name, EntityType.PROTOCOL))
        return {p: p in self.protocols for p in all_protocols}

    def load_protocol(self, protocol_type: str) -> None:
        """Load a protocol configuration and validate it."""
        if protocol_type in self.protocols:
            log.debug(f"Protocol '{protocol_type}' is already loaded, skipping")
            return

        try:
            protocol_def = self.package_manager.read_protocol(protocol_type)

            ProtocolValidator(protocol_def, list(self.labs.values())).validate()

            self.protocols[protocol_type] = protocol_def

            log.info(f"Loaded protocol '{protocol_type}'")
        except Exception:
            self._cleanup_protocol_resources(protocol_type)
            raise

    def unload_protocol(self, protocol_type: str) -> None:
        """Unload a protocol from the configuration manager."""
        if protocol_type not in self.protocols:
            raise EosConfigurationError(f"Protocol '{protocol_type}' that was requested to be unloaded is not loaded.")

        self._cleanup_protocol_resources(protocol_type)
        self.protocols.pop(protocol_type)
        log.info(f"Unloaded protocol '{protocol_type}'")

    def load_protocols(self, protocol_types: set[str]) -> None:
        """Load multiple protocols."""
        for protocol_type in protocol_types:
            self.load_protocol(protocol_type)

    def unload_protocols(self, protocol_types: set[str]) -> None:
        """Unload multiple protocols."""
        for protocol_type in protocol_types:
            self.unload_protocol(protocol_type)

    def _cleanup_protocol_resources(self, protocol_type: str) -> None:
        """Clean up resources associated with a protocol."""
        try:
            self.campaign_optimizers.unload_campaign_optimizer(protocol_type)
        except Exception as e:
            raise EosConfigurationError(
                f"Error unloading campaign optimizer for protocol '{protocol_type}': {e!s}"
            ) from e

    def _unload_protocols_associated_with_labs(self, lab_names: set[str]) -> None:
        """Unload all protocols that depend on any of the given labs."""
        protocols_to_remove = [
            protocol_type
            for protocol_type, protocol in self.protocols.items()
            if any(lab in protocol.labs for lab in lab_names)
        ]

        for protocol_type in protocols_to_remove:
            self.unload_protocol(protocol_type)
            log.debug(f"Unloaded protocol '{protocol_type}' as it was associated with lab(s) {lab_names}")

    def refresh_task_spec(self, task_type: str) -> None:
        """Re-read a single task spec from disk and update the registry."""
        dir_path = self.task_specs.get_dir_by_type(task_type)
        if dir_path is None:
            raise EosConfigurationError(f"Task type '{task_type}' not found in spec registry.")
        entity_name = dir_path.name
        spec = self.package_manager.read_task_spec(entity_name)
        if not spec.output_resources:
            spec.output_resources = spec.input_resources.copy()
        self.task_specs.update_spec(spec.type, spec)
        log.debug(f"Refreshed task spec '{task_type}' from disk")

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
