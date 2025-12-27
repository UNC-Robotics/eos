from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.entities.task_def import TaskDef, DeviceAssignmentDef, DynamicDeviceAssignmentDef
from eos.configuration.entities.task_spec_def import TaskSpecDef
from eos.configuration.utils import is_device_reference


class TaskDeviceValidator:
    """Validates that a task configuration has the required devices specified in its specification."""

    def __init__(self, task: TaskDef, task_spec: TaskSpecDef, configuration_manager: ConfigurationManager):
        self.task = task
        self.task_spec = task_spec
        self.configuration_manager = configuration_manager
        self.device_specs = configuration_manager.device_specs

    def validate(self) -> None:
        """Validate that the task has all required devices matching the task spec."""
        if not self.task_spec.devices:
            return

        # Validate all spec devices are present in task config
        self._validate_all_devices_present()

        # Validate each device configuration
        for device_name, device in self.task.devices.items():
            if isinstance(device, DeviceAssignmentDef):
                self._validate_static_device(device_name, device)
            elif isinstance(device, DynamicDeviceAssignmentDef):
                self._validate_dynamic_device(device_name, device)
            elif isinstance(device, str) and not is_device_reference(device):
                # Device reference - will be resolved later, just validate format
                raise ValueError(
                    f"Device '{device_name}' in task '{self.task.name}' has invalid reference format: "
                    f"'{device}'. Expected format: 'task_name.device_name'"
                )

    def _validate_all_devices_present(self) -> None:
        """Validate that all devices required by the spec are present in the task config."""
        spec_device_names = set(self.task_spec.devices.keys())
        config_device_names = set(self.task.devices.keys())

        missing_devices = spec_device_names - config_device_names
        if missing_devices:
            raise ValueError(f"Task '{self.task.name}' is missing required devices: {missing_devices}")

    def _validate_static_device(self, device_name: str, device: DeviceAssignmentDef) -> None:
        """Validate a specific device assignment against the task spec."""
        # Check if this device is required by the spec
        if device_name not in self.task_spec.devices:
            # Device is not required by spec, skip validation (extra devices are allowed)
            return

        # Validate lab exists
        if device.lab_name not in self.configuration_manager.labs:
            raise ValueError(
                f"Lab '{device.lab_name}' specified for device '{device_name}' "
                f"in task '{self.task.name}' does not exist"
            )

        lab = self.configuration_manager.labs[device.lab_name]

        # Validate device exists in lab
        if device.name not in lab.devices:
            raise ValueError(
                f"Device '{device.name}' specified for '{device_name}' in task '{self.task.name}' "
                f"does not exist in lab '{device.lab_name}'"
            )

        lab_device = lab.devices[device.name]
        device_spec = self.device_specs.get_spec_by_config(lab_device)

        if device_spec is None:
            raise ValueError(
                f"No device specification found for device '{device.name}' "
                f"in lab '{device.lab_name}' for task '{self.task.name}'"
            )

        # Validate device type matches spec requirement
        spec_device = self.task_spec.devices[device_name]
        if device_spec.type != spec_device.type:
            raise ValueError(
                f"Device '{device_name}' in task '{self.task.name}' requires type '{spec_device.type}' "
                f"but '{device.lab_name}:{device.name}' has type '{device_spec.type}'"
            )

    def _validate_dynamic_device(self, device_name: str, device: DynamicDeviceAssignmentDef) -> None:
        """Validate a dynamic device request against the task spec."""
        # Check if this device is required by the spec
        if device_name not in self.task_spec.devices:
            # Device is not required by spec, skip validation
            return

        spec_device = self.task_spec.devices[device_name]

        # Validate dynamic device type matches spec requirement
        if device.device_type != spec_device.type:
            raise ValueError(
                f"Device '{device_name}' in task '{self.task.name}' requires type '{spec_device.type}' "
                f"but dynamic request specifies type '{device.device_type}'"
            )
