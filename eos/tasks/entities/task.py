from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_serializer
from sqlalchemy import String, ForeignKey, JSON, Integer, Enum as sa_Enum, DateTime, Index
from sqlalchemy.ext.mutable import MutableList, MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from eos.configuration.entities.task import TaskDeviceConfig, TaskConfig
from eos.containers.entities.container import Container
from eos.database.abstract_sql_db_interface import Base


class TaskStatus(Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskDefinition(BaseModel):
    """The definition of a task. Used for submission."""

    id: str
    type: str
    experiment_id: str | None = None

    devices: list[TaskDeviceConfig] = Field(default_factory=list)
    input_parameters: dict[str, Any] | None = None
    input_containers: dict[str, Container] | None = None

    priority: int = Field(0, ge=0)
    resource_allocation_timeout: int = Field(600, ge=0)  # sec

    meta: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_config(cls, config: TaskConfig, experiment_id: str | None) -> "TaskDefinition":
        """Create a TaskDefinition from a TaskConfig."""
        return cls(
            id=config.id,
            type=config.type,
            experiment_id=experiment_id,
            devices=config.devices,
            input_parameters=config.parameters,
            input_containers={
                container_name: Container(id=container_id) for container_name, container_id in config.containers.items()
            },
        )

    def to_config(self) -> TaskConfig:
        """Convert a TaskDefinition to a TaskConfig."""
        containers = {}
        if self.input_containers:
            containers = {container_name: container.id for container_name, container in self.input_containers.items()}

        return TaskConfig(
            id=self.id,
            type=self.type,
            devices=self.devices,
            containers=containers,
            parameters=self.input_parameters or {},
            dependencies=[],
        )

    class Config:
        from_attributes = True


class Task(TaskDefinition):
    """The state of a task in the system."""

    status: TaskStatus = TaskStatus.CREATED
    output_parameters: dict[str, Any] | None = None
    output_containers: dict[str, Container] | None = None
    output_file_names: list[str] | None = None

    start_time: datetime | None = None
    end_time: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    class Config:
        arbitrary_types_allowed = True

    @field_serializer("status")
    def status_enum_to_string(self, v: TaskStatus) -> str:
        return v.value

    @classmethod
    def from_definition(cls, definition: TaskDefinition) -> "Task":
        """Create a Task instance from a TaskDefinition."""
        return cls(**definition.model_dump())


class TaskModel(Base):
    """The database model for tasks."""

    __tablename__ = "tasks"

    # Global unique identifier
    uid: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    id: Mapped[str] = mapped_column(String, nullable=False)
    experiment_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=True
    )

    type: Mapped[str] = mapped_column(String, nullable=False)

    devices: Mapped[list[dict]] = mapped_column(MutableList.as_mutable(JSON), nullable=False, default=[])

    input_parameters: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON), nullable=True)
    input_containers: Mapped[dict[str, dict] | None] = mapped_column(MutableDict.as_mutable(JSON), nullable=True)

    output_parameters: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON), nullable=True)
    output_containers: Mapped[dict[str, dict] | None] = mapped_column(MutableDict.as_mutable(JSON), nullable=True)
    output_file_names: Mapped[list[str] | None] = mapped_column(MutableList.as_mutable(JSON), nullable=True)

    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resource_allocation_timeout: Mapped[int] = mapped_column(Integer, nullable=False, default=600)

    meta: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False, default={})

    status: Mapped[TaskStatus] = mapped_column(sa_Enum(TaskStatus), nullable=False, default=TaskStatus.CREATED)

    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.now(timezone.utc)
    )

    __table_args__ = (
        # Composite unique index for (id, experiment_id)
        Index("idx_experiment_id_task_id", "experiment_id", "id", unique=True),
    )
