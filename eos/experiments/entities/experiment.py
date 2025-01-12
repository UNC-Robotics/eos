from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_serializer
from sqlalchemy import DateTime, String, JSON, Enum as sa_Enum
from sqlalchemy.ext.mutable import MutableDict, MutableList
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

    id: str
    type: str

    owner: str

    priority: int = Field(0, ge=0)

    dynamic_parameters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    meta: dict[str, Any] | None = None

    resume: bool = False

    class Config:
        from_attributes = True


class Experiment(ExperimentDefinition):
    """The state of an experiment in the system."""

    status: ExperimentStatus = ExperimentStatus.CREATED

    running_tasks: list[str] = Field(default_factory=list)
    completed_tasks: list[str] = Field(default_factory=list)

    start_time: datetime | None = None
    end_time: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

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

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False)

    owner: Mapped[str] = mapped_column(String, nullable=False)

    priority: Mapped[int] = mapped_column(nullable=False, default=0)

    dynamic_parameters: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), nullable=False, default={})
    meta: Mapped[dict | None] = mapped_column(MutableDict.as_mutable(JSON), nullable=True)

    resume: Mapped[bool] = mapped_column(nullable=False, default=False)

    status: Mapped[ExperimentStatus] = mapped_column(
        sa_Enum(ExperimentStatus), nullable=False, default=ExperimentStatus.CREATED
    )

    running_tasks: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), nullable=False, default=[])
    completed_tasks: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), nullable=False, default=[])

    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.now(timezone.utc)
    )
