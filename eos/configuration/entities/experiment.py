from typing import Any

from pydantic import BaseModel, Field

from eos.configuration.entities.task import TaskConfig


class ExperimentResourceConfig(BaseModel):
    desc: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ExperimentConfig(BaseModel):
    type: str
    desc: str
    labs: list[str]

    tasks: list[TaskConfig]

    resources: dict[str, ExperimentResourceConfig] = Field(default_factory=dict)
