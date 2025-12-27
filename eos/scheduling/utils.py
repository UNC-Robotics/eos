from collections.abc import Iterable

from eos.configuration.entities.task_def import DynamicDeviceAssignmentDef


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
