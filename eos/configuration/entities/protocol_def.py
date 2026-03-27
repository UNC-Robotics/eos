from typing import Any

from pydantic import BaseModel, Field

from eos.configuration.entities.task_def import TaskDef


class ProtocolResourceDef(BaseModel):
    desc: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ProtocolDef(BaseModel):
    type: str
    desc: str
    labs: list[str]

    tasks: list[TaskDef]

    resources: dict[str, ProtocolResourceDef] = Field(default_factory=dict)
