from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator
from typing import Self

from eos.configuration.entities.task_parameters import (
    TaskParameter,
    TaskParameterFactory,
    TaskParameterGroup,
    TaskParameterType,
    ValidName,
)


class ResourceRequirement(BaseModel):
    type: str

    @field_validator("type")
    def _validate_type_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Resource 'type' field must be specified.")
        return v


class OutputParameter(BaseModel):
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


class DeviceRequirementDef(BaseModel):
    type: str

    @field_validator("type")
    def _validate_type_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Device 'type' field must be specified.")
        return v


class TaskSpecDef(BaseModel):
    type: str
    desc: str | None = None
    devices: dict[ValidName, DeviceRequirementDef] = Field(default_factory=dict)

    input_resources: dict[ValidName, ResourceRequirement] = Field(default_factory=dict)
    input_parameters: dict[ValidName, Any] = Field(default_factory=dict)

    output_resources: dict[ValidName, ResourceRequirement] = Field(default_factory=dict)
    output_parameters: dict[ValidName, OutputParameter] = Field(default_factory=dict)

    _flat_index: dict[str, TaskParameter] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _set_default_output_resources(self) -> Self:
        """Set output resources to input resources if not specified"""
        if not self.output_resources:
            self.output_resources = self.input_resources.copy()
        return self

    @field_validator("input_parameters")
    def _validate_parameters(cls, input_parameters: dict) -> dict:
        """Leaf if entry has a `type:` key, else group of leaves. Leaf names must be globally unique."""
        seen: set[str] = set()

        def claim(name: str) -> None:
            if name in seen:
                raise ValueError(f"Duplicate input parameter name '{name}' across groups and/or top level.")
            seen.add(name)

        for name, config in input_parameters.items():
            if not isinstance(config, dict):
                raise ValueError(f"Invalid parameter configuration for '{name}': expected a mapping.")

            if "type" in config:
                try:
                    param_type = TaskParameterType(config["type"])
                    input_parameters[name] = TaskParameterFactory.create(param_type, **config)
                except (ValueError, KeyError) as e:
                    raise ValueError(f"Invalid parameter configuration: {e!s}") from e
                claim(name)
            else:
                group = TaskParameterGroup(params=config)
                input_parameters[name] = group
                for leaf_name in group.params:
                    claim(leaf_name)

        return input_parameters

    @model_validator(mode="after")
    def _build_flat_index(self) -> Self:
        flat: dict[str, TaskParameter] = {}
        for name, entry in self.input_parameters.items():
            if isinstance(entry, TaskParameterGroup):
                flat.update(entry.params)
            else:
                flat[name] = entry
        self._flat_index = flat
        return self

    def iter_parameters(self) -> Iterator[tuple[str, TaskParameter]]:
        """Yield (leaf_name, spec) pairs across top-level leaves and every group, in declaration order."""
        return iter(self._flat_index.items())

    def get_parameter(self, name: str) -> TaskParameter | None:
        """Return the leaf spec for `name` regardless of whether it is top-level or grouped."""
        return self._flat_index.get(name)
