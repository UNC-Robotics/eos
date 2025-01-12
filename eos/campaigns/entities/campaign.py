from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, String, JSON, Enum as sa_Enum, Integer, Boolean, ForeignKey
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import mapped_column, Mapped
from pydantic import BaseModel, Field, field_serializer, model_validator

from eos.database.abstract_sql_db_interface import Base


class CampaignDefinition(BaseModel):
    """The definition of a campaign. Used for submission."""

    id: str
    experiment_type: str

    owner: str
    priority: int = Field(0, ge=0)

    max_experiments: int = Field(0, ge=0)
    max_concurrent_experiments: int = Field(1, ge=1)

    optimize: bool
    optimizer_computer_ip: str = "127.0.0.1"

    dynamic_parameters: list[dict[str, dict[str, Any]]] | None = None

    meta: dict[str, Any] = Field(default_factory=dict)

    resume: bool = False

    @model_validator(mode="after")
    def validate_dynamic_parameters(self) -> "CampaignDefinition":
        if not self.optimize:
            if not self.dynamic_parameters:
                raise ValueError("Campaign dynamic parameters must be provided if optimization is not enabled.")
            if len(self.dynamic_parameters) != self.max_experiments:
                raise ValueError(
                    "Dynamic parameters must be provided for all experiments up to the max experiments if "
                    "optimization is not enabled."
                )
        return self

    class Config:
        from_attributes = True


class CampaignStatus(Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class Campaign(CampaignDefinition):
    """The state of a campaign in the system."""

    status: CampaignStatus = CampaignStatus.CREATED

    experiments_completed: int = Field(0, ge=0)
    current_experiment_ids: list[str] = Field(default_factory=list)

    pareto_solutions: list[dict[str, Any]] | None = None

    start_time: datetime | None = None
    end_time: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    @field_serializer("status")
    def status_enum_to_string(self, v: CampaignStatus) -> str:
        return v.value

    @classmethod
    def from_definition(cls, definition: CampaignDefinition) -> "Campaign":
        """Create a Campaign instance from a CampaignDefinition."""
        return cls(**definition.model_dump())


class CampaignSample(BaseModel):
    """A sample collected during campaign execution."""

    campaign_id: str
    experiment_id: str

    inputs: dict[str, Any]
    outputs: dict[str, Any]

    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    class Config:
        from_attributes = True


class CampaignModel(Base):
    """The database model for campaigns."""

    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    experiment_type: Mapped[str] = mapped_column(String, nullable=False)

    owner: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    max_experiments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_concurrent_experiments: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    optimize: Mapped[bool] = mapped_column(Boolean, nullable=False)
    optimizer_computer_ip: Mapped[str] = mapped_column(String, nullable=False, default="127.0.0.1")

    dynamic_parameters: Mapped[list[dict[str, dict[str, Any]]] | None] = mapped_column(
        MutableList.as_mutable(JSON), nullable=True
    )
    meta: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False, default={})

    resume: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[CampaignStatus] = mapped_column(
        sa_Enum(CampaignStatus), nullable=False, default=CampaignStatus.CREATED
    )

    experiments_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_experiment_ids: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), nullable=False, default=[])

    pareto_solutions: Mapped[list[dict[str, Any]] | None] = mapped_column(MutableList.as_mutable(JSON), nullable=True)

    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class CampaignSampleModel(Base):
    """The database model for campaign samples."""

    __tablename__ = "campaign_samples"

    campaign_id: Mapped[str] = mapped_column(String, ForeignKey("campaigns.id"), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(String, ForeignKey("experiments.id"), primary_key=True)

    inputs: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False)
    outputs: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
