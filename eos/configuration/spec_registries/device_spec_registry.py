from eos.configuration.entities.device_spec import DeviceSpec
from eos.configuration.entities.lab import LabDeviceConfig
from eos.configuration.spec_registries.spec_registry import SpecRegistry


class DeviceSpecRegistry(SpecRegistry[DeviceSpec, LabDeviceConfig]):
    """
    The device specification registry stores the specifications for all devices that are available in EOS.
    """
