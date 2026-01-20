import copy
from collections import defaultdict
from pathlib import Path
from typing import Any

from eos.configuration.constants import EOS_COMPUTER_NAME, LABS_DIR
from eos.configuration.entities.experiment_def import ExperimentDef
from eos.configuration.entities.lab_def import LabDef, ResourceDef
from eos.configuration.entities.task_def import TaskDef
from eos.configuration.entities.task_parameters import TaskParameterFactory, TaskParameterType
from eos.configuration.entities.task_spec_def import TaskSpecDef, ResourceRequirement
from eos.configuration.exceptions import (
    EosConfigurationError,
    EosExperimentConfigurationError,
    EosLabConfigurationError,
    EosResourceConfigurationError,
    EosTaskValidationError,
)
from eos.configuration.registries import DeviceSpecRegistry, TaskSpecRegistry
from eos.configuration.utils import (
    is_dynamic_parameter,
    is_parameter_reference,
    is_resource_reference,
)
from eos.logging.batch_error_logger import batch_error, raise_batched_errors
from eos.utils.di.di_container import inject


class LabValidator:
    """Validates lab configuration."""

    @inject
    def __init__(self, config_dir: str, lab: LabDef, task_specs: TaskSpecRegistry, device_specs: DeviceSpecRegistry):
        self._lab = lab
        self._lab_dir = Path(config_dir) / LABS_DIR / lab.name.lower()
        self._task_specs = task_specs
        self._device_specs = device_specs

    def validate(self) -> None:
        """Run all lab validation checks."""
        self._validate_lab_folder_name_matches_lab_type()
        self._validate_computers()
        self._validate_devices()
        self._validate_resources()

    def _validate_lab_folder_name_matches_lab_type(self) -> None:
        """Ensure lab folder name matches the configured lab type."""
        if self._lab_dir.name != self._lab.name:
            raise EosLabConfigurationError(
                f"Lab folder name '{self._lab_dir.name}' does not match lab type '{self._lab.name}'."
            )

    def _validate_computers(self) -> None:
        """Validate all computer configurations."""
        self._validate_computer_unique_ips()
        self._validate_eos_computer_not_specified()

    def _validate_computer_unique_ips(self) -> None:
        """Ensure all computers have unique IP addresses."""
        ip_addresses = set()
        for computer_name, computer in self._lab.computers.items():
            if computer.ip in ip_addresses:
                batch_error(
                    f"Computer '{computer_name}' has a duplicate IP address '{computer.ip}'.",
                    EosLabConfigurationError,
                )
            ip_addresses.add(computer.ip)
        raise_batched_errors(EosLabConfigurationError)

    def _validate_eos_computer_not_specified(self) -> None:
        """Ensure reserved computer name and IPs are not used."""
        for computer_name, computer in self._lab.computers.items():
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
        """Validate all device configurations."""
        self._validate_device_types()
        self._validate_devices_have_computers()
        self._validate_device_init_parameters()

    def _validate_devices_have_computers(self) -> None:
        """Ensure each device references a valid computer."""
        for device_name, device in self._lab.devices.items():
            if device.computer.lower() == EOS_COMPUTER_NAME:
                continue
            if device.computer not in self._lab.computers:
                batch_error(
                    f"Device '{device_name}' has invalid computer '{device.computer}'.",
                    EosLabConfigurationError,
                )
        raise_batched_errors(EosLabConfigurationError)

    def _validate_device_types(self) -> None:
        """Ensure all device types exist in the device spec registry."""
        for device_name, device in self._lab.devices.items():
            if not self._device_specs.get_spec_by_config(device):
                batch_error(
                    f"Device type '{device.type}' of device '{device_name}' does not exist.",
                    EosLabConfigurationError,
                )
        raise_batched_errors(EosLabConfigurationError)

    def _validate_device_init_parameters(self) -> None:
        """Validate device initialization parameters against their specs."""
        for device_name, device in self._lab.devices.items():
            device_spec = self._device_specs.get_spec_by_config(device)
            if device.init_parameters:
                spec_params = device_spec.init_parameters or {}
                for param_name in device.init_parameters:
                    if param_name not in spec_params:
                        batch_error(
                            f"Invalid initialization parameter '{param_name}' for device '{device_name}' "
                            f"of type '{device.type}' in lab type '{self._lab.name}'. "
                            f"Valid parameters are: {', '.join(spec_params.keys())}",
                            EosLabConfigurationError,
                        )
        raise_batched_errors(EosLabConfigurationError)

    def _validate_resources(self) -> None:
        """Validate resource configurations."""
        self._validate_resource_type_definitions_unique()

    def _validate_resource_type_definitions_unique(self) -> None:
        """Ensure resource type definitions are unique."""
        type_names = list(self._lab.resource_types.keys())
        duplicates = {t for t in type_names if type_names.count(t) > 1}
        if duplicates:
            batch_error(
                f"Duplicate resource type definitions found: {', '.join(sorted(duplicates))}",
                EosLabConfigurationError,
            )
        raise_batched_errors(EosLabConfigurationError)


