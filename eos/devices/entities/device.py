from enum import Enum
from typing import Any

from pydantic import BaseModel, field_serializer, Field
from ray.actor import ActorHandle


class DeviceStatus(Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Device(BaseModel):
    id: str
    lab_id: str
    type: str
    computer: str
    location: str | None = None
    status: DeviceStatus = DeviceStatus.ACTIVE
    metadata: dict[str, Any] = Field(default_factory=dict)

    actor_handle: ActorHandle | None = Field(exclude=True, default=None)

    class Config:
        arbitrary_types_allowed = True

    def get_actor_id(self) -> str:
        return f"{self.lab_id}.{self.id}"

    @field_serializer("status")
    def status_enum_to_string(self, v: DeviceStatus) -> str:
        return v.value
