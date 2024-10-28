from typing import Any, Annotated

from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Self

from eos.configuration.entities.task_parameters import (
    TaskParameterFactory,
    TaskParameterType,
)


class TaskSpecContainerConfig(BaseModel):
    type: str

    @field_validator("type")
    def _validate_type_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Container 'type' field must be specified.")
        return v


class TaskSpecOutputParameterConfig(BaseModel):
    type: TaskParameterType
    desc: str | None = None
    unit: str | None = None

    @field_validator("type")
    def _validate_parameter_type(cls, v: str) -> TaskParameterType:
        try:
            return TaskParameterType(v)
        except ValueError as e:
            raise ValueError(f"Invalid task output parameter type '{v}'") from e

    @model_validator(mode="after")
    def _validate_unit(self) -> Self:
        numeric_types = {TaskParameterType.INT, TaskParameterType.FLOAT}
        is_numeric = self.type in numeric_types
        has_unit = self.unit is not None and self.unit.strip() != ""

        if is_numeric and not has_unit:
            raise ValueError("Task output parameter type is numeric but no unit is specified.")
        if not is_numeric and has_unit:
            raise ValueError("Task output parameter type is not numeric but a unit is specified.")
        return self


ValidName = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_.]*$")]


class TaskSpecConfig(BaseModel):
    type: str
    desc: str | None = None
    device_types: list[str] | None = None

    input_containers: dict[ValidName, TaskSpecContainerConfig] = Field(default_factory=dict)
    input_parameters: dict[ValidName, Any] = Field(default_factory=dict)

    output_containers: dict[ValidName, TaskSpecContainerConfig] = Field(default_factory=dict)
    output_parameters: dict[ValidName, TaskSpecOutputParameterConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _set_default_output_containers(self) -> Self:
        """Set output containers to input containers if not specified"""
        if not self.output_containers:
            self.output_containers = self.input_containers.copy()
        return self

    @field_validator("input_parameters")
    def _validate_parameters(cls, input_parameters: dict) -> dict:
        """Validate that all input parameters can be created"""
        for param_name, param_config in input_parameters.items():
            try:
                param_type = TaskParameterType(param_config["type"])
                input_parameters[param_name] = TaskParameterFactory.create(param_type, **param_config)
            except (ValueError, KeyError) as e:
                raise ValueError(f"Invalid parameter configuration: {e!s}") from e
        return input_parameters
