from typing import Any


def is_parameter_reference(parameter: Any) -> bool:
    return (
        isinstance(parameter, str)
        and parameter.count(".") == 1
        and all(component.strip() for component in parameter.split("."))
    )


def is_dynamic_parameter(parameter: Any) -> bool:
    return isinstance(parameter, str) and parameter.lower() == "eos_dynamic"


def is_resource_reference(resource_name: str) -> bool:
    """
    Check if the resource name is a reference.
    """
    return (
        isinstance(resource_name, str)
        and resource_name.count(".") == 1
        and all(component.strip() for component in resource_name.split("."))
    )


def is_device_reference(device_value: Any) -> bool:
    """
    Check if the device value is a reference (task_name.device_name).
    """
    return (
        isinstance(device_value, str)
        and device_value.count(".") == 1
        and all(component.strip() for component in device_value.split("."))
    )
