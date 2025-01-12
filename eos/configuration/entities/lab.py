from typing import Any

from bofire.data_models.base import BaseModel
from pydantic import Field


class Location(BaseModel):
    desc: str
    meta: dict[str, Any] | None = None


class LabComputerConfig(BaseModel):
    ip: str
    desc: str | None = None


class LabDeviceConfig(BaseModel):
    type: str
    computer: str
    location: str | None = None
    desc: str | None = None
    init_parameters: dict[str, Any] | None = None


class LabContainerConfig(BaseModel):
    type: str
    location: str
    ids: list[str]
    desc: str | None = None
    meta: dict[str, Any] | None = None


class LabConfig(BaseModel):
    type: str
    desc: str
    devices: dict[str, LabDeviceConfig]
    locations: dict[str, Location] = Field(default_factory=dict)
    computers: dict[str, LabComputerConfig] = Field(default_factory=dict)
    containers: list[LabContainerConfig] = Field(default_factory=list)
