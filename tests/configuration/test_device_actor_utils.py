import pytest
import ray

from eos.devices.device_actor_utils import DeviceActorReference, create_device_actor_dict
from eos.utils.ray_utils import RayActorWrapper


@ray.remote
class DummyDevice:
    def __init__(self, device_name):
        self.device_name = device_name

    def get_name(self):
        return self.device_name


@pytest.fixture
def device_actor_references_dict():
    """Create a dict mapping device names to DeviceActorReference objects."""
    return {
        "mixer": DeviceActorReference("d1", "lab1", "mixer_type", DummyDevice.remote("d1"), {}),
        "heater": DeviceActorReference("d2", "lab1", "heater_type", DummyDevice.remote("d2"), {}),
        "analyzer": DeviceActorReference("d3", "lab2", "analyzer_type", DummyDevice.remote("d3"), {}),
    }


@pytest.fixture
def device_dict(device_actor_references_dict):
    """Create a device dict using create_device_actor_dict."""
    return create_device_actor_dict(device_actor_references_dict)


class TestCreateDeviceActorDict:
    def test_creates_correct_dict_structure(self, device_dict):
        """Test that the function creates a dict with correct keys."""
        assert isinstance(device_dict, dict)
        assert set(device_dict.keys()) == {"mixer", "heater", "analyzer"}

    def test_values_are_ray_actor_wrappers(self, device_dict):
        """Test that all values are RayActorWrapper instances."""
        assert all(isinstance(wrapper, RayActorWrapper) for wrapper in device_dict.values())

    def test_wrappers_reference_correct_actors(self, device_dict):
        """Test that wrappers correctly reference the underlying actors."""
        assert device_dict["mixer"].get_name() == "d1"
        assert device_dict["heater"].get_name() == "d2"
        assert device_dict["analyzer"].get_name() == "d3"

    def test_empty_input(self):
        """Test that empty input produces empty dict."""
        result = create_device_actor_dict({})
        assert result == {}

    def test_single_device(self):
        """Test with a single device."""
        single_ref = {"single": DeviceActorReference("dev1", "lab1", "type1", DummyDevice.remote("dev1"), {})}
        result = create_device_actor_dict(single_ref)
        assert len(result) == 1
        assert "single" in result
        assert isinstance(result["single"], RayActorWrapper)
        assert result["single"].get_name() == "dev1"

    def test_preserves_device_names(self, device_actor_references_dict):
        """Test that device names from the input dict are preserved as keys."""
        result = create_device_actor_dict(device_actor_references_dict)
        # Keys should match the input dict keys, not the actual device names
        assert "mixer" in result
        assert "heater" in result
        assert "analyzer" in result
