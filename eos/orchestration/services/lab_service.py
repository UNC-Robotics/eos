import traceback

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.lab import LabDeviceConfig
from eos.devices.device_manager import DeviceManager
from eos.logging.logger import log
from eos.utils.di.di_container import inject


class LabService:
    """
    Top-level lab functionality integration.
    Exposes an interface for querying lab state.
    """

    @inject
    def __init__(
        self,
        configuration_manager: ConfigurationManager,
        device_manager: DeviceManager,
    ):
        self._configuration_manager = configuration_manager
        self._device_manager = device_manager

    async def get_lab_devices(
        self, lab_types: set[str] | None = None, task_type: str | None = None
    ) -> dict[str, dict[str, LabDeviceConfig]]:
        """Get the devices that are available in the given labs or for a specific task type."""
        use_all_labs = not lab_types or not any(lab_type.strip() for lab_type in lab_types)
        effective_lab_types = set(self._configuration_manager.labs.keys()) if use_all_labs else lab_types

        # Get device types for the specified task (if any)
        task_device_types = set()
        if task_type:
            task_spec = self._configuration_manager.task_specs.get_spec_by_type(task_type)
            if task_spec.device_types:
                task_device_types = set(task_spec.device_types)

        lab_devices = {}
        for lab_type in effective_lab_types:
            lab = self._configuration_manager.labs.get(lab_type)
            if not lab:
                continue

            filtered_devices = {
                name: device
                for name, device in lab.devices.items()
                if not task_device_types or device.type in task_device_types
            }

            if filtered_devices:
                lab_devices[lab_type] = filtered_devices

        return lab_devices

    async def get_device_report(self, lab_id: str, device_id: str) -> dict:
        """Get a report for a specific device."""
        try:
            device_actor = self._device_manager.get_device_actor(lab_id, device_id)
            return await device_actor.report.remote()
        except Exception:
            log.error(
                f"Failed to get device report for lab '{lab_id}' and device '{device_id}': {traceback.format_exc()}"
            )
            raise
