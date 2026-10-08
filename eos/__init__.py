"""EOS public API for user packages: ``from eos import task, Param, Context, File, Device, Resource``."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eos.devices.base_device import BaseDevice as Device
    from eos.resources.entities.resource import Resource
    from eos.tasks.file import File
    from eos.tasks.task_definition import Context, Param, task

# Resolved lazily so importing any eos submodule doesn't load the whole task API.
_EXPORTS = {
    "Context": ("eos.tasks.task_definition", "Context"),
    "Device": ("eos.devices.base_device", "BaseDevice"),
    "File": ("eos.tasks.file", "File"),
    "Param": ("eos.tasks.task_definition", "Param"),
    "Resource": ("eos.resources.entities.resource", "Resource"),
    "task": ("eos.tasks.task_definition", "task"),
}

__all__ = ["Context", "Device", "File", "Param", "Resource", "task"]


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module 'eos' has no attribute '{name}'")
    module_name, attribute = _EXPORTS[name]
    return getattr(import_module(module_name), attribute)
