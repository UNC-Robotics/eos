import re
from typing import Any

_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _is_dot_reference(value: Any) -> bool:
    """Check if value is a valid dotted reference (e.g., 'task_name.item_name')."""
    if not isinstance(value, str) or value.count(".") != 1:
        return False
    left, right = value.split(".")
    return bool(_IDENTIFIER_PATTERN.match(left) and _IDENTIFIER_PATTERN.match(right))


def is_parameter_reference(parameter: Any) -> bool:
    """Check if parameter is a reference to another task's parameter."""
    return _is_dot_reference(parameter)


def is_dynamic_parameter(parameter: Any) -> bool:
    """Check if parameter is marked as dynamic (resolved at runtime)."""
    return isinstance(parameter, str) and parameter.lower() == "eos_dynamic"


def is_resource_reference(resource_name: str) -> bool:
    """Check if resource name is a reference to another task's output resource."""
    return _is_dot_reference(resource_name)


def is_device_reference(device_value: Any) -> bool:
    """Check if device value is a reference to another task's device."""
    return _is_dot_reference(device_value)
