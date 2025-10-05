from eos.devices.entities.device import DeviceStatus
from eos.devices.exceptions import EosDeviceStateError
from tests.fixtures import *

LAB_NAME = "small_lab"


@pytest.mark.parametrize("setup_lab_experiment", [(LAB_NAME, "water_purification")], indirect=True)
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
