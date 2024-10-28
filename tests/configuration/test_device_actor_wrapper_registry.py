import pytest
import ray

from eos.devices.device_actor_wrapper_registry import DeviceActorWrapperRegistry, DeviceActorReference
from eos.utils.ray_utils import RayActorWrapper


@ray.remote
class DummyDevice:
    def __init__(self, device_id):
        self.device_id = device_id

    def get_id(self):
        return self.device_id


@pytest.fixture
def device_actor_references():
    return [
        DeviceActorReference("d1", "lab1", "type1", DummyDevice.remote("d1")),
        DeviceActorReference("d2", "lab1", "type2", DummyDevice.remote("d2")),
        DeviceActorReference("d3", "lab2", "type1", DummyDevice.remote("d3")),
        DeviceActorReference("d4", "lab2", "type2", DummyDevice.remote("d4")),
    ]


@pytest.fixture
def device_actor_wrapper_references(device_actor_references):
    return DeviceActorWrapperRegistry(device_actor_references)


class TestDeviceActorWrapperRegistry:
    def test_get_existing_device(self, device_actor_wrapper_references):
        device = device_actor_wrapper_references.get("lab1", "d1")
        assert isinstance(device, RayActorWrapper)
        assert device.get_id() == "d1"

    def test_get_nonexistent_device(self, device_actor_wrapper_references):
        device = device_actor_wrapper_references.get("lab1", "nonexistent")
        assert device is None

    def test_get_all_by_lab_id(self, device_actor_wrapper_references):
        devices = device_actor_wrapper_references.get_all_by_lab_id("lab1")
        assert len(devices) == 2
        assert all(isinstance(device, RayActorWrapper) for device in devices)
        device_ids = [device.get_id() for device in devices]
        assert set(device_ids) == {"d1", "d2"}

    def test_get_all_by_nonexistent_lab_id(self, device_actor_wrapper_references):
        devices = device_actor_wrapper_references.get_all_by_lab_id("nonexistent")
        assert len(devices) == 0

    def test_get_all_by_type(self, device_actor_wrapper_references):
        devices = device_actor_wrapper_references.get_all_by_type("type1")
        assert len(devices) == 2
        assert all(isinstance(device, RayActorWrapper) for device in devices)
        device_ids = [device.get_id() for device in devices]
        assert set(device_ids) == {"d1", "d3"}

    def test_get_all_by_nonexistent_type(self, device_actor_wrapper_references):
        devices = device_actor_wrapper_references.get_all_by_type("nonexistent")
        assert len(devices) == 0

    def test_device_uniqueness(self, device_actor_wrapper_references):
        lab1_devices = device_actor_wrapper_references.get_all_by_lab_id("lab1")
        lab2_devices = device_actor_wrapper_references.get_all_by_lab_id("lab2")
        all_devices = lab1_devices + lab2_devices
        unique_devices = {device.actor for device in all_devices}
        assert len(all_devices) == len(unique_devices)
