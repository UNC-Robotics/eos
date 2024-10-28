from typing import Any

from pydantic import BaseModel

from eos.configuration.entities.task import TaskConfig


class ExperimentContainerConfig(BaseModel):
    id: str
    desc: str | None = None
    metadata: dict[str, Any] | None = None


class ExperimentConfig(BaseModel):
    type: str
    desc: str
    labs: list[str]

    tasks: list[TaskConfig]

    containers: list[ExperimentContainerConfig] | None = None
