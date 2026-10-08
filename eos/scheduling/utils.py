from collections.abc import Callable, Iterable, Mapping

import networkx as nx

from eos.configuration.entities.task_def import (
    DeviceAssignmentDef,
    DynamicDeviceAssignmentDef,
    DynamicResourceAssignmentDef,
    TaskDef,
)
from eos.configuration.protocol_graph import ProtocolGraph
from eos.configuration.utils import is_device_reference, is_resource_reference


def filter_device_pool(req: DynamicDeviceAssignmentDef, pool: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Filter an iterable of (lab_name, device_name) by req constraints and sort deterministically."""
    filtered = list(pool)

    if req.allowed_labs:
        allowed_labs = set(req.allowed_labs)
        filtered = [(lab, dev) for (lab, dev) in filtered if lab in allowed_labs]

    if req.allowed_devices:
        allowed_set = {(d.lab_name, d.name) for d in req.allowed_devices}
        filtered = [(lab, dev) for (lab, dev) in filtered if (lab, dev) in allowed_set]

    filtered.sort(key=lambda x: (x[0], x[1]))
    return filtered


def sort_resource_pool(names: Iterable[str]) -> list[str]:
    """Return a deterministically sorted list of resource names."""
    lst = list(names)
    lst.sort()
    return lst


def resolve_device_root(
    tasks: Mapping[str, TaskDef], ref_task_name: str, ref_device_name: str
) -> tuple[str, str, object] | None:
    """Follow device references to the root definition. Returns (task, device, value) or None on a cycle."""
    return _resolve_root(tasks, ref_task_name, ref_device_name, "devices", is_device_reference)


def resolve_resource_root(
    tasks: Mapping[str, TaskDef], ref_task_name: str, ref_resource_name: str
) -> tuple[str, str, object] | None:
    """Follow resource references to the root definition. Returns (task, resource, value) or None on a cycle."""
    return _resolve_root(tasks, ref_task_name, ref_resource_name, "resources", is_resource_reference)


def _resolve_root(
    tasks: Mapping[str, TaskDef], task_name: str, slot: str, section: str, is_reference: Callable[[str], bool]
) -> tuple[str, str, object] | None:
    visited: set[tuple[str, str]] = set()
    while (task_name, slot) not in visited:
        visited.add((task_name, slot))
        value = getattr(tasks[task_name], section).get(slot)
        if not (isinstance(value, str) and is_reference(value)):
            return task_name, slot, value
        task_name, slot = value.split(".")
    return None


def _device_identity(tasks: Mapping[str, TaskDef], task_name: str, slot: str, value: object) -> tuple | None:
    """Identify the device a slot will use: a specific device or the dynamic slot it is rooted at."""
    if isinstance(value, str) and is_device_reference(value):
        root = resolve_device_root(tasks, *value.split("."))
        if root is None:
            return None
        task_name, slot, value = root
    if isinstance(value, DynamicDeviceAssignmentDef):
        return ("dynamic", task_name, slot)
    if isinstance(value, DeviceAssignmentDef):
        return ("device", value.lab_name, value.name)
    return None


def _resource_identity(tasks: Mapping[str, TaskDef], task_name: str, slot: str, value: object) -> tuple | None:
    """Identify the resource a slot will use: a specific resource or the dynamic slot it is rooted at."""
    if isinstance(value, str) and is_resource_reference(value):
        root = resolve_resource_root(tasks, *value.split("."))
        if root is None:
            return None
        task_name, slot, value = root
    if isinstance(value, DynamicResourceAssignmentDef):
        return ("dynamic", task_name, slot)
    if isinstance(value, str) and not is_resource_reference(value):
        return ("resource", value)
    return None


def compute_hold_users(
    protocol_graph: ProtocolGraph,
) -> tuple[dict[tuple[str, str], frozenset[str]], dict[tuple[str, str], frozenset[str]]]:
    """
    Map each held (task, slot) to the descendant tasks that reuse the same device or resource.

    A hold only needs to persist while one of these tasks is still pending.
    Returns (device_hold_users, resource_hold_users).
    """
    task_graph = protocol_graph.get_task_graph()
    tasks = {name: protocol_graph.get_task(name) for name in task_graph.nodes}
    device_ids = {
        name: {slot: _device_identity(tasks, name, slot, value) for slot, value in task.devices.items()}
        for name, task in tasks.items()
    }
    resource_ids = {
        name: {slot: _resource_identity(tasks, name, slot, value) for slot, value in task.resources.items()}
        for name, task in tasks.items()
    }

    device_users: dict[tuple[str, str], frozenset[str]] = {}
    resource_users: dict[tuple[str, str], frozenset[str]] = {}
    for name, task in tasks.items():
        descendants = nx.descendants(task_graph, name)
        for holds, ids, users in (
            (task.device_holds, device_ids, device_users),
            (task.resource_holds, resource_ids, resource_users),
        ):
            for slot, held in holds.items():
                identity = ids[name].get(slot)
                if held and identity is not None:
                    users[(name, slot)] = frozenset(d for d in descendants if identity in ids[d].values())

    return device_users, resource_users


def _item_key(identity: tuple | None) -> tuple[str, str] | str | None:
    """The allocation index key of a specific device or resource, or None for a dynamic one."""
    if identity is None or identity[0] == "dynamic":
        return None
    return (identity[1], identity[2]) if identity[0] == "device" else identity[1]


def compute_hold_needs(
    protocol_graph: ProtocolGraph,
    device_users: dict[tuple[str, str], frozenset[str]],
    resource_users: dict[tuple[str, str], frozenset[str]],
) -> tuple[dict[tuple[str, str], frozenset], dict[tuple[str, str], frozenset]]:
    """
    Map each held (task, slot) to the other specific devices and resources its hold users need.

    A hold must not start while another protocol run holds one of these, or both could wait on each other forever.
    Returns (device_hold_needs, resource_hold_needs) as allocation index keys.
    """
    tasks = {name: protocol_graph.get_task(name) for name in protocol_graph.get_task_graph().nodes}
    items: dict[str, dict[tuple[str, str], object]] = {}
    for name, task in tasks.items():
        items[name] = {
            ("device", slot): _item_key(_device_identity(tasks, name, slot, v)) for slot, v in task.devices.items()
        }
        items[name] |= {
            ("resource", slot): _item_key(_resource_identity(tasks, name, slot, v))
            for slot, v in task.resources.items()
        }

    device_needs: dict[tuple[str, str], frozenset] = {}
    resource_needs: dict[tuple[str, str], frozenset] = {}
    for kind, holds, needs in (("device", device_users, device_needs), ("resource", resource_users, resource_needs)):
        for (task_name, slot), users in holds.items():
            held = items[task_name].get((kind, slot))
            needs[(task_name, slot)] = frozenset(
                item for user in users for item in items[user].values() if item is not None and item != held
            )
    return device_needs, resource_needs
