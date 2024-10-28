from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.lab import LabDeviceConfig


class LabModule:
    """
    Top-level lab functionality integration.
    Exposes an interface for querying lab state.
    """

    def __init__(
        self,
        configuration_manager: ConfigurationManager,
    ):
        self._configuration_manager = configuration_manager

    async def get_lab_devices(
        self, lab_types: set[str] | None = None, task_type: str | None = None
    ) -> dict[str, dict[str, LabDeviceConfig]]:
        """
        Get the devices that are available in the given labs or for a specific task type.

        :param lab_types: The lab types. If None, all labs will be considered.
        :param task_type: The task type. If provided, only devices supporting this task type will be returned.
        :return: A dictionary of lab types and the devices available in each lab.
        """
        lab_devices = {}

        if not lab_types or not any(lab_type.strip() for lab_type in lab_types):
            lab_types = set(self._configuration_manager.labs.keys())

        task_device_types = set()
        if task_type:
            task_spec = self._configuration_manager.task_specs.get_spec_by_type(task_type)
            task_device_types = set(task_spec.device_types) if task_spec.device_types else set()

        for lab_type in lab_types:
            lab = self._configuration_manager.labs.get(lab_type)
            if not lab:
                continue

            if task_device_types:
                devices = {name: device for name, device in lab.devices.items() if device.type in task_device_types}
            else:
                devices = lab.devices

            if devices:
                lab_devices[lab_type] = devices

        return lab_devices
