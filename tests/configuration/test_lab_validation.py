from eos.configuration.entities.lab import LabContainerConfig
from eos.configuration.exceptions import EosLabConfigurationError
from eos.configuration.validation.lab_validator import LabValidator
from tests.fixtures import *


@pytest.fixture()
def lab(configuration_manager):
    configuration_manager.load_lab("small_lab")
    return configuration_manager.labs["small_lab"]


class TestLabValidation:
    def test_device_locations(self, configuration_manager, lab):
        lab.devices["magnetic_mixer"].location = "invalid_location"

        with pytest.raises(EosLabConfigurationError):
            LabValidator(configuration_manager._user_dir, lab).validate()

    def test_container_locations(self, configuration_manager, lab):
        lab.containers[0].location = "invalid_location"

        with pytest.raises(EosLabConfigurationError):
            LabValidator(configuration_manager._user_dir, lab).validate()

    def test_device_computers(self, configuration_manager, lab):
        lab.devices["magnetic_mixer"].computer = "invalid_computer"

        with pytest.raises(EosLabConfigurationError):
            LabValidator(configuration_manager._user_dir, lab).validate()

    def test_container_non_unique_type(self, configuration_manager, lab):
        lab.containers.extend(
            [
                LabContainerConfig(
                    type="beaker",
                    location="substance_shelf",
                    ids=["a", "b"],
                ),
                LabContainerConfig(
                    type="beaker",
                    location="substance_shelf",
                    ids=["c", "d"],
                ),
            ]
        )

        with pytest.raises(EosLabConfigurationError):
            LabValidator(configuration_manager._user_dir, lab).validate()

    def test_container_duplicate_ids(self, configuration_manager, lab):
        lab.containers.extend(
            [
                LabContainerConfig(
                    type="beaker",
                    location="substance_shelf",
                    ids=["a", "b"],
                ),
                LabContainerConfig(
                    type="flask",
                    location="substance_shelf",
                    ids=["a", "b"],
                ),
            ]
        )

        with pytest.raises(EosLabConfigurationError):
            LabValidator(configuration_manager._user_dir, lab).validate()
