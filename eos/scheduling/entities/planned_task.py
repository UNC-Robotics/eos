from dataclasses import dataclass

from eos.configuration.entities.task_def import DeviceAssignmentDef


@dataclass
class PlannedTask:
    """A task start in a simulated schedule, relative to when planning began."""

    start: int
    devices: dict[str, DeviceAssignmentDef]
    resources: dict[str, str]
