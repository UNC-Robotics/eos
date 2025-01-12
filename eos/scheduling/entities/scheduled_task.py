from pydantic import BaseModel

from eos.configuration.entities.task import TaskDeviceConfig
from eos.resource_allocation.entities.resource_request import ActiveResourceAllocationRequest


class ScheduledTask(BaseModel):
    id: str
    experiment_id: str
    devices: list[TaskDeviceConfig]
    allocated_resources: ActiveResourceAllocationRequest | None
