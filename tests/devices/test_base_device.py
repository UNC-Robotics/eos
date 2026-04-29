from typing import Any
from unittest.mock import Mock

import pytest

from eos.devices.base_device import BaseDevice, DeviceStatus
from eos.devices.exceptions import EosDeviceError, EosDeviceCleanupError, EosDeviceInitializationError


class MockDevice(BaseDevice):
    def __init__(self, device_name: str, lab_name: str, device_type: str):
        self.mock_resource = None
        super().__init__(device_name, lab_name, device_type)

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
        assert mock_device.name == "test_device"
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
        assert status_report["name"] == "test_device"
        assert status_report["lab_name"] == "test_lab"
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


class _MixinForTest:
    """Stand-in for an integration mixin (e.g. SilaDeviceMixin); not a BaseDevice subclass."""

    def mixin_public_method(self, value: int = 0) -> int:
        return value

    def _mixin_private(self) -> None:
        pass


class _DeviceBaseForTest(BaseDevice):
    """Intermediate device base class. Its public methods should still be exposed."""

    async def _initialize(self, init_parameters: dict[str, Any]) -> None:
        pass

    async def _cleanup(self) -> None:
        pass

    async def _report(self) -> dict[str, Any]:
        return {}

    def base_public_method(self) -> str:
        return "base"


class _UserDevice(_DeviceBaseForTest, _MixinForTest):
    """Concrete user device combining a BaseDevice subclass with a non-BaseDevice mixin."""

    def user_public_method(self, name: str, count: int = 1) -> bool:
        """User-defined method docstring."""
        return True

    async def user_async_method(self) -> None:
        pass

    def _user_private(self) -> None:
        pass


class TestGetAvailableFunctions:
    @pytest.fixture
    def device(self):
        return _UserDevice("test", "lab", "user")

    def test_includes_user_methods(self, device):
        functions = device.get_available_functions()
        assert "user_public_method" in functions
        assert "user_async_method" in functions

    def test_includes_intermediate_base_methods(self, device):
        functions = device.get_available_functions()
        assert "base_public_method" in functions

    def test_excludes_private_methods(self, device):
        functions = device.get_available_functions()
        for name in ["_user_private", "_mixin_private", "_initialize", "_cleanup", "_report"]:
            assert name not in functions

    def test_excludes_basedevice_methods(self, device):
        functions = device.get_available_functions()
        for name in [
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
            assert name not in functions

    def test_excludes_non_basedevice_mixin_methods(self, device):
        # The whole point: a mixin that isn't a BaseDevice subclass is hidden,
        # without BaseDevice having to know about it.
        assert "mixin_public_method" not in device.get_available_functions()

    def test_metadata_shape(self, device):
        meta = device.get_available_functions()["user_public_method"]
        assert meta["name"] == "user_public_method"
        assert meta["return_type"] == "bool"
        assert meta["is_async"] is False
        assert meta["docstring"] == "User-defined method docstring."

        params = {p["name"]: p for p in meta["parameters"]}
        assert "self" not in params
        assert params["name"]["type"] == "str"
        assert params["name"]["required"] is True
        assert params["count"]["type"] == "int"
        assert params["count"]["required"] is False
        assert params["count"]["default"] == "1"

    def test_async_method_flagged(self, device):
        assert device.get_available_functions()["user_async_method"]["is_async"] is True

    def test_result_is_cached_per_class(self, device):
        a = device.get_available_functions()
        b = _UserDevice("other", "lab", "user").get_available_functions()
        assert a is b
