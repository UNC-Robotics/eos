from datetime import datetime, UTC
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, String, JSON, Enum as sa_Enum, Integer, Boolean, ForeignKey
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import mapped_column, Mapped
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from eos.database.abstract_sql_db_interface import Base


class CampaignSubmission(BaseModel):
    """Campaign submitted to the system."""

    name: str
    experiment_type: str

    owner: str
    priority: int = Field(0, ge=0)

    max_experiments: int = Field(0, ge=0)
    max_concurrent_experiments: int = Field(1, ge=1)

    optimize: bool
    optimizer_ip: str = "127.0.0.1"

    global_parameters: dict[str, dict[str, Any]] | None = None  # Shared across all experiments
    experiment_parameters: list[dict[str, dict[str, Any]]] | None = None  # Per-experiment (overrides global)

    meta: dict[str, Any] = Field(default_factory=dict)

    resume: bool = False

    @model_validator(mode="after")
    def validate_parameters(self) -> "CampaignSubmission":
        if not self.optimize:
            if not self.experiment_parameters and not self.global_parameters:
                raise ValueError(
                    "Campaign experiment_parameters or global_parameters must be provided if optimization is not "
                    "enabled."
                )
            if self.experiment_parameters and len(self.experiment_parameters) != self.max_experiments:
                raise ValueError(
                    "experiment_parameters must be provided for all experiments up to the max experiments if "
                    "optimization is not enabled."
                )
        return self

    model_config = ConfigDict(from_attributes=True)


class CampaignStatus(Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class Campaign(CampaignSubmission):
    """The state of a campaign in the system."""

    status: CampaignStatus = CampaignStatus.CREATED

    experiments_completed: int = Field(0, ge=0)

    pareto_solutions: list[dict[str, Any]] | None = None

    start_time: datetime | None = None
    end_time: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    @field_serializer("status")
    def status_enum_to_string(self, v: CampaignStatus) -> str:
        return v.value

    @classmethod
    def from_submission(cls, submission: CampaignSubmission) -> "Campaign":
        """Create a Campaign instance from a CampaignSubmission."""
        return cls(**submission.model_dump())


class CampaignSample(BaseModel):
    """A sample collected during campaign execution."""

    campaign_name: str
    experiment_name: str

    inputs: dict[str, Any]
    outputs: dict[str, Any]

    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    model_config = ConfigDict(from_attributes=True)


class CampaignModel(Base):
    """The database model for campaigns."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    experiment_type: Mapped[str] = mapped_column(String(255), nullable=False)

    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    max_experiments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_concurrent_experiments: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    optimize: Mapped[bool] = mapped_column(Boolean, nullable=False)
    optimizer_ip: Mapped[str] = mapped_column(String(45), nullable=False, default="127.0.0.1")

    global_parameters: Mapped[dict[str, dict[str, Any]] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    experiment_parameters: Mapped[list[dict[str, dict[str, Any]]] | None] = mapped_column(
        MutableList.as_mutable(JSON), nullable=True
    )
    meta: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False, default={})

    resume: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[CampaignStatus] = mapped_column(
        sa_Enum(CampaignStatus), nullable=False, default=CampaignStatus.CREATED, index=True
    )

    experiments_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    pareto_solutions: Mapped[list[dict[str, Any]] | None] = mapped_column(MutableList.as_mutable(JSON), nullable=True)

    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class CampaignSampleModel(Base):
    """The database model for campaign samples."""

    __tablename__ = "campaign_samples"

    campaign_name: Mapped[str] = mapped_column(String(255), ForeignKey("campaigns.name"), primary_key=True)
    experiment_name: Mapped[str] = mapped_column(String(255), ForeignKey("experiments.name"), primary_key=True)

    inputs: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False)
    outputs: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
