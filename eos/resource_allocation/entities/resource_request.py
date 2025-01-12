from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, field_serializer, Field
from sqlalchemy import String, JSON, Enum as sa_Enum, Integer, DateTime, ForeignKey
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import mapped_column, Mapped

from eos.database.abstract_sql_db_interface import Base


class ResourceType(Enum):
    CONTAINER = "CONTAINER"
    DEVICE = "DEVICE"


class Resource(BaseModel):
    id: str
    lab_id: str
    resource_type: ResourceType

    @field_serializer("resource_type")
    def resource_type_enum_to_string(self, v: ResourceType) -> str:
        return v.value


class ResourceAllocationRequest(BaseModel):
    requester: str
    resources: list[Resource] = Field(default_factory=list)
    experiment_id: str | None = None
    reason: str | None = None

    priority: int = Field(default=0, ge=0)
    timeout: int = Field(default=600, gt=0)

    def add_resource(self, resource_id: str, lab_id: str, resource_type: ResourceType) -> None:
        self.resources.append(Resource(id=resource_id, lab_id=lab_id, resource_type=resource_type))

    def remove_resource(self, resource_id: str, lab_id: str, resource_type: ResourceType) -> None:
        self.resources = [
            r
            for r in self.resources
            if not (r.id == resource_id and r.lab_id == lab_id and r.resource_type == resource_type)
        ]

    class Config:
        from_attributes = True


class ResourceRequestAllocationStatus(Enum):
    PENDING = "PENDING"
    ALLOCATED = "ALLOCATED"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class ActiveResourceAllocationRequest(BaseModel):
    id: int

    requester: str
    resources: list[Resource] = Field(default_factory=list)
    experiment_id: str | None = None
    reason: str | None = None

    priority: int = Field(default=0, ge=0)
    timeout: int = Field(default=600, gt=0)

    status: ResourceRequestAllocationStatus = ResourceRequestAllocationStatus.PENDING

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_serializer("status")
    def status_enum_to_string(self, v: ResourceRequestAllocationStatus) -> str:
        return v.value

    class Config:
        from_attributes = True


class ResourceAllocationRequestModel(Base):
    """The database model for resource allocation requests."""

    __tablename__ = "resource_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    requester: Mapped[str] = mapped_column(String, nullable=False)
    experiment_id: Mapped[str | None] = mapped_column(String, ForeignKey("experiments.id"), nullable=True)

    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timeout: Mapped[int] = mapped_column(Integer, nullable=False, default=600)

    reason: Mapped[str | None] = mapped_column(String, nullable=True)

    resources: Mapped[list[dict[str, Any]]] = mapped_column(MutableList.as_mutable(JSON), nullable=False, default=[])

    status: Mapped[ResourceRequestAllocationStatus] = mapped_column(
        sa_Enum(ResourceRequestAllocationStatus), nullable=False, default=ResourceRequestAllocationStatus.PENDING
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc)
    )
    allocated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
