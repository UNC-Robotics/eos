from typing import Any

from pydantic import BaseModel, Field


class Container(BaseModel):
    id: str
    type: str | None = None
    lab: str | None = None

    location: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True
