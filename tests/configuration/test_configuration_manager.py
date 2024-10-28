import copy
import shutil
import tempfile

from eos.configuration.constants import TASK_IMPLEMENTATION_FILE_NAME
from eos.configuration.exceptions import (
    EosMissingConfigurationError,
    EosConfigurationError,
    EosTaskImplementationClassNotFoundError,
)
from tests.fixtures import *

LAB_1_ID = "small_lab"
LAB_2_ID = "multiplication_lab"


class TestConfigurationManager:

    def test_load_lab(self, configuration_manager):
        initial_labs = configuration_manager.labs
        configuration_manager.load_lab(LAB_1_ID)

        assert LAB_1_ID in configuration_manager.labs

        expected_labs = copy.deepcopy(initial_labs)
        expected_labs[LAB_1_ID] = configuration_manager.labs[LAB_1_ID]

        assert configuration_manager.labs == expected_labs

    def test_load_labs(self, configuration_manager):
        initial_labs = configuration_manager.labs
        configuration_manager.load_labs([LAB_1_ID, LAB_2_ID])

        assert LAB_1_ID in configuration_manager.labs
        assert LAB_2_ID in configuration_manager.labs

        expected_labs = copy.deepcopy(initial_labs)
        expected_labs[LAB_1_ID] = configuration_manager.labs[LAB_1_ID]
        expected_labs[LAB_2_ID] = configuration_manager.labs[LAB_2_ID]

        assert configuration_manager.labs == expected_labs

    def test_load_nonexistent_lab(self, configuration_manager):
        initial_labs = configuration_manager.labs
        with pytest.raises(EosMissingConfigurationError):
            configuration_manager.load_lab("nonexistent_lab")

        assert configuration_manager.labs == initial_labs

    def test_unload_lab(self, configuration_manager):
        configuration_manager.load_lab(LAB_1_ID)
        configuration_manager.load_lab(LAB_2_ID)
        configuration_manager.load_experiment("water_purification")

        expected_labs = copy.deepcopy(configuration_manager.labs)
        expected_experiments = copy.deepcopy(configuration_manager.experiments)
        configuration_manager.unload_lab(LAB_1_ID)

        assert LAB_1_ID not in configuration_manager.labs
        assert "water_purification" not in configuration_manager.experiments

        expected_labs.pop(LAB_1_ID)
        assert configuration_manager.labs == expected_labs

        expected_experiments.pop("water_purification")
        assert configuration_manager.experiments == expected_experiments

    def test_unload_nonexistent_lab(self, configuration_manager):
        configuration_manager.load_lab(LAB_1_ID)
        configuration_manager.load_lab(LAB_2_ID)

        with pytest.raises(EosConfigurationError):
            configuration_manager.unload_lab("nonexistent_lab")

    def test_load_experiment(self, configuration_manager):
        configuration_manager.load_lab(LAB_1_ID)

        initial_experiments = configuration_manager.experiments
        configuration_manager.load_experiment("water_purification")
        assert "water_purification" in configuration_manager.experiments

        expected_experiments = copy.deepcopy(initial_experiments)
        expected_experiments["water_purification"] = configuration_manager.experiments["water_purification"]

        assert configuration_manager.experiments == expected_experiments

    def test_load_nonexistent_experiment(self, configuration_manager):
        configuration_manager.load_lab(LAB_1_ID)

        initial_experiments = configuration_manager.experiments
        with pytest.raises(EosMissingConfigurationError):
            configuration_manager.load_experiment("nonexistent_experiment")

        assert configuration_manager.experiments == initial_experiments

    def test_unload_experiment(self, configuration_manager):
        configuration_manager.load_lab(LAB_1_ID)

        if "water_purification" not in configuration_manager.experiments:
            configuration_manager.load_experiment("water_purification")

        expected_experiments = copy.deepcopy(configuration_manager.experiments)
        configuration_manager.unload_experiment("water_purification")

        assert "water_purification" not in configuration_manager.experiments
        expected_experiments.pop("water_purification")
        assert configuration_manager.experiments == expected_experiments

    def test_unload_nonexistent_experiment(self, configuration_manager):
        configuration_manager.load_lab(LAB_1_ID)
        with pytest.raises(EosConfigurationError):
            configuration_manager.unload_experiment("nonexistent_experiment")

    def test_nonexistent_task_implementation_class(self, user_dir):
        with tempfile.TemporaryDirectory(prefix="eos_test-") as temp_user_dir:
            shutil.copytree(user_dir, temp_user_dir, dirs_exist_ok=True)

            temp_tasks_dir_path = Path(temp_user_dir) / "testing" / "tasks"
            (temp_tasks_dir_path / "noop" / TASK_IMPLEMENTATION_FILE_NAME).unlink()

            with pytest.raises(EosTaskImplementationClassNotFoundError):
                ConfigurationManager(user_dir=str(temp_user_dir))
