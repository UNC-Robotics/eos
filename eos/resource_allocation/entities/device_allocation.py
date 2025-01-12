from eos.resource_allocation.entities.resource_allocation import (
    ResourceAllocation,
    ResourceAllocationModel,
)

from sqlalchemy import String
from sqlalchemy.orm import mapped_column, Mapped


class DeviceAllocation(ResourceAllocation):
    lab_id: str
    device_type: str


class DeviceAllocationModel(ResourceAllocationModel):
    """Model for device allocations."""

    __tablename__ = "device_allocations"

    lab_id: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    device_type: Mapped[str] = mapped_column(String, nullable=False)
