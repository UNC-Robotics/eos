from datetime import datetime, timezone

from pydantic import BaseModel

from sqlalchemy import String, DateTime, ForeignKey, Integer, Index, Enum as sa_Enum
from sqlalchemy.orm import mapped_column, Mapped

from eos.database.abstract_sql_db_interface import Base
from eos.allocation.entities.allocation_request import AllocationType


class Allocation(BaseModel):
    """Unified allocation for devices and resources."""

    name: str
    allocation_type: AllocationType
    lab_name: str | None  # Only for DEVICE allocations
    item_type: str  # device_type or resource_type
    owner: str
    experiment_name: str | None = None
    created_at: datetime = datetime.now(tz=timezone.utc)

    class Config:
        arbitrary_types_allowed = True
        from_attributes = True


class AllocationModel(Base):
    """Unified database model for device and resource allocations."""

    __tablename__ = "allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    allocation_type: Mapped[AllocationType] = mapped_column(sa_Enum(AllocationType), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    lab_name: Mapped[str | None] = mapped_column(String, nullable=True)  # Only for DEVICE
    item_type: Mapped[str] = mapped_column(String, nullable=False)  # device_type or resource_type

    owner: Mapped[str] = mapped_column(String, nullable=False)
    experiment_name: Mapped[str | None] = mapped_column(String, ForeignKey("experiments.name"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        # Composite unique constraint for (allocation_type, lab_name, name)
        # For DEVICE: (DEVICE, lab_name, name) must be unique
        # For RESOURCE: (RESOURCE, NULL, name) must be unique
        Index("idx_allocation_type_lab_name_name", "allocation_type", "lab_name", "name", unique=True),
    )
