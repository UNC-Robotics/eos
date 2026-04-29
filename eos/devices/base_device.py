import asyncio
import atexit
import functools
import inspect
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from eos.devices.exceptions import (
    EosDeviceInitializationError,
    EosDeviceCleanupError,
)


def register_async_exit_callback(async_fn, *args, **kwargs) -> None:
    """
    Register an async function to run at program exit.
    """

    async def _run_async_fn() -> None:
        await async_fn(*args, **kwargs)

    def _run_on_exit() -> None:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_run_async_fn())
        loop.close()

    atexit.register(_run_on_exit)


class DeviceStatus(Enum):
    DISABLED = "DISABLED"
    IDLE = "IDLE"
    BUSY = "BUSY"
    ERROR = "ERROR"


class BaseDevice(ABC):
    """
    The base class for all devices in EOS.
    """

    def __init__(
        self,
        device_name: str,
        lab_name: str,
        device_type: str,
    ):
        self._device_name = device_name
        self._lab_name = lab_name
        self._device_type = device_type
        self._status = DeviceStatus.DISABLED
        self._init_parameters = {}

        self._lock = asyncio.Lock()

        register_async_exit_callback(self.cleanup)

    async def initialize(self, init_parameters: dict[str, Any]) -> None:
        """
        Initialize the device. After calling this method, the device is ready to be used for tasks
        and the status is IDLE.
        """
        async with self._lock:
            if self._status != DeviceStatus.DISABLED:
                raise EosDeviceInitializationError(f"Device {self._device_name} is already initialized.")

            try:
                await self._initialize(init_parameters)
                self._status = DeviceStatus.IDLE
                self._init_parameters = init_parameters
            except Exception as e:
                self._status = DeviceStatus.ERROR
                raise EosDeviceInitializationError(
                    f"Error initializing device {self._device_name}: {e!s}",
                ) from e

    async def cleanup(self) -> None:
        """
        Clean up the device. After calling this method, the device can no longer be used for tasks and the status is
        DISABLED.
        """
        async with self._lock:
            if self._status == DeviceStatus.DISABLED:
                return

            if self._status == DeviceStatus.BUSY:
                raise EosDeviceCleanupError(
                    f"Device {self._device_name} is busy. Cannot perform cleanup.",
                )

            try:
                await self._cleanup()
                self._status = DeviceStatus.DISABLED
            except Exception as e:
                self._status = DeviceStatus.ERROR
                raise EosDeviceCleanupError(f"Error cleaning up device {self._device_name}: {e!s}") from e

    async def report(self) -> dict[str, Any]:
        """
        Return a dictionary with any member variables needed for logging purposes and progress tracking.
        """
        return await self._report()

    async def enable(self) -> None:
        """
        Enable the device. The status should be IDLE after calling this method.
        """
        if self._status == DeviceStatus.DISABLED:
            await self.initialize(self._init_parameters)

    async def disable(self) -> None:
        """
        Disable the device. The status should be DISABLED after calling this method.
        """
        if self._status != DeviceStatus.DISABLED:
            await self.cleanup()

    def get_status(self) -> dict[str, Any]:
        return {
            "name": self._device_name,
            "lab_name": self._lab_name,
            "status": self._status,
        }

    def get_name(self) -> str:
        return self._device_name

    def get_lab_name(self) -> str:
        return self._lab_name

    def get_device_type(self) -> str:
        return self._device_type

    def get_init_parameters(self) -> dict[str, Any]:
        return self._init_parameters

    @property
    def name(self) -> str:
        return self._device_name

    @property
    def lab_name(self) -> str:
        return self._lab_name

    @property
    def device_type(self) -> str:
        return self._device_type

    @property
    def status(self) -> DeviceStatus:
        return self._status

    @property
    def init_parameters(self) -> dict[str, Any]:
        return self._init_parameters

    def get_available_functions(self) -> dict[str, Any]:
        """
        Get information about all public methods (functions) available on this device.
        Returns a dictionary with function names as keys and metadata as values.
        """
        return _build_available_functions(type(self))

    @abstractmethod
    async def _initialize(self, initialization_parameters: dict[str, Any]) -> None:
        """
        Implementation for the initialization of the device.
        """

    @abstractmethod
    async def _cleanup(self) -> None:
        """
        Implementation for the cleanup of the device.
        """

    @abstractmethod
    async def _report(self) -> dict[str, Any]:
        """
        Implementation for the report method.
        """


@functools.cache
def _build_available_functions(cls: type) -> dict[str, Any]:
    """Return metadata for public methods defined on BaseDevice subclasses of cls."""
    exposed_names = {
        name
        for klass in cls.__mro__
        if issubclass(klass, BaseDevice) and klass is not BaseDevice
        for name, val in klass.__dict__.items()
        if not name.startswith("_") and (inspect.isfunction(val) or isinstance(val, (staticmethod, classmethod)))
    }

    functions = {}
    for name in exposed_names:
        method = getattr(cls, name, None)
        if method is None:
            continue
        try:
            sig = inspect.signature(method)
        except (ValueError, TypeError):
            continue

        params = []
        for param_name, param in sig.parameters.items():
            # Skip 'self' parameter and internal Ray parameters
            if param_name == "self" or param_name.startswith("_ray_"):
                continue
            params.append(
                {
                    "name": param_name,
                    "type": _format_annotation(param.annotation, inspect.Parameter.empty),
                    "required": param.default == inspect.Parameter.empty,
                    "default": str(param.default) if param.default != inspect.Parameter.empty else None,
                }
            )

        functions[name] = {
            "name": name,
            "parameters": params,
            "return_type": _format_annotation(sig.return_annotation, inspect.Signature.empty),
            "docstring": inspect.getdoc(method) or "",
            "is_async": inspect.iscoroutinefunction(method),
        }

    return functions


def _format_annotation(annotation: Any, empty_sentinel: Any) -> str:
    if annotation is empty_sentinel:
        return "Any"
    if hasattr(annotation, "__name__"):
        return annotation.__name__
    return str(annotation).replace("typing.", "")
