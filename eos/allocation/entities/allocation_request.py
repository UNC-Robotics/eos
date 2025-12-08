from datetime import datetime, UTC
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_serializer, Field
from sqlalchemy import String, Enum as sa_Enum, Integer, DateTime, ForeignKey
from sqlalchemy.orm import mapped_column, Mapped, relationship

from eos.database.abstract_sql_db_interface import Base
from eos.allocation.entities.allocation_request_device import AllocationRequestDeviceModel
from eos.allocation.entities.allocation_request_resource import AllocationRequestResourceModel


class AllocationType(Enum):
    """Types of items that can be allocated."""

    RESOURCE = "RESOURCE"  # General resources (beakers, vials, etc.)
    DEVICE = "DEVICE"  # Devices


class AllocationRequestItem(BaseModel):
    """An item (resource or device) to be allocated in a request."""

    name: str
    lab_name: str
    allocation_type: AllocationType

    @field_serializer("allocation_type")
    def allocation_type_enum_to_string(self, v: AllocationType) -> str:
        return v.value


class AllocationRequest(BaseModel):
    """Request for allocation of resources and/or devices."""

    requester: str
    allocations: list[AllocationRequestItem] = Field(default_factory=list)
    experiment_name: str | None = None
    reason: str | None = None

    priority: int = Field(default=0, ge=0)
    timeout: int = Field(default=600, gt=0)

    def add_allocation(self, item_name: str, lab_name: str, allocation_type: AllocationType) -> None:
        self.allocations.append(
            AllocationRequestItem(name=item_name, lab_name=lab_name, allocation_type=allocation_type)
        )

    def remove_allocation(self, item_name: str, lab_name: str, allocation_type: AllocationType) -> None:
        self.allocations = [
            a
            for a in self.allocations
            if not (a.name == item_name and a.lab_name == lab_name and a.allocation_type == allocation_type)
        ]

    model_config = ConfigDict(from_attributes=True)


class AllocationRequestStatus(Enum):
    PENDING = "PENDING"
    ALLOCATED = "ALLOCATED"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class ActiveAllocationRequest(BaseModel):
    """An active allocation request being processed."""

    id: int

    requester: str
    allocations: list[AllocationRequestItem] = Field(default_factory=list)
    experiment_name: str | None = None
    reason: str | None = None

    priority: int = Field(default=0, ge=0)
    timeout: int = Field(default=600, gt=0)

    status: AllocationRequestStatus = AllocationRequestStatus.PENDING

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_serializer("status")
    def status_enum_to_string(self, v: AllocationRequestStatus) -> str:
        return v.value

    model_config = ConfigDict(from_attributes=True)


class AllocationRequestModel(Base):
    """Database model for allocation requests."""

    __tablename__ = "allocation_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    requester: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    experiment_name: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("experiments.name"), nullable=True, index=True
    )

    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timeout: Mapped[int] = mapped_column(Integer, nullable=False, default=600)

    reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    status: Mapped[AllocationRequestStatus] = mapped_column(
        sa_Enum(AllocationRequestStatus), nullable=False, default=AllocationRequestStatus.PENDING, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=UTC)
    )
    allocated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships to allocation request items
    devices: Mapped[list[AllocationRequestDeviceModel]] = relationship(
        "AllocationRequestDeviceModel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    resources: Mapped[list[AllocationRequestResourceModel]] = relationship(
        "AllocationRequestResourceModel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
