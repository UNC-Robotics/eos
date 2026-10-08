from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _LabModel(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")


class LabComputerDef(_LabModel):
    ip: str
    desc: str | None = None


class LabDeviceDef(_LabModel):
    type: str
    computer: str
    desc: str | None = None
    init_parameters: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class ResourceTypeDef(_LabModel):
    """Configuration for a resource type with default metadata."""

    meta: dict[str, Any] = Field(default_factory=dict)


class ResourceDef(_LabModel):
    """Configuration for a unique resource instance."""

    type: str
    meta: dict[str, Any] = Field(default_factory=dict)


class LabDef(_LabModel):
    name: str
    desc: str
    devices: dict[str, LabDeviceDef]
    computers: dict[str, LabComputerDef] = Field(default_factory=dict)
    resource_types: dict[str, ResourceTypeDef] = Field(default_factory=dict)
    resources: dict[str, ResourceDef] = Field(default_factory=dict)