class MultiLabValidator:
    """Cross-validates multiple lab configurations."""

    def __init__(self, labs: list[LabDef]):
        self._labs = labs

    def validate(self) -> None:
        """Run all multi-lab validation checks."""
        self._validate_computer_ips_globally_unique()
        self._validate_resource_names_globally_unique()

    def _validate_computer_ips_globally_unique(self) -> None:
        """Ensure computer IPs are unique across all labs."""
        computer_ips = defaultdict(list)
        for lab in self._labs:
            for computer in lab.computers.values():
                computer_ips[computer.ip].append(lab.name)

        duplicate_ips = {ip: labs for ip, labs in computer_ips.items() if len(labs) > 1}
        if duplicate_ips:
            duplicate_ips_str = "\n  ".join(
                f"'{ip}': defined in labs {', '.join(labs)}" for ip, labs in duplicate_ips.items()
            )
            raise EosLabConfigurationError(
                f"The following computer IPs are not globally unique:\n  {duplicate_ips_str}"
            )

    def _validate_resource_names_globally_unique(self) -> None:
        """Ensure resource names are unique across all labs."""
        resource_names = defaultdict(list)
        for lab in self._labs:
            for resource_name in lab.resources:
                resource_names[resource_name].append(lab.name)

        duplicate_names = {name: labs for name, labs in resource_names.items() if len(labs) > 1}
        if duplicate_names:
            duplicate_names_str = "\n  ".join(
                f"'{name}': defined in labs {', '.join(labs)}" for name, labs in duplicate_names.items()
            )
            raise EosLabConfigurationError(
                f"The following resource names are not globally unique:\n  {duplicate_names_str}"
            )


class ExperimentResourceRegistry:
    """Stores resource information for labs used by an experiment."""

    def __init__(self, experiment: ExperimentDef, labs: list[LabDef]):
        self._labs = [lab for lab in labs if lab.name in experiment.labs]

    def find_resource_by_name(self, resource_name: str) -> ResourceDef | None:
        """Find a resource by name across all labs."""
        for lab in self._labs:
            if resource_name in lab.resources:
                return lab.resources[resource_name]
        return None


class ExperimentValidator:
    """Validates experiment configuration."""

    def __init__(self, experiment: ExperimentDef, labs: list[LabDef]):
        self._experiment = experiment
        self._labs = labs
        self._resource_registry = ExperimentResourceRegistry(experiment, labs)
        self._task_validator = TaskValidator(experiment, labs, self._resource_registry)

    def validate(self) -> None:
        """Run all experiment validation checks."""
        self._validate_labs()
        self._validate_resources()
        self._task_validator.validate_all_tasks()

    def _validate_labs(self) -> None:
        """Ensure all required labs exist."""
        lab_types = [lab.name for lab in self._labs]
        invalid_labs = [lab for lab in self._experiment.labs if lab not in lab_types]

        if invalid_labs:
            raise EosExperimentConfigurationError(
                f"The following labs required by experiment '{self._experiment.type}' do not exist:"
                f"\n  {chr(10).join(invalid_labs)}"
            )

    def _validate_resources(self) -> None:
        """Ensure all required resources exist."""
        if not self._experiment.resources:
            return

        for resource_name in self._experiment.resources:
            if not any(resource_name in lab.resources for lab in self._labs):
                raise EosResourceConfigurationError(f"Resource '{resource_name}' does not exist.")


