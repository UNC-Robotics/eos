import asyncio
import atexit
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
        device_id: str,
        lab_id: str,
        device_type: str,
    ):
        self._device_id = device_id
        self._lab_id = lab_id
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
                raise EosDeviceInitializationError(f"Device {self._device_id} is already initialized.")

            try:
                await self._initialize(init_parameters)
                self._status = DeviceStatus.IDLE
                self._init_parameters = init_parameters
            except Exception as e:
                self._status = DeviceStatus.ERROR
                raise EosDeviceInitializationError(
                    f"Error initializing device {self._device_id}: {e!s}",
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
                    f"Device {self._device_id} is busy. Cannot perform cleanup.",
                )

            try:
                await self._cleanup()
                self._status = DeviceStatus.DISABLED
            except Exception as e:
                self._status = DeviceStatus.ERROR
                raise EosDeviceCleanupError(f"Error cleaning up device {self._device_id}: {e!s}") from e

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
            "id": self._device_id,
            "status": self._status,
        }

    def get_id(self) -> str:
        return self._device_id

    def get_lab_id(self) -> str:
        return self._lab_id

    def get_device_type(self) -> str:
        return self._device_type

    def get_init_parameters(self) -> dict[str, Any]:
        return self._init_parameters

    @property
    def id(self) -> str:
        return self._device_id

    @property
    def lab_id(self) -> str:
        return self._lab_id

    @property
    def device_type(self) -> str:
        return self._device_type

    @property
    def status(self) -> DeviceStatus:
        return self._status

    @property
    def init_parameters(self) -> dict[str, Any]:
        return self._init_parameters

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
