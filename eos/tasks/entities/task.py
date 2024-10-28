from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_serializer

from eos.configuration.entities.task import TaskDeviceConfig, TaskConfig
from eos.containers.entities.container import Container


class TaskStatus(Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskInput(BaseModel):
    parameters: dict[str, Any] | None = None
    containers: dict[str, Container] | None = None

    class Config:
        arbitrary_types_allowed = True


class TaskOutput(BaseModel):
    parameters: dict[str, Any] | None = None
    containers: dict[str, Container] | None = None
    file_names: list[str] | None = None


class TaskDefinition(BaseModel):
    """The definition of a task. Used for submission."""

    id: str
    type: str
    experiment_id: str = "on_demand"

    devices: list[TaskDeviceConfig] = Field(default_factory=list)
    input: TaskInput = Field(default_factory=TaskInput)

    resource_allocation_priority: int = Field(90, ge=0)
    resource_allocation_timeout: int = Field(600, ge=0)  # sec

    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_config(cls, config: TaskConfig, experiment_id: str) -> "TaskDefinition":
        """Create a TaskDefinition from a TaskConfig."""
        input_params = TaskInput(
            parameters=config.parameters,
            containers={
                container_name: Container(id=container_id) for container_name, container_id in config.containers.items()
            },
        )

        return cls(
            id=config.id,
            type=config.type,
            experiment_id=experiment_id,
            devices=config.devices,
            input=input_params,
        )

    def to_config(self) -> TaskConfig:
        """Convert a TaskDefinition to a TaskConfig."""
        containers = {}
        if self.input.containers:
            containers = {container_name: container.id for container_name, container in self.input.containers.items()}

        return TaskConfig(
            id=self.id,
            type=self.type,
            devices=self.devices,
            containers=containers,
            parameters=self.input.parameters or {},
            dependencies=[],
        )


class Task(TaskDefinition):
    """The state of a task in the system."""

    status: TaskStatus = TaskStatus.CREATED
    output: TaskOutput = TaskOutput()

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