class TaskValidator:
    """Validates task configurations."""

    def __init__(
        self,
        experiment: ExperimentDef,
        labs: list[LabDef],
        resource_registry: ExperimentResourceRegistry | None = None,
    ):
        self._experiment = experiment
        self._labs = labs
        self._task_specs = TaskSpecRegistry()
        self._resource_registry = resource_registry or ExperimentResourceRegistry(experiment, labs)

    def validate_all_tasks(self) -> None:
        """Validate all tasks in the experiment."""
        for task in self._experiment.tasks:
            self._validate_task(task)

    def _validate_task(self, task: TaskDef) -> None:
        """Validate a single task's parameters and resources."""
        task_spec = self._task_specs.get_spec_by_config(task)
        self._validate_task_parameters(task, task_spec)
        self._validate_task_resources(task, task_spec)

    def _validate_task_parameters(self, task: TaskDef, task_spec: TaskSpecDef) -> None:
        """Validate task parameters including references."""
        if task_spec.input_parameters is None and task.parameters is not None:
            raise EosTaskValidationError(
                f"Task '{task.name}' does not accept input parameters but parameters were provided."
            )

        if not task.parameters:
            return

        for parameter_name in task.parameters:
            self._validate_parameter_in_task_spec(task.name, parameter_name, task_spec)
        raise_batched_errors(root_exception_type=EosTaskValidationError)

        self._validate_all_required_parameters_provided(task.name, task.parameters, task_spec)

        for parameter_name, parameter in task.parameters.items():
            self._validate_parameter(task.name, parameter_name, parameter, task_spec)
        raise_batched_errors(root_exception_type=EosTaskValidationError)

        self._validate_parameter_references(task)

    def _validate_parameter_in_task_spec(self, task_name: str, parameter_name: str, task_spec: TaskSpecDef) -> None:
        """Check that the parameter exists in the task specification."""
        if parameter_name not in task_spec.input_parameters:
            batch_error(
                f"Parameter '{parameter_name}' in task '{task_name}' is invalid. "
                f"Expected a parameter found in the task specification.",
                EosTaskValidationError,
            )

    def _validate_parameter(self, task_name: str, parameter_name: str, parameter: Any, task_spec: TaskSpecDef) -> None:
        """Validate a parameter, skipping references and dynamic parameters."""
        if is_parameter_reference(parameter) or is_dynamic_parameter(parameter):
            return
        self._validate_parameter_spec(task_name, parameter_name, parameter, task_spec)

    def _validate_parameter_spec(
        self, task_name: str, parameter_name: str, parameter: Any, task_spec: TaskSpecDef
    ) -> None:
        """Validate a parameter against its task specification."""
        parameter_spec = copy.deepcopy(task_spec.input_parameters[parameter_name])

        if not isinstance(parameter, TaskParameterType(parameter_spec.type).python_type):
            batch_error(
                f"Parameter '{parameter_name}' in task '{task_name}' has incorrect type {type(parameter)}. "
                f"Expected type: '{parameter_spec.type}'.",
                EosTaskValidationError,
            )
            return

        parameter_spec.value = parameter

        try:
            parameter_type = TaskParameterType(parameter_spec.type)
            TaskParameterFactory.create(parameter_type, **parameter_spec.model_dump())
        except EosConfigurationError as e:
            batch_error(
                f"Parameter '{parameter_name}' in task '{task_name}' validation error: {e}",
                EosTaskValidationError,
            )

    def _validate_all_required_parameters_provided(
        self, task_name: str, parameters: dict[str, Any], task_spec: TaskSpecDef
    ) -> None:
        """Ensure all required parameters are provided."""
        required_parameters = [param for param, spec in task_spec.input_parameters.items() if spec.value is None]
        missing_parameters = [param for param in required_parameters if param not in parameters]

        if missing_parameters:
            raise EosTaskValidationError(
                f"Task '{task_name}' is missing required input parameters: {missing_parameters}"
            )

    def _validate_parameter_references(self, task: TaskDef) -> None:
        """Validate all parameter references in a task."""
        for parameter_name, parameter in task.parameters.items():
            if is_parameter_reference(parameter):
                self._validate_parameter_reference(parameter_name, task)

    def _validate_parameter_reference(self, parameter_name: str, task: TaskDef) -> None:
        """Validate a parameter reference exists and has matching type."""
        parameter = task.parameters[parameter_name]
        referenced_task_name, referenced_parameter = str(parameter).split(".")

        referenced_task = self._find_task_by_name(referenced_task_name)
        if not referenced_task:
            raise EosTaskValidationError(
                f"Parameter '{parameter_name}' in task '{task.name}' references task '{referenced_task_name}' "
                f"which does not exist."
            )

        referenced_task_spec = self._task_specs.get_spec_by_config(referenced_task)

        referenced_parameter_spec = None
        if referenced_task_spec.output_parameters and referenced_parameter in referenced_task_spec.output_parameters:
            referenced_parameter_spec = referenced_task_spec.output_parameters[referenced_parameter]
        elif referenced_task_spec.input_parameters and referenced_parameter in referenced_task_spec.input_parameters:
            referenced_parameter_spec = referenced_task_spec.input_parameters[referenced_parameter]

        if not referenced_parameter_spec:
            raise EosTaskValidationError(
                f"Parameter '{parameter_name}' in task '{task.name}' references parameter '{referenced_parameter}' "
                f"which does not exist in task '{referenced_task_name}'."
            )

        task_spec = self._task_specs.get_spec_by_config(task)
        parameter_spec = task_spec.input_parameters[parameter_name]

        if (
            TaskParameterType(parameter_spec.type).python_type
            != TaskParameterType(referenced_parameter_spec.type).python_type
        ):
            raise EosTaskValidationError(
                f"Type mismatch for referenced parameter '{referenced_parameter}' in task '{task.name}'. "
                f"The required parameter type is '{parameter_spec.type}' which does not match the referenced parameter "
                f"type '{referenced_parameter_spec.type.value}'."
            )

    def _validate_task_resources(self, task: TaskDef, task_spec: TaskSpecDef) -> None:
        """Validate task resources including references."""
        if not task.resources and task_spec.input_resources:
            raise EosTaskValidationError(f"Task '{task.name}' requires input resources but none were provided.")

        if not task.resources:
            return

        self._validate_input_resource_requirements(task, task_spec)
        raise_batched_errors(root_exception_type=EosTaskValidationError)

        self._validate_resource_references(task)

    def _validate_input_resource_requirements(self, task: TaskDef, task_spec: TaskSpecDef) -> None:
        """Validate resource types and quantities match requirements."""
        required_resources = task_spec.input_resources or {}
        provided_resources = self._get_provided_resources(task)

        self._validate_resource_counts(task.name, required_resources, provided_resources)
        self._validate_resource_types(task.name, required_resources, provided_resources)

    def _get_provided_resources(self, task: TaskDef) -> dict[str, str]:
        """Get provided resources, validating existence for non-references."""
        provided_resources = {}
        for resource_name, resource_value in task.resources.items():
            if not isinstance(resource_value, str):
                provided_resources[resource_name] = getattr(resource_value, "resource_type", "reference")
            elif is_resource_reference(resource_value):
                provided_resources[resource_name] = "reference"
            else:
                lab_resource = self._validate_resource_exists(task.name, resource_value)
                if lab_resource:
                    provided_resources[resource_name] = lab_resource.type
        return provided_resources

    def _validate_resource_exists(self, task_name: str, resource_name: str) -> ResourceDef | None:
        """Validate a resource exists in the lab."""
        resource = self._resource_registry.find_resource_by_name(resource_name)
        if not resource:
            batch_error(
                f"resource '{resource_name}' in task '{task_name}' does not exist in the lab.",
                EosTaskValidationError,
            )
        return resource

    def _validate_resource_counts(
        self, task_name: str, required: dict[str, ResourceRequirement], provided: dict[str, str]
    ) -> None:
        """Validate resource count matches requirements."""
        if len(provided) != len(required):
            batch_error(
                f"Task '{task_name}' requires {len(required)} resource(s) but {len(provided)} were provided.",
                EosTaskValidationError,
            )

    def _validate_resource_types(
        self, task_name: str, required: dict[str, ResourceRequirement], provided: dict[str, str]
    ) -> None:
        """Validate resource types match requirements."""
        for resource_name, resource_spec in required.items():
            if resource_name not in provided:
                batch_error(
                    f"Required resource '{resource_name}' not provided for task '{task_name}'.",
                    EosTaskValidationError,
                )
            elif provided[resource_name] != "reference" and provided[resource_name] != resource_spec.type:
                batch_error(
                    f"resource '{resource_name}' in task '{task_name}' has incorrect type. "
                    f"Expected '{resource_spec.type}' but got '{provided[resource_name]}'.",
                    EosTaskValidationError,
                )

        for resource_name in provided:
            if resource_name not in required:
                batch_error(
                    f"Unexpected resource '{resource_name}' provided for task '{task_name}'.",
                    EosTaskValidationError,
                )

    def _validate_resource_references(self, task: TaskDef) -> None:
        """Validate all resource references in a task."""
        for resource_name, resource_value in task.resources.items():
            if isinstance(resource_value, str) and is_resource_reference(resource_value):
                self._validate_resource_reference(resource_name, resource_value, task)

    def _validate_resource_reference(self, resource_name: str, resource_value: str, task: TaskDef) -> None:
        """Validate a resource reference exists and has matching type."""
        referenced_task_name, referenced_resource = resource_value.split(".")

        referenced_task = self._find_task_by_name(referenced_task_name)
        if not referenced_task:
            raise EosTaskValidationError(
                f"resource '{resource_name}' in task '{task.name}' references task '{referenced_task_name}' "
                f"which does not exist."
            )

        referenced_task_spec = self._task_specs.get_spec_by_config(referenced_task)

        if referenced_resource not in referenced_task_spec.output_resources:
            raise EosTaskValidationError(
                f"resource '{resource_name}' in task '{task.name}' references resource '{referenced_resource}' "
                f"which is not an output resource of task '{referenced_task_name}'."
            )

        task_spec = self._task_specs.get_spec_by_config(task)
        if resource_name not in task_spec.input_resources:
            raise EosTaskValidationError(
                f"resource '{resource_name}' is not a valid input resource for task '{task.name}'."
            )

        required_resource_spec = task_spec.input_resources[resource_name]
        referenced_resource_spec = referenced_task_spec.output_resources[referenced_resource]

        if required_resource_spec.type != referenced_resource_spec.type:
            raise EosTaskValidationError(
                f"Type mismatch for referenced resource '{referenced_resource}' in task '{task.name}'. "
                f"The required resource type is '{required_resource_spec.type}' which does not match the referenced "
                f"resource type '{referenced_resource_spec.type}'."
            )

    def _find_task_by_name(self, task_name: str) -> TaskDef | None:
        """Find a task by name in the experiment."""
        return next((task for task in self._experiment.tasks if task.name == task_name), None)
