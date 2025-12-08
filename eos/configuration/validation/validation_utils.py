import re
from typing import Any

# Pattern for valid identifier: starts with letter or underscore, followed by letters, digits, or underscores
_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def is_parameter_reference(parameter: Any) -> bool:
    if not isinstance(parameter, str) or parameter.count(".") != 1:
        return False
    task_name, param_name = parameter.split(".")
    # Both parts must be valid identifiers
    return bool(_IDENTIFIER_PATTERN.match(task_name) and _IDENTIFIER_PATTERN.match(param_name))


def is_dynamic_parameter(parameter: Any) -> bool:
    return isinstance(parameter, str) and parameter.lower() == "eos_dynamic"


def is_resource_reference(resource_name: str) -> bool:
    """
    Check if the resource name is a reference (task_name.resource_name).
    """
    if not isinstance(resource_name, str) or resource_name.count(".") != 1:
        return False
    task_name, ref_name = resource_name.split(".")
    return bool(_IDENTIFIER_PATTERN.match(task_name) and _IDENTIFIER_PATTERN.match(ref_name))


def is_device_reference(device_value: Any) -> bool:
    """
    Check if the device value is a reference (task_name.device_name).
    """
    if not isinstance(device_value, str) or device_value.count(".") != 1:
        return False
    task_name, device_name = device_value.split(".")
    return bool(_IDENTIFIER_PATTERN.match(task_name) and _IDENTIFIER_PATTERN.match(device_name))
