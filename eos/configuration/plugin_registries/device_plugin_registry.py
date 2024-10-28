from eos.configuration.constants import DEVICE_CONFIG_FILE_NAME, DEVICE_IMPLEMENTATION_FILE_NAME
from eos.configuration.exceptions import EosDeviceImplementationClassNotFoundError
from eos.configuration.packages.entities import EntityType
from eos.configuration.packages.package_manager import PackageManager
from eos.configuration.plugin_registries.plugin_registry import PluginRegistry, PluginRegistryConfig
from eos.configuration.spec_registries.device_spec_registry import DeviceSpecRegistry
from eos.devices.base_device import BaseDevice


class DevicePluginRegistry(PluginRegistry[BaseDevice, DeviceSpecRegistry]):
    def __init__(self, package_manager: PackageManager):
        config = PluginRegistryConfig(
            spec_registry=DeviceSpecRegistry(),
            base_class=BaseDevice,
            config_file_name=DEVICE_CONFIG_FILE_NAME,
            implementation_file_name=DEVICE_IMPLEMENTATION_FILE_NAME,
            not_found_exception_class=EosDeviceImplementationClassNotFoundError,
            entity_type=EntityType.DEVICE,
        )
        super().__init__(package_manager, config)
