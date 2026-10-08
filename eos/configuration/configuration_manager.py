from typing import TYPE_CHECKING

from eos.configuration.exceptions import EosConfigurationError
from eos.configuration.packages import EntityType, PackageManager
from eos.configuration.registries import (
    CampaignOptimizerPluginRegistry,
    DeviceSpecRegistry,
    TaskSpecRegistry,
    create_device_plugin_registry,
    create_task_plugin_registry,
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

        self.task_specs = TaskSpecRegistry({}, {})
        self.tasks = create_task_plugin_registry(self.package_manager, self.task_specs)

        self.device_specs = DeviceSpecRegistry({}, {})
        self.devices = create_device_plugin_registry(self.package_manager, self.device_specs)

        self.load_plugins()

        self.labs: dict[str, LabDef] = {}
        self.protocols: dict[str, ProtocolDef] = {}

        self.campaign_optimizers = CampaignOptimizerPluginRegistry(self.package_manager)
        self.def_sync = DefSync(self.package_manager, self.task_specs, self.device_specs)

        log.debug("Configuration manager initialized")

    def load_plugins(self) -> None:
        """Import all tasks and devices of the active packages from disk and rebuild their specs."""
        self.package_manager.purge_modules()
        self.devices.load_all()
        self.tasks.load_all()

    def get_loaded_labs(self) -> dict[str, bool]:
        """Return all lab types mapped to their loaded status."""
        all_labs = set()
        for package in self.package_manager.get_all_packages():
            all_labs.update(self.package_manager.get_entities_in_package(package.name, EntityType.LAB))
        return {lab: lab in self.labs for lab in all_labs}

    def load_lab(self, lab_type: str, validate_multi_lab: bool = True) -> None:
        """Load a lab configuration and validate it."""
        lab = self.package_manager.read_lab(lab_type)

        lab_validator = LabValidator(self._user_dir, lab, self.task_specs, self.device_specs, self.devices.plugin_types)
        lab_validator.validate()

        self.labs[lab_type] = lab

        if validate_multi_lab:
            MultiLabValidator(list(self.labs.values())).validate()

        log.info(f"Loaded lab '{lab_type}'")

    def load_labs(self, lab_types: set[str]) -> None:
        """Load multiple labs and validate cross-lab configuration."""
        for lab_name in lab_types:
            self.load_lab(lab_name, validate_multi_lab=False)

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
