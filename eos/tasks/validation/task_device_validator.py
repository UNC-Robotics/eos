from collections import Counter

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task import TaskConfig
from eos.configuration.entities.task_spec import TaskSpecConfig


class TaskDeviceValidator:
    """Validates that a task configuration has the required devices specified in its specification."""

    def __init__(self, task_config: TaskConfig, task_spec: TaskSpecConfig, configuration_manager: ConfigurationManager):
        self.task_config = task_config
        self.task_spec = task_spec
        self.configuration_manager = configuration_manager
        self.device_specs = configuration_manager.device_specs

    def validate(self) -> None:
        """Validate that the task has all required device types."""
        if not self.task_spec.device_types:
            return

        # Get device type mapping once for all validations
        device_type_map = self._get_device_type_map()
        configured_device_types = set(device_type_map.values())

        self._validate_required_types(configured_device_types)
        self._validate_no_duplicate_types(device_type_map)

    def _get_device_type_map(self) -> dict[str, str]:
        """Maps device IDs to their types, validating labs and devices exist."""
        device_type_map = {}

        for device in self.task_config.devices:
            # Validate lab exists
            if device.lab_id not in self.configuration_manager.labs:
                raise ValueError(f"Lab '{device.lab_id}' specified in task '{self.task_config.id}' does not exist")

            lab_config = self.configuration_manager.labs[device.lab_id]

            # Validate device exists in lab
            if device.id not in lab_config.devices:
                raise ValueError(
                    f"Device '{device.id}' specified in task '{self.task_config.id}' "
                    f"does not exist in lab '{device.lab_id}'"
                )

            device_config = lab_config.devices[device.id]
            device_spec = self.device_specs.get_spec_by_config(device_config)

            if device_spec is None:
                raise ValueError(f"No device specification found for device '{device.id}' in lab '{device.lab_id}'")

            device_type_map[f"{device.lab_id}:{device.id}"] = device_spec.type

        return device_type_map

    def _validate_required_types(self, configured_device_types: set[str]) -> None:
        """Validate all required device types are present."""
        missing_device_types = set(self.task_spec.device_types) - configured_device_types
        if missing_device_types:
            raise ValueError(f"Task '{self.task_config.id}' is missing required device types: {missing_device_types}")

    def _validate_no_duplicate_types(self, device_type_map: dict[str, str]) -> None:
        """Validate no duplicate device types exist."""
        type_counts = Counter(device_type_map.values())
        for device_type, count in type_counts.items():
            if count > 1:
                raise ValueError(f"Task '{self.task_config.id}' assigned multiple devices of type '{device_type}'")
