from typing import Any

from pydantic import BaseModel


class DeviceSpec(BaseModel):
    type: str
    desc: str | None = None
    init_parameters: dict[str, Any] | None = None
