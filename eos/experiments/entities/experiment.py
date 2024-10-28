from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_serializer


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

    owner: str | None = None

    dynamic_parameters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    metadata: dict[str, Any] | None = None

    resume: bool = False


class Experiment(ExperimentDefinition):
    """The state of an experiment in the system."""

    status: ExperimentStatus = ExperimentStatus.CREATED

    running_tasks: list[str] = Field(default_factory=list)
    completed_tasks: list[str] = Field(default_factory=list)

    start_time: datetime | None = None
    end_time: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    class Config:
        arbitrary_types_allowed = True

    @field_serializer("status")
    def status_enum_to_string(self, v: ExperimentStatus) -> str:
        return v.value

    @classmethod
    def from_definition(cls, definition: ExperimentDefinition) -> "Experiment":
        """Create an Experiment instance from an ExperimentDefinition."""
        return cls(**definition.model_dump())
