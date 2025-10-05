import copy

from eos.configuration.exceptions import EosLabConfigurationError
from eos.configuration.validation.validators import MultiLabValidator
from tests.fixtures import *


class TestMultiLabValidation:
    def test_duplicate_resource_names(self, configuration_manager):
        configuration_manager.load_lab("small_lab")
        lab = configuration_manager.labs["small_lab"]

        # Create a deep copy of the lab to simulate two instances
        lab_copy = copy.deepcopy(lab)

        with pytest.raises(EosLabConfigurationError):
            MultiLabValidator([lab, lab_copy]).validate()
