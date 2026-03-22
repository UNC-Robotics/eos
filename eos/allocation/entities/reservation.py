from datetime import datetime, UTC
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import String, Integer, DateTime, Enum as sa_Enum, JSON
from sqlalchemy.orm import mapped_column, Mapped

from eos.database.abstract_sql_db_interface import Base


class ReservationStatus(Enum):
    """Status of a manual device/resource reservation."""

    PENDING = "PENDING"
    GRANTED = "GRANTED"
    CANCELLED = "CANCELLED"


class Reservation(BaseModel):
    """A manual reservation request from a scientist for devices/resources."""

    id: int = 0
    owner: str
    priority: int = Field(default=100, ge=0)
    status: ReservationStatus = ReservationStatus.PENDING
    devices: list[tuple[str, str]] = Field(default_factory=list)  # [(lab_name, device_name)]
    resources: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    model_config = ConfigDict(from_attributes=True)


class ReservationModel(Base):
    """Database model for manual reservations."""

    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    status: Mapped[ReservationStatus] = mapped_column(
        sa_Enum(ReservationStatus), nullable=False, default=ReservationStatus.PENDING, index=True
    )
    devices: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    resources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
