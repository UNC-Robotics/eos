from datetime import datetime, UTC

from pydantic import BaseModel, ConfigDict, Field

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import mapped_column, Mapped

from eos.database.abstract_sql_db_interface import Base


class ResourceAllocation(BaseModel):
    """Allocation for a resource."""

    name: str
    owner: str
    experiment_name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    model_config = ConfigDict(from_attributes=True)


class ResourceAllocationModel(Base):
    """Database model for resource allocations."""

    __tablename__ = "resource_allocations"

    name: Mapped[str] = mapped_column(String(255), ForeignKey("resources.name"), nullable=False, primary_key=True)

    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    experiment_name: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("experiments.name"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
