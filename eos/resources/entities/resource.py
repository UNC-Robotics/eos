from typing import Any

from pydantic import BaseModel, Field

from sqlalchemy import String, JSON, Integer
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import mapped_column, Mapped

from eos.database.abstract_sql_db_interface import Base


class Resource(BaseModel):
    """A resource that can be used by tasks."""

    name: str
    type: str
    meta: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class ResourceModel(Base):
    """The database model for resources."""

    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False, default={})
