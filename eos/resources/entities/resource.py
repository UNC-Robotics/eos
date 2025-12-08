from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sqlalchemy import String, JSON
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import mapped_column, Mapped

from eos.database.abstract_sql_db_interface import Base


class Resource(BaseModel):
    """A resource that can be used by tasks."""

    name: str
    type: str
    lab: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class ResourceModel(Base):
    """The database model for resources."""

    __tablename__ = "resources"

    name: Mapped[str] = mapped_column(String(255), nullable=False, primary_key=True)

    type: Mapped[str] = mapped_column(String(255), nullable=False)
    lab: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    meta: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False, default={})
