from typing import Any

from pydantic import BaseModel, Field


class TaskDeviceConfig(BaseModel):
    lab_id: str
    id: str


class TaskConfig(BaseModel):
    id: str
    type: str
    desc: str | None = None
    duration: int | None = None

    devices: list[TaskDeviceConfig] = Field(default_factory=list)
    containers: dict[str, str] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)

    dependencies: list[str] = Field(default_factory=list)
