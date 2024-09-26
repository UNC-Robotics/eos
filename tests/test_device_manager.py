from eos.devices.entities.device import DeviceStatus
from eos.devices.exceptions import EosDeviceStateError
from tests.fixtures import *

LAB_ID = "small_lab"


@pytest.mark.parametrize("setup_lab_experiment", [(LAB_ID, "water_purification")], indirect=True)
class TestDeviceManager:
    def test_get_device(self, device_manager):
        device = device_manager.get_device(LAB_ID, "substance_fridge")
        assert device.id == "substance_fridge"
        assert device.lab_id == LAB_ID
        assert device.type == "fridge"
        assert device.location == "substance_fridge"

    def test_get_device_nonexistent(self, device_manager):
        device = device_manager.get_device(LAB_ID, "nonexistent_device")
        assert device is None

    def test_get_all_devices(self, device_manager):
        devices = device_manager.get_devices(lab_id=LAB_ID)
        assert len(devices) == 5

    def test_get_devices_by_type(self, device_manager):
        devices = device_manager.get_devices(lab_id=LAB_ID, type="magnetic_mixer")
        assert len(devices) == 2
        assert all(device.type == "magnetic_mixer" for device in devices)

    def test_set_device_status(self, device_manager):
        device_manager.set_device_status(LAB_ID, "evaporator", DeviceStatus.ACTIVE)
        device = device_manager.get_device(LAB_ID, "evaporator")
        assert device.status == DeviceStatus.ACTIVE

    def test_set_device_status_nonexistent(self, device_manager):
        with pytest.raises(EosDeviceStateError):
            device_manager.set_device_status(LAB_ID, "nonexistent_device", DeviceStatus.INACTIVE)