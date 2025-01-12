from eos.resource_allocation.entities.resource_allocation import (
    ResourceAllocation,
    ResourceAllocationModel,
)

from sqlalchemy import String
from sqlalchemy.orm import mapped_column, Mapped


class ContainerAllocation(ResourceAllocation):
    container_type: str


class ContainerAllocationModel(ResourceAllocationModel):
    """Model for container allocations."""

    __tablename__ = "container_allocations"

    container_type: Mapped[str] = mapped_column(String, nullable=False)
