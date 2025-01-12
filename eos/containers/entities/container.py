from typing import Any

from pydantic import BaseModel, Field

from sqlalchemy import String, JSON
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import mapped_column, Mapped

from eos.database.abstract_sql_db_interface import Base


class Container(BaseModel):
    id: str
    type: str | None = None
    lab: str | None = None

    location: str | None = None

    meta: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class ContainerModel(Base):
    """The database model for containers."""

    __tablename__ = "containers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str | None] = mapped_column(String, nullable=True)
    lab: Mapped[str | None] = mapped_column(String, nullable=True)

    location: Mapped[str | None] = mapped_column(String, nullable=True)

    meta: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False, default={})
