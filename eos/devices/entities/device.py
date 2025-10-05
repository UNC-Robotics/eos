from enum import Enum
from typing import Any

from pydantic import BaseModel, field_serializer, Field
from ray.actor import ActorHandle
from sqlalchemy import String, JSON, Enum as sa_Enum, Integer, Index
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import mapped_column, Mapped

from eos.database.abstract_sql_db_interface import Base


class DeviceStatus(Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Device(BaseModel):
    name: str
    lab_name: str

    type: str
    computer: str
    status: DeviceStatus = DeviceStatus.ACTIVE
    meta: dict[str, Any] = Field(default_factory=dict)

    actor_handle: ActorHandle | None = Field(exclude=True, default=None)

    def get_actor_name(self) -> str:
        return f"{self.lab_name}.{self.name}"

    @field_serializer("status")
    def status_enum_to_string(self, v: DeviceStatus) -> str:
        return v.value

    class Config:
        arbitrary_types_allowed = True
        from_attributes = True


class DeviceModel(Base):
    """The database model for devices."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String, nullable=False)
    lab_name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    computer: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[DeviceStatus] = mapped_column(sa_Enum(DeviceStatus), nullable=False, default=DeviceStatus.ACTIVE)
    meta: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False, default={})

    __table_args__ = (
        # Composite unique index for (lab_name, name)
        Index("idx_lab_name_device_name", "lab_name", "name", unique=True),
    )
