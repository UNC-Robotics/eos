from datetime import datetime, UTC
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, String, JSON, Boolean, Index
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import mapped_column, Mapped

from eos.database.abstract_sql_db_interface import Base


class Specification(BaseModel):
    """A specification entity (task, device, lab, or experiment spec)."""

    spec_type: str
    spec_name: str
    spec_data: dict[str, Any]
    is_loaded: bool = False
    package_name: str
    source_path: str

    model_config = ConfigDict(from_attributes=True)


class SpecificationModel(Base):
    """The database model for specifications."""

    __tablename__ = "specifications"

    spec_type: Mapped[str] = mapped_column(String(255), nullable=False, primary_key=True)
    spec_name: Mapped[str] = mapped_column(String(255), nullable=False, primary_key=True)

    spec_data: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False)
    is_loaded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    package_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        # Index on spec_type for fast filtering
        Index("idx_spec_type", "spec_type"),
    )
