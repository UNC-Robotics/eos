from dataclasses import dataclass

from eos.configuration.entities.task_def import DeviceAssignmentDef
from eos.allocation.entities.allocation_request import ActiveAllocationRequest


@dataclass(slots=True, frozen=True)
class ScheduledTask:
    name: str
    experiment_name: str
    devices: dict[str, DeviceAssignmentDef]
    resources: dict[str, str]
    allocations: ActiveAllocationRequest | None
