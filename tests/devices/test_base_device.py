from typing import Any
from unittest.mock import Mock

import pytest

from eos.devices.base_device import BaseDevice, DeviceStatus
from eos.devices.exceptions import EosDeviceError, EosDeviceCleanupError, EosDeviceInitializationError


class MockDevice(BaseDevice):
    def __init__(self, device_id: str, lab_id: str, device_type: str):
        self.mock_resource = None
        super().__init__(device_id, lab_id, device_type)

    async def _initialize(self, init_parameters: dict[str, Any]) -> None:
        self.mock_resource = Mock()

    async def _cleanup(self) -> None:
        if self.mock_resource:
            self.mock_resource.close()
            self.mock_resource = None

    async def _report(self) -> dict[str, Any]:
        return {"mock_resource": str(self.mock_resource)}

    def raise_exception(self):
        raise EosDeviceError("Test exception")


class TestBaseDevice:
    @pytest.fixture
    async def mock_device(self):
        mock_device = MockDevice("test_device", "test_lab", "mock")
        await mock_device.initialize({})
        return mock_device

    def test_initialize(self, mock_device):
        assert mock_device.id == "test_device"
        assert mock_device.device_type == "mock"
        assert mock_device.status == DeviceStatus.IDLE
        assert mock_device.mock_resource is not None

    @pytest.mark.asyncio
    async def test_cleanup(self, mock_device):
        await mock_device.cleanup()
        assert mock_device.status == DeviceStatus.DISABLED
        assert mock_device.mock_resource is None

    @pytest.mark.asyncio
    async def test_enable_disable(self, mock_device):
        await mock_device.disable()
        assert mock_device.status == DeviceStatus.DISABLED
        await mock_device.enable()
        assert mock_device.status == DeviceStatus.IDLE

    @pytest.mark.asyncio
    async def test_report(self, mock_device):
        report = await mock_device.report()
        assert "mock_resource" in report

    def test_get_status(self, mock_device):
        status_report = mock_device.get_status()
        assert status_report["id"] == "test_device"
        assert status_report["status"] == DeviceStatus.IDLE

    def test_exception_handling(self, mock_device):
        with pytest.raises(EosDeviceError):
            mock_device.raise_exception()

    @pytest.mark.asyncio
    async def test_initialization_error(self):
        class FailingDevice(MockDevice):
            async def _initialize(self, init_parameters: dict[str, Any]) -> None:
                raise ValueError("Initialization failed")

        device = FailingDevice("fail_device", "test_lab", "failing")
        with pytest.raises(EosDeviceInitializationError):
            await device.initialize({})

    @pytest.mark.asyncio
    async def test_cleanup_error(self, mock_device):
        mock_device.mock_resource.close.side_effect = Exception("Cleanup failed")
        with pytest.raises(EosDeviceError):
            await mock_device.cleanup()
        mock_device.mock_resource.close.side_effect = None
        assert mock_device.status == DeviceStatus.ERROR

    @pytest.mark.asyncio
    async def test_busy_status_cleanup(self, mock_device):
        mock_device._status = DeviceStatus.BUSY
        with pytest.raises(EosDeviceCleanupError):
            await mock_device.cleanup()
        assert mock_device.status == DeviceStatus.BUSY
        mock_device._status = DeviceStatus.IDLE

    @pytest.mark.asyncio
    async def test_double_initialization(self, mock_device):
        with pytest.raises(EosDeviceInitializationError):
            await mock_device.initialize({})
        assert mock_device.status == DeviceStatus.IDLE
