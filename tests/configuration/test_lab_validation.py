from eos.configuration.entities.lab import LabResourceConfig
from eos.configuration.exceptions import EosLabConfigurationError
from eos.configuration.validation.validators import LabValidator
from tests.fixtures import *


@pytest.fixture()
def lab(configuration_manager):
    configuration_manager.load_lab("small_lab")
    return configuration_manager.labs["small_lab"]


class TestLabValidation:
    def test_device_computers(self, configuration_manager, lab):
        lab.devices["magnetic_mixer"].computer = "invalid_computer"

        with pytest.raises(EosLabConfigurationError):
            LabValidator(
                configuration_manager._user_dir,
                lab,
                configuration_manager.task_specs,
                configuration_manager.device_specs,
            ).validate()

    def test_resources_allow_duplicate_types(self, configuration_manager, lab):
        # Duplicate types are allowed across different resource IDs
        lab.resources = {}
        lab.resources["a"] = LabResourceConfig(type="beaker_500")
        lab.resources["b"] = LabResourceConfig(type="beaker_500")

        # Should not raise error
        LabValidator(
            configuration_manager._user_dir,
            lab,
            configuration_manager.task_specs,
            configuration_manager.device_specs,
        ).validate()

    def test_resource_duplicate_names_within_lab_not_possible(self, configuration_manager, lab):
        # In dict-based resources, duplicate IDs cannot coexist (later assignment overwrites earlier).
        lab.resources = {}
        lab.resources["dup"] = LabResourceConfig(type="beaker")
        lab.resources["dup"] = LabResourceConfig(type="flask")

        # Should not raise due to duplicate IDs within the same lab (dict enforces uniqueness).
        LabValidator(
            configuration_manager._user_dir,
            lab,
            configuration_manager.task_specs,
            configuration_manager.device_specs,
        ).validate()
