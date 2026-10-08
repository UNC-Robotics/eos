from typing import Any

from pydantic import BaseModel, Field


class DeviceInitParameterDef(BaseModel):
    type: str
    desc: str | None = None
    default: Any = None
    required: bool = False


class DeviceSpecDef(BaseModel):
    type: str
    desc: str | None = None
    init_parameters: dict[str, DeviceInitParameterDef] = Field(default_factory=dict)
