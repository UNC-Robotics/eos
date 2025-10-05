from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class DeviceIdentifier(BaseModel):
    """Identifies a specific device"""

    lab_name: str
    name: str


class TaskDeviceConfig(BaseModel):
    """Specific device assignment"""

    lab_name: str
    name: str


class DynamicTaskDeviceConfig(BaseModel):
    """Dynamic device requirements - selects one or more device by type."""

    allocation_type: Literal["dynamic"] = "dynamic"
    device_type: str

    # Optional constraints to narrow down the selection
    allowed_labs: list[str] | None = None  # None = any lab
    allowed_devices: list[DeviceIdentifier] | None = None  # None = any device of the type

    @model_validator(mode="after")
    def validate_constraints(self) -> "DynamicTaskDeviceConfig":
        return self


class DynamicTaskResourceConfig(BaseModel):
    """Dynamic resource requirements - selects one or more resources by type."""

    allocation_type: Literal["dynamic"] = "dynamic"
    resource_type: str

    @model_validator(mode="after")
    def validate_fields(self) -> "DynamicTaskResourceConfig":
        if not self.resource_type or not self.resource_type.strip():
            raise ValueError("Dynamic resource request requires a non-empty 'resource_type'.")
        return self


class TaskConfig(BaseModel):
    name: str
    type: str
    desc: str | None = None

    duration: int = 1  # seconds
    group: str | None = None

    devices: dict[str, str | TaskDeviceConfig | DynamicTaskDeviceConfig] = Field(default_factory=dict)
    resources: dict[str, str | DynamicTaskResourceConfig] = Field(default_factory=dict)

    parameters: dict[str, Any] = Field(default_factory=dict)

    dependencies: list[str] = Field(default_factory=list)
