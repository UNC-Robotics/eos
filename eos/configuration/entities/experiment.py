from typing import Any

from pydantic import BaseModel, Field

from eos.configuration.entities.task import TaskConfig


class ExperimentContainerConfig(BaseModel):
    id: str
    desc: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ExperimentConfig(BaseModel):
    type: str
    desc: str
    labs: list[str]

    tasks: list[TaskConfig]

    containers: list[ExperimentContainerConfig] = Field(default_factory=list)
