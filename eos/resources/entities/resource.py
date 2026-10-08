from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from sqlalchemy import String, JSON
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import mapped_column, Mapped

from eos.database.abstract_sql_db_interface import Base


class Resource(BaseModel):
    """A resource that can be used by tasks. Subclass with ``type="..."`` to declare a resource type for tasks."""

    name: str
    type: str
    lab: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)

    resource_type: ClassVar[str | None] = None

    def __init_subclass__(cls, type: str | None = None, **kwargs: Any) -> None:  # noqa: A002
        super().__init_subclass__(**kwargs)
        if type is not None:
            cls.resource_type = type

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        if extra_fields := cls.model_fields.keys() - Resource.model_fields.keys():
            raise TypeError(f"Resource type '{cls.__name__}' cannot declare fields {sorted(extra_fields)}. Use meta.")


class ResourceModel(Base):
    """The database model for resources."""

    __tablename__ = "resources"

    name: Mapped[str] = mapped_column(String(255), nullable=False, primary_key=True)

    type: Mapped[str] = mapped_column(String(255), nullable=False)
    lab: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    meta: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False, default={})
