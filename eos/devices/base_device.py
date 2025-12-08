import asyncio
import atexit
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
        functions = {}

        # Get all members of the class
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            # Skip private methods (starting with _) and inherited base methods
            if name.startswith("_"):
                continue

            # Skip BaseDevice methods that are not device-specific
            if name in [
                "initialize",
                "cleanup",
                "report",
                "enable",
                "disable",
                "get_status",
                "get_name",
                "get_lab_name",
                "get_device_type",
                "get_init_parameters",
                "get_available_functions",
            ]:
                continue

            try:
                sig = inspect.signature(method)
                params = []

                for param_name, param in sig.parameters.items():
                    # Skip 'self' parameter and internal Ray parameters
                    if param_name == "self" or param_name.startswith("_ray_"):
                        continue

                    # Format type annotation nicely
                    type_str = "Any"
                    if param.annotation != inspect.Parameter.empty:
                        type_obj = param.annotation
                        if hasattr(type_obj, "__name__"):
                            type_str = type_obj.__name__
                        else:
                            type_str = str(type_obj).replace("typing.", "")

                    param_info = {
                        "name": param_name,
                        "type": type_str,
                        "required": param.default == inspect.Parameter.empty,
                        "default": str(param.default) if param.default != inspect.Parameter.empty else None,
                    }
                    params.append(param_info)

                # Format return type annotation nicely
                return_type_str = "Any"
                if sig.return_annotation != inspect.Signature.empty:
                    return_obj = sig.return_annotation
                    if hasattr(return_obj, "__name__"):
                        return_type_str = return_obj.__name__
                    else:
                        return_type_str = str(return_obj).replace("typing.", "")

                functions[name] = {
                    "name": name,
                    "parameters": params,
                    "return_type": return_type_str,
                    "docstring": inspect.getdoc(method) or "",
                    "is_async": inspect.iscoroutinefunction(method),
                }
            except Exception:  # noqa: S112
                # If we can't inspect the method for any reason, skip it
                continue

        return functions

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
