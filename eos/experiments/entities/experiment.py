from datetime import datetime, UTC
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer
from sqlalchemy import DateTime, String, JSON, Enum as sa_Enum, Integer, ForeignKey
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import mapped_column, Mapped

from eos.database.abstract_sql_db_interface import Base


class ExperimentStatus(Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class ExperimentDefinition(BaseModel):
    """The definition of an experiment. Used for submission."""

    name: str
    type: str

    owner: str

    priority: int = Field(0, ge=0)

    parameters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    meta: dict[str, Any] | None = None

    resume: bool = False

    model_config = ConfigDict(from_attributes=True)


class Experiment(ExperimentDefinition):
    """The state of an experiment in the system."""

    campaign: str | None = None

    status: ExperimentStatus = ExperimentStatus.CREATED

    start_time: datetime | None = None
    end_time: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    @field_serializer("status")
    def status_enum_to_string(self, v: ExperimentStatus) -> str:
        return v.value

    @classmethod
    def from_definition(cls, definition: ExperimentDefinition) -> "Experiment":
        """Create an Experiment instance from an ExperimentDefinition."""
        return cls(**definition.model_dump())


class ExperimentModel(Base):
    """The database model for experiments."""

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    type: Mapped[str] = mapped_column(String(255), nullable=False)

    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign: Mapped[str | None] = mapped_column(String(255), ForeignKey("campaigns.name"), nullable=True, index=True)

    priority: Mapped[int] = mapped_column(nullable=False, default=0)

    parameters: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), nullable=False, default={})
    meta: Mapped[dict | None] = mapped_column(MutableDict.as_mutable(JSON), nullable=True)

    resume: Mapped[bool] = mapped_column(nullable=False, default=False)

    status: Mapped[ExperimentStatus] = mapped_column(
        sa_Enum(ExperimentStatus), nullable=False, default=ExperimentStatus.CREATED, index=True
    )

    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
