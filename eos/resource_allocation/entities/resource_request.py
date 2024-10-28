from datetime import datetime, timezone
from enum import Enum

from bson import ObjectId
from pydantic import BaseModel, field_serializer, Field


class ResourceType(Enum):
    CONTAINER = "CONTAINER"
    DEVICE = "DEVICE"


class Resource(BaseModel):
    id: str
    lab_id: str
    resource_type: ResourceType

    @field_serializer("resource_type")
    def resource_type_enum_to_string(self, v: ResourceType) -> str:
        return v.value


class ResourceAllocationRequest(BaseModel):
    requester: str
    resources: list[Resource] = Field(default_factory=list)
    experiment_id: str | None = None
    reason: str | None = None
    priority: int = Field(default=100, gt=0)

    def add_resource(self, resource_id: str, lab_id: str, resource_type: ResourceType) -> None:
        self.resources.append(Resource(id=resource_id, lab_id=lab_id, resource_type=resource_type))

    def remove_resource(self, resource_id: str, lab_id: str, resource_type: ResourceType) -> None:
        self.resources = [
            r
            for r in self.resources
            if not (r.id == resource_id and r.lab_id == lab_id and r.resource_type == resource_type)
        ]


class ResourceRequestAllocationStatus(Enum):
    PENDING = "PENDING"
    ALLOCATED = "ALLOCATED"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class ActiveResourceAllocationRequest(BaseModel):
    id: ObjectId = Field(default_factory=ObjectId, alias="_id")
    request: ResourceAllocationRequest
    status: ResourceRequestAllocationStatus = ResourceRequestAllocationStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    allocated_at: datetime | None = None

    class Config:
        arbitrary_types_allowed = True
        populate_by_name = True

    @field_serializer("status")
    def status_enum_to_string(self, v: ResourceRequestAllocationStatus) -> str:
        return v.value
