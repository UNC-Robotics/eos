from datetime import datetime, timezone

from pydantic import BaseModel

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import mapped_column, Mapped

from eos.database.abstract_sql_db_interface import Base


class ResourceAllocation(BaseModel):
    id: str
    owner: str
    experiment_id: str | None = None
    created_at: datetime = datetime.now(tz=timezone.utc)

    class Config:
        arbitrary_types_allowed = True
        from_attributes = True


class ResourceAllocationModel(Base):
    """Base model for resource allocations."""

    __abstract__ = True

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    experiment_id: Mapped[str | None] = mapped_column(String, ForeignKey("experiments.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
