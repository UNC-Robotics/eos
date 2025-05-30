from eos.configuration.constants import DEVICE_CONFIG_FILE_NAME, DEVICE_IMPLEMENTATION_FILE_NAME
from eos.configuration.exceptions import EosDevicePluginError
from eos.configuration.packages.entities import EntityType
from eos.configuration.packages.package_manager import PackageManager
from eos.configuration.plugin_registries.plugin_registry import PluginRegistry, PluginRegistryConfig
from eos.configuration.spec_registries.device_spec_registry import DeviceSpecRegistry
from eos.devices.base_device import BaseDevice
from eos.utils.di.di_container import inject


class DevicePluginRegistry(PluginRegistry[BaseDevice, DeviceSpecRegistry]):
    @inject
    def __init__(self, package_manager: PackageManager, device_specs: DeviceSpecRegistry):
        config = PluginRegistryConfig(
            spec_registry=device_specs,
            base_class=BaseDevice,
            config_file_name=DEVICE_CONFIG_FILE_NAME,
            implementation_file_name=DEVICE_IMPLEMENTATION_FILE_NAME,
            exception_class=EosDevicePluginError,
            entity_type=EntityType.DEVICE,
        )
        super().__init__(package_manager, config, initialize=False)
