from pathlib import Path

from eos.configuration.constants import LABS_DIR, EOS_COMPUTER_NAME
from eos.configuration.entities.lab import LabConfig
from eos.configuration.exceptions import EosLabConfigurationError
from eos.configuration.spec_registries.device_spec_registry import DeviceSpecRegistry
from eos.configuration.spec_registries.task_spec_registry import TaskSpecRegistry
from eos.logging.batch_error_logger import batch_error, raise_batched_errors
from eos.utils.di.di_container import inject_all


class LabValidator:
    """
    Validates the configuration of a lab. It validates the locations, devices, and containers defined in the
    lab configuration.
    """

    @inject_all
    def __init__(
        self, config_dir: str, lab_config: LabConfig, task_specs: TaskSpecRegistry, device_specs: DeviceSpecRegistry
    ):
        self._lab_config = lab_config
        self._lab_config_dir = Path(config_dir) / LABS_DIR / lab_config.type.lower()
        self._task_specs = task_specs
        self._device_specs = device_specs

    def validate(self) -> None:
        self._validate_lab_folder_name_matches_lab_type()
        self._validate_locations()
        self._validate_computers()
        self._validate_devices()
        self._validate_containers()

    def _validate_locations(self) -> None:
        self._validate_device_locations()
        self._validate_container_locations()

    def _validate_lab_folder_name_matches_lab_type(self) -> None:
        if self._lab_config_dir.name != self._lab_config.type:
            raise EosLabConfigurationError(
                f"Lab folder name '{self._lab_config_dir.name}' does not match lab type '{self._lab_config.type}'."
            )

    def _validate_device_locations(self) -> None:
        locations = self._lab_config.locations
        for device_name, device in self._lab_config.devices.items():
            if device.location and device.location not in locations:
                batch_error(
                    f"Device '{device_name}' has invalid location '{device.location}'.",
                    EosLabConfigurationError,
                )
        raise_batched_errors(EosLabConfigurationError)

    def _validate_container_locations(self) -> None:
        locations = self._lab_config.locations
        for container in self._lab_config.containers:
            if container.location not in locations:
                raise EosLabConfigurationError(
                    f"Container of type '{container.type}' has invalid location '{container.location}'."
                )

    def _validate_computers(self) -> None:
        self._validate_computer_unique_ips()
        self._validate_eos_computer_not_specified()

    def _validate_computer_unique_ips(self) -> None:
        ip_addresses = set()

        for computer_name, computer in self._lab_config.computers.items():
            if computer.ip in ip_addresses:
                batch_error(
                    f"Computer '{computer_name}' has a duplicate IP address '{computer.ip}'.",
                    EosLabConfigurationError,
                )
            ip_addresses.add(computer.ip)

        raise_batched_errors(EosLabConfigurationError)

    def _validate_eos_computer_not_specified(self) -> None:
        for computer_name, computer in self._lab_config.computers.items():
            if computer_name.lower() == EOS_COMPUTER_NAME:
                batch_error(
                    "Computer name 'eos_computer' is reserved and cannot be used.",
                    EosLabConfigurationError,
                )
            if computer.ip in ["127.0.0.1", "localhost"]:
                batch_error(
                    f"Computer '{computer_name}' cannot use the reserved IP '127.0.0.1' or 'localhost'.",
                    EosLabConfigurationError,
                )
        raise_batched_errors(EosLabConfigurationError)

    def _validate_devices(self) -> None:
        self._validate_device_types()
        self._validate_devices_have_computers()
        self._validate_device_init_parameters()

    def _validate_devices_have_computers(self) -> None:
        for device_name, device in self._lab_config.devices.items():
            if device.computer.lower() == EOS_COMPUTER_NAME:
                continue
            if device.computer not in self._lab_config.computers:
                batch_error(
                    f"Device '{device_name}' has invalid computer '{device.computer}'.",
                    EosLabConfigurationError,
                )
        raise_batched_errors(EosLabConfigurationError)

    def _validate_device_types(self) -> None:
        for device_name, device in self._lab_config.devices.items():
            if not self._device_specs.get_spec_by_config(device):
                batch_error(
                    f"Device type '{device.type}' of device '{device_name}' does not exist.",
                    EosLabConfigurationError,
                )
        raise_batched_errors(EosLabConfigurationError)

    def _validate_device_init_parameters(self) -> None:
        for device_name, device in self._lab_config.devices.items():
            device_spec = self._device_specs.get_spec_by_config(device)

            if device.init_parameters:
                spec_params = device_spec.init_parameters or {}
                for param_name in device.init_parameters:
                    if param_name not in spec_params:
                        batch_error(
                            f"Invalid initialization parameter '{param_name}' for device '{device_name}' "
                            f"of type '{device.type}' in lab type '{self._lab_config.type}'. "
                            f"Valid parameters are: {', '.join(spec_params.keys())}",
                            EosLabConfigurationError,
                        )

        raise_batched_errors(EosLabConfigurationError)

    def _validate_containers(self) -> None:
        self._validate_container_unique_types()
        self._validate_container_unique_ids()

    def _validate_container_unique_types(self) -> None:
        container_types = []
        for container in self._lab_config.containers:
            container_types.append(container.type)

        unique_container_types = set(container_types)

        for container_type in unique_container_types:
            if container_types.count(container_type) > 1:
                batch_error(
                    f"Container type '{container_type}' already defined."
                    f" Please add more ids to the existing container definition.",
                    EosLabConfigurationError,
                )
        raise_batched_errors(EosLabConfigurationError)

    def _validate_container_unique_ids(self) -> None:
        container_ids = set()
        duplicate_ids = set()
        for container in self._lab_config.containers:
            for container_id in container.ids:
                if container_id in container_ids:
                    duplicate_ids.add(container_id)
                else:
                    container_ids.add(container_id)

        if duplicate_ids:
            duplicate_ids_str = "\n  ".join(duplicate_ids)
            raise EosLabConfigurationError(
                f"Containers must have unique IDs. The following are not unique:\n  {duplicate_ids_str}"
            )
