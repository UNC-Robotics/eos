from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_serializer, model_validator


class CampaignDefinition(BaseModel):
    """The definition of a campaign. Used for submission."""

    id: str
    experiment_type: str

    max_experiments: int = Field(0, ge=0)
    max_concurrent_experiments: int = Field(1, ge=1)

    optimize: bool
    optimizer_computer_ip: str = "127.0.0.1"

    dynamic_parameters: list[dict[str, dict[str, Any]]] | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

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

    class Config:
        arbitrary_types_allowed = True

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
