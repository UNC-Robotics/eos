from dataclasses import dataclass
from typing import Any

from ray.actor import ActorHandle

from eos.utils.ray_utils import RayActorWrapper


@dataclass(frozen=True)
class DeviceActorReference:
    """Reference to a device actor with its lab, name, type, and handle."""

    name: str
    lab_name: str
    type: str
    actor_handle: ActorHandle
    meta: dict[str, Any]


def create_device_actor_dict(device_references: dict[str, DeviceActorReference]) -> dict[str, RayActorWrapper]:
    """Create a simple dict of device name to RayActorWrapper from device references.

    Args:
        device_references: Dict mapping device name (from task spec/config) to DeviceActorReference

    Returns:
        Dict mapping device name to RayActorWrapper for direct access in tasks
    """
    return {name: RayActorWrapper(ref.actor_handle, ref.meta) for name, ref in device_references.items()}
