from typing import Any

from pydantic import BaseModel, Field

from eos.configuration.entities.task_def import TaskDef


class ExperimentResourceDef(BaseModel):
    desc: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ExperimentDef(BaseModel):
    type: str
    desc: str
    labs: list[str]

    tasks: list[TaskDef]

    resources: dict[str, ExperimentResourceDef] = Field(default_factory=dict)
