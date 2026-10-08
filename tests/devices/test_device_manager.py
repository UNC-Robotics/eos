import asyncio
import time

import eos.devices.device_manager as device_manager_module
from eos.devices.device_manager import DeviceManager
from eos.devices.entities.device import DeviceStatus
from eos.devices.exceptions import EosDeviceInitializationError, EosDeviceStateError
from tests.fixtures import *

LAB_NAME = "small_lab"


@pytest.mark.parametrize("setup_lab_protocol", [(LAB_NAME, "water_purification")], indirect=True)
class TestDeviceManager:
    @pytest.mark.asyncio
    async def test_get_device(self, db, device_manager):
        device = await device_manager.get_device(db, LAB_NAME, "substance_fridge")
        assert device.type == "fridge"
        assert device.lab_name == LAB_NAME
        assert device.name == "substance_fridge"

    @pytest.mark.asyncio
    async def test_get_device_nonexistent(self, db, device_manager):
        device = await device_manager.get_device(db, LAB_NAME, "nonexistent_device")
        assert device is None

    @pytest.mark.asyncio
    async def test_get_all_devices(self, db, device_manager):
        devices = await device_manager.get_devices(db, lab_name=LAB_NAME)
        assert len(devices) == 5

    @pytest.mark.asyncio
    async def test_get_devices_by_type(self, db, device_manager):
        devices = await device_manager.get_devices(db, lab_name=LAB_NAME, type="magnetic_mixer")
        assert len(devices) == 2
        assert all(device.type == "magnetic_mixer" for device in devices)

    @pytest.mark.asyncio
    async def test_set_device_status(self, db, device_manager):
        await device_manager.set_device_status(db, LAB_NAME, "evaporator", DeviceStatus.ACTIVE)
        device = await device_manager.get_device(db, LAB_NAME, "evaporator")
        assert device.status == DeviceStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_set_device_status_nonexistent(self, db, device_manager):
        with pytest.raises(EosDeviceStateError):
            await device_manager.set_device_status(db, LAB_NAME, "nonexistent_device", DeviceStatus.INACTIVE)


class _LoopMonitor:
    """Records the longest stall of the event loop while active."""

    def __init__(self, interval: float = 0.01):
        self.interval = interval
        self.max_gap = 0.0

    async def __aenter__(self) -> "_LoopMonitor":
        self._task = asyncio.create_task(self._run())
        return self

    async def __aexit__(self, *exc) -> None:
        self._task.cancel()

    async def _run(self) -> None:
        last = time.monotonic()
        while True:
            await asyncio.sleep(self.interval)
            now = time.monotonic()
            self.max_gap = max(self.max_gap, now - last)
            last = now


class TestDeviceManagerNonBlocking:
    @staticmethod
    async def _start_slow_actor(configuration_manager, device_manager, name: str, cleanup_delay: float):
        device_class = ray.remote(configuration_manager.devices.get_plugin_class_type("slow_device"))
        handle = device_class.options(name=name, num_cpus=0).remote(name, "slow_lab")
        await handle.initialize.remote({"cleanup_delay": cleanup_delay})
        device_manager._device_actor_handles[name] = handle
        device_manager._device_actor_computer_ips[name] = "127.0.0.1"
        return handle

    @staticmethod
    async def _wait_until_killed(name: str) -> None:
        for _ in range(100):
            try:
                ray.get_actor(name)
            except ValueError:
                return
            await asyncio.sleep(0.05)
        pytest.fail(f"Actor '{name}' was not killed")

    @pytest.mark.asyncio
    async def test_cleanup_timeout_does_not_block_event_loop(self, configuration_manager):
        device_manager = DeviceManager(configuration_manager=configuration_manager)
        await self._start_slow_actor(configuration_manager, device_manager, "slow_lab.cleanup", cleanup_delay=30)

        start = time.monotonic()
        async with _LoopMonitor() as monitor:
            await device_manager._cleanup_device_actors_with_timeout(["slow_lab.cleanup"], cleanup_timeout=1)

        assert 1 <= time.monotonic() - start < 5
        assert monitor.max_gap < 0.5
        assert "slow_lab.cleanup" not in device_manager._device_actor_handles
        await self._wait_until_killed("slow_lab.cleanup")

    @pytest.mark.asyncio
    async def test_health_check_only_covers_given_actors(self, configuration_manager, monkeypatch):
        monkeypatch.setattr(device_manager_module, "HEALTH_CHECK_TIMEOUT", 0.5)
        device_manager = DeviceManager(configuration_manager=configuration_manager)
        busy = await self._start_slow_actor(configuration_manager, device_manager, "slow_lab.busy", cleanup_delay=30)
        busy.cleanup.remote()  # Keeps the actor busy so it cannot answer status checks

        # Unrelated busy actors are not checked
        start = time.monotonic()
        await device_manager._raise_on_errors([])
        assert time.monotonic() - start < 0.2
        assert "slow_lab.busy" in device_manager._device_actor_handles

        async with _LoopMonitor() as monitor:
            with pytest.raises(EosDeviceInitializationError, match="slow_lab.busy"):
                await device_manager._raise_on_errors(["slow_lab.busy"])
        assert monitor.max_gap < 0.3
        assert "slow_lab.busy" not in device_manager._device_actor_handles
        await self._wait_until_killed("slow_lab.busy")

    @pytest.mark.asyncio
    async def test_recover_unresponsive_actor_does_not_block(self, configuration_manager, monkeypatch):
        monkeypatch.setattr(device_manager_module, "HEALTH_CHECK_TIMEOUT", 0.5)
        device_manager = DeviceManager(configuration_manager=configuration_manager)
        busy = await self._start_slow_actor(configuration_manager, device_manager, "slow_lab.stale", cleanup_delay=30)
        busy.cleanup.remote()
        device_manager._device_actor_handles.clear()

        async with _LoopMonitor() as monitor:
            recovered = await device_manager._try_recover_actor("slow_lab.stale", "127.0.0.1")
        assert not recovered
        assert monitor.max_gap < 0.3
        await self._wait_until_killed("slow_lab.stale")
