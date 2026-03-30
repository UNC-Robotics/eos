from dataclasses import dataclass

from eos.configuration.entities.task_def import DeviceAssignmentDef


@dataclass(slots=True, frozen=True)
class ScheduledTask:
    """A task ready for execution with its concrete device and resource assignments."""

    name: str
    protocol_run_name: str | None
    devices: dict[str, DeviceAssignmentDef]
    resources: dict[str, str]
