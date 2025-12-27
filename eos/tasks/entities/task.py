from datetime import datetime, UTC
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from sqlalchemy import String, ForeignKey, JSON, Integer, Enum as sa_Enum, DateTime, Index
from sqlalchemy.ext.mutable import MutableList, MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from eos.configuration.entities.task_def import DeviceAssignmentDef, TaskDef
from eos.resources.entities.resource import Resource
from eos.database.abstract_sql_db_interface import Base


class TaskStatus(Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskSubmission(BaseModel):
    """Task submitted to the system."""

    name: str
    type: str
    experiment_name: str | None = None

    devices: dict[str, DeviceAssignmentDef] = Field(default_factory=dict)
    input_parameters: dict[str, Any] | None = None
    input_resources: dict[str, Resource] | None = None

    priority: int = Field(0, ge=0)
    allocation_timeout: int = Field(600, ge=0)  # sec

    meta: dict[str, Any] = Field(default_factory=dict)

    @field_validator("experiment_name", mode="before")
    def empty_str_to_none(cls, v) -> str | None:
        if v == "":
            return None
        return v

    @classmethod
    def from_def(cls, config: TaskDef, experiment_name: str | None) -> "TaskSubmission":
        """Create a TaskSubmission from a TaskDef.

        Only specific device assignments (DeviceAssignmentDef) are converted to TaskSubmission.
        Dynamic devices are resolved by the scheduler and converted to specific assignments.

        If config.resources contains resource names, create minimal Resource objects to preserve the
        assignment. The task executor will replace these with full Resource objects during initialization.
        """
        specific_devices = {name: dev for name, dev in config.devices.items() if isinstance(dev, DeviceAssignmentDef)}

        # Convert resource name assignments to Resource objects so to_config() can extract them
        input_resources = None
        if config.resources:
            input_resources = {key: Resource(name=name, type="") for key, name in config.resources.items()}

        return cls(
            name=config.name,
            type=config.type,
            experiment_name=experiment_name,
            devices=specific_devices,
            input_parameters=config.parameters,
            input_resources=input_resources,
        )

    def to_def(self) -> TaskDef:
        """Convert a TaskSubmission to a TaskDef."""
        resources = {}
        if self.input_resources:
            resources = {resource_name: resource.name for resource_name, resource in self.input_resources.items()}

        return TaskDef(
            name=self.name,
            type=self.type,
            devices=self.devices,
            resources=resources,
            parameters=self.input_parameters or {},
            dependencies=[],
        )

    model_config = ConfigDict(from_attributes=True)


class Task(TaskSubmission):
    """The state of a task in the system."""

    status: TaskStatus = TaskStatus.CREATED
    output_parameters: dict[str, Any] | None = None
    output_resources: dict[str, Resource] | None = None
    output_file_names: list[str] | None = None

    start_time: datetime | None = None
    end_time: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_serializer("status")
    def status_enum_to_string(self, v: TaskStatus) -> str:
        return v.value

    @classmethod
    def from_submission(cls, submission: TaskSubmission) -> "Task":
        """Create a Task instance from a TaskSubmission."""
        return cls(**submission.model_dump())


class TaskModel(Base):
    """The database model for tasks."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    experiment_name: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("experiments.name", ondelete="CASCADE"), nullable=True
    )

    type: Mapped[str] = mapped_column(String(255), nullable=False)

    devices: Mapped[dict[str, dict]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False, default={})

    input_parameters: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON), nullable=True)
    input_resources: Mapped[dict[str, dict] | None] = mapped_column(MutableDict.as_mutable(JSON), nullable=True)

    output_parameters: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON), nullable=True)
    output_resources: Mapped[dict[str, dict] | None] = mapped_column(MutableDict.as_mutable(JSON), nullable=True)
    output_file_names: Mapped[list[str] | None] = mapped_column(MutableList.as_mutable(JSON), nullable=True)

    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allocation_timeout: Mapped[int] = mapped_column(Integer, nullable=False, default=600)

    meta: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False, default={})

    status: Mapped[TaskStatus] = mapped_column(
        sa_Enum(TaskStatus), nullable=False, default=TaskStatus.CREATED, index=True
    )

    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        # Composite unique index for (experiment_name, name)
        Index("idx_experiment_name_task_name", "experiment_name", "name", unique=True),
    )
