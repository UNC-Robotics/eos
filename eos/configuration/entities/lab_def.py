from typing import Any

from bofire.data_models.base import BaseModel
from pydantic import Field


class LabComputerDef(BaseModel):
    ip: str
    desc: str | None = None


class LabDeviceDef(BaseModel):
    type: str
    computer: str
    desc: str | None = None
    init_parameters: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class ResourceTypeDef(BaseModel):
    """Configuration for a resource type with default metadata."""

    meta: dict[str, Any] = Field(default_factory=dict)


class ResourceDef(BaseModel):
    """Configuration for a unique resource instance."""

    type: str
    meta: dict[str, Any] = Field(default_factory=dict)


class LabDef(BaseModel):
    name: str
    desc: str
    devices: dict[str, LabDeviceDef]
    computers: dict[str, LabComputerDef] = Field(default_factory=dict)
    resource_types: dict[str, ResourceTypeDef] = Field(default_factory=dict)
    resources: dict[str, ResourceDef] = Field(default_factory=dict)
