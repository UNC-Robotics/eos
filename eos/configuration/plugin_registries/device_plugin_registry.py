from eos.configuration.constants import DEVICE_CONFIG_FILE_NAME, DEVICE_IMPLEMENTATION_FILE_NAME
from eos.configuration.exceptions import EosDeviceImplementationClassNotFoundError
from eos.configuration.packages.entities import EntityType
from eos.configuration.packages.package_manager import PackageManager
from eos.configuration.plugin_registries.plugin_registry import PluginRegistry, PluginRegistryConfig
from eos.configuration.spec_registries.device_specification_registry import DeviceSpecificationRegistry
from eos.devices.base_device import BaseDevice


class DevicePluginRegistry(PluginRegistry[BaseDevice, DeviceSpecificationRegistry]):
    def __init__(self, package_manager: PackageManager):
        config = PluginRegistryConfig(
            spec_registry=DeviceSpecificationRegistry(),
            base_class=BaseDevice,
            config_file_name=DEVICE_CONFIG_FILE_NAME,
            implementation_file_name=DEVICE_IMPLEMENTATION_FILE_NAME,
            class_suffix="Device",
            not_found_exception_class=EosDeviceImplementationClassNotFoundError,
            entity_type=EntityType.DEVICE,
        )
        super().__init__(package_manager, config)

    def get_device_class_type(self, device_type: str) -> type[BaseDevice]:
        return self.get_plugin_class_type(device_type)