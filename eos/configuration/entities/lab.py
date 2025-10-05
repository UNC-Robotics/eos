from typing import Any

from bofire.data_models.base import BaseModel
from pydantic import Field


class LabComputerConfig(BaseModel):
    ip: str
    desc: str | None = None


class LabDeviceConfig(BaseModel):
    type: str
    computer: str
    desc: str | None = None
    init_parameters: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class LabResourceTypeConfig(BaseModel):
    """Configuration for a resource type with default metadata."""

    meta: dict[str, Any] = Field(default_factory=dict)


class LabResourceConfig(BaseModel):
    """Configuration for a unique resource instance."""

    type: str
    meta: dict[str, Any] = Field(default_factory=dict)


class LabConfig(BaseModel):
    name: str
    desc: str
    devices: dict[str, LabDeviceConfig]
    computers: dict[str, LabComputerConfig] = Field(default_factory=dict)
    resource_types: dict[str, LabResourceTypeConfig] = Field(default_factory=dict)
    resources: dict[str, LabResourceConfig] = Field(default_factory=dict)
