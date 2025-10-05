from dataclasses import dataclass

from eos.configuration.entities.task import TaskDeviceConfig
from eos.allocation.entities.allocation_request import ActiveAllocationRequest


@dataclass(slots=True, frozen=True)
class ScheduledTask:
    name: str
    experiment_name: str
    devices: dict[str, TaskDeviceConfig]
    resources: dict[str, str]
    allocations: ActiveAllocationRequest | None
