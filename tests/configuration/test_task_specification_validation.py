from pydantic import ValidationError

from eos.configuration.entities.task_parameters import (
    TaskParameterFactory,
    TaskParameterType,
)
from eos.configuration.entities.task_spec import (
    TaskSpecOutputParameterConfig,
    TaskSpecConfig,
)
from tests.fixtures import *


class TestTaskSpecifications:
    def test_invalid_parameter_type(self):
        with pytest.raises(ValueError):
            TaskParameterFactory.create(
                "invalid_type",
                value=120,
                desc="Duration of evaporation in seconds.",
            )

    def test_numeric_parameter_unit_not_specified(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.INT,
                unit="",
                value=120,
                min=60,
                desc="Duration of evaporation in seconds.",
            )

    def test_numeric_parameter_value_not_numeric(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.INT,
                unit="sec",
                value="not_a_number",
                min=60,
                desc="Duration of evaporation in seconds.",
            )

    def test_numeric_parameter_min_greater_than_max(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.INT,
                unit="sec",
                value=120,
                min=300,
                max=60,
                desc="Duration of evaporation in seconds.",
            )

    def test_numeric_parameter_out_of_range_min(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.INT,
                unit="sec",
                value=5,
                min=60,
                max=300,
                desc="Duration of evaporation in seconds.",
            )

    def test_numeric_parameter_out_of_range_max(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.INT,
                unit="sec",
                value=100,
                min=0,
                max=80,
                desc="Duration of evaporation in seconds.",
            )

    def test_boolean_parameter_invalid_value(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.BOOL,
                value="not_a_boolean",
                desc="Whether to sparge the evaporation vessel with nitrogen.",
            )

    def test_choice_parameter_choices_not_specified(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.CHOICE,
                choices=[],
                value="method1",
                desc="Method to use",
            )

    def test_choice_parameter_no_value(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.CHOICE,
                choices=["method1", "method2"],
                value=None,
                desc="Method to use",
            )

    def test_choice_parameter_invalid_value(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.CHOICE,
                choices=["method1", "method2"],
                value="invalid_method",
                desc="Method to use",
            )

    def test_list_parameter_invalid_element_type(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.LIST,
                length=3,
                element_type="invalid_type",
                value=[1, 2, 3],
                desc="List of elements",
            )

    def test_list_parameter_nested_list(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.LIST,
                length=3,
                element_type="list",
                value=[[1], [2], [3]],
                desc="List of elements",
            )

    def test_list_parameter_invalid_value(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.LIST,
                length=3,
                element_type="int",
                value=4,
                desc="List of elements",
            )

    def test_list_parameter_elements_not_same_type(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.LIST,
                length=3,
                element_type="int",
                value=[1, True, "3"],
                desc="List of elements",
            )

    def test_list_parameter_invalid_value_element_size(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.LIST,
                length=3,
                element_type="int",
                value=[1, 2],
                desc="List of elements",
            )

    def test_list_parameter_invalid_value_element_min(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.LIST,
                length=3,
                element_type="int",
                value=[1, 2, 3],
                min=[2, 2, "INVALID"],
                desc="List of elements",
            )

    def test_list_parameter_invalid_value_element_max(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.LIST,
                length=3,
                element_type="int",
                value=[1, 2, 3],
                max=[2, 2, "INVALID"],
                desc="List of elements",
            )

    def test_list_parameter_value_less_than_min(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.LIST,
                length=3,
                element_type="int",
                value=[2, 2, 2],
                min=[2, 2, 3],
                desc="List of elements",
            )

    def test_list_parameter_value_greater_than_max(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.LIST,
                length=3,
                element_type="int",
                value=[2, 2, 2],
                max=[2, 2, 1],
                desc="List of elements",
            )

    def test_list_parameter_invalid_min_max_size(self):
        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.LIST,
                length=3,
                element_type="int",
                value=[2, 2, 2],
                min=[2, 2],
                desc="List of elements",
            )

        with pytest.raises(ValidationError):
            TaskParameterFactory.create(
                TaskParameterType.LIST,
                length=3,
                element_type="int",
                value=[2, 2, 2],
                max=[2, 2],
                desc="List of elements",
            )

    def test_parameter_factory_invalid_type(self):
        with pytest.raises(ValueError):
            TaskParameterFactory.create(
                "invalid_type",
                value=120,
                desc="Duration of evaporation in seconds.",
            )

    def test_parameter_invalid_name(self, configuration_manager):
        task_specs = configuration_manager.task_specs

        task_spec = task_specs.get_spec_by_type("Magnetic Mixing")

        task_spec.input_parameters["invalid_name*"] = {
            "type": "int",
            "unit": "sec",
            "value": 120,
            "desc": "Duration of evaporation in seconds.",
        }

        with pytest.raises(ValidationError):
            TaskSpecConfig(**task_spec.model_dump())

        del task_spec.input_parameters["invalid_name*"]

    def test_output_numeric_parameter_unit_not_specified(self, configuration_manager):
        with pytest.raises(ValidationError):
            TaskSpecOutputParameterConfig(
                type=TaskParameterType.INT,
                unit="",
                desc="Duration of evaporation in seconds.",
            )

    def test_output_non_numeric_parameter_unit_specified(self, configuration_manager):
        with pytest.raises(ValidationError):
            TaskSpecOutputParameterConfig(
                type=TaskParameterType.BOOL,
                unit="sec",
                desc="Whether to sparge the evaporation vessel with nitrogen.",
            )
