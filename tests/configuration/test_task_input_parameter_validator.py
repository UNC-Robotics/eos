import pytest
from pydantic import ValidationError

from eos.configuration.entities.task_parameters import TaskParameterType
from eos.configuration.entities.task import TaskConfig
from eos.configuration.entities.task_spec import TaskSpecConfig
from eos.tasks.exceptions import EosTaskValidationError
from eos.tasks.validation.task_input_parameter_validator import TaskInputParameterValidator


class TestTaskInputParameterValidator:
    @pytest.fixture
    def task_spec(self):
        return TaskSpecConfig(
            type="test_task",
            desc="A test task",
            input_parameters={
                "int_param": {"type": "int", "unit": "n/a", "desc": "An integer parameter", "min": 0, "max": 100},
                "float_param": {"type": "float", "unit": "n/a", "desc": "A float parameter", "min": 0.0, "max": 1.0},
                "str_param": {"type": "str", "desc": "A string parameter"},
                "bool_param": {"type": "bool", "value": False, "desc": "A boolean parameter"},
                "list_param": {"type": "list", "desc": "A list parameter", "element_type": "int", "length": 3},
                "choice_param": {
                    "type": "choice",
                    "value": "A",
                    "desc": "A choice parameter",
                    "choices": ["A", "B", "C"],
                },
                "dict_param": {"type": "dict", "desc": "A dictionary parameter"},
            },
        )

    @pytest.fixture
    def task_config(self, task_spec):
        return TaskConfig(
            id="test_task_1",
            type="test_task",
            parameters={
                "int_param": 50,
                "float_param": 0.5,
                "str_param": "test",
                "bool_param": True,
                "list_param": [1, 2, 3],
                "dict_param": {"key": "value"},
                "choice_param": "A",
            },
        )

    @pytest.fixture
    def validator(self, task_config, task_spec):
        return TaskInputParameterValidator(task_config, task_spec)

    def test_valid_input_parameters(self, validator):
        validator.validate()  # Should not raise any exceptions

    @pytest.mark.parametrize(
        ("param_name", "invalid_value"),
        [
            ("int_param", "not_an_int"),
            ("float_param", "not_a_float"),
            ("bool_param", "not_a_bool"),
            ("list_param", "not_a_list"),
            ("dict_param", "not_a_dict"),
            ("choice_param", "D"),
        ],
    )
    def test_invalid_input_parameters(self, validator, task_config, param_name, invalid_value):
        task_config.parameters[param_name] = invalid_value
        with pytest.raises((ValidationError, EosTaskValidationError)):
            validator.validate()

    def test_missing_required_parameter(self, validator, task_config):
        del task_config.parameters["int_param"]
        with pytest.raises((ValidationError, EosTaskValidationError)):
            validator.validate()

    def test_extra_parameter(self, validator, task_config):
        task_config.parameters["extra_param"] = "extra"
        with pytest.raises((ValidationError, EosTaskValidationError)):
            validator.validate()

    @pytest.mark.parametrize(
        ("param_type", "valid_values", "invalid_values"),
        [
            (TaskParameterType.INT, [0, 50, 100, "50"], [-1, 101, "fifty"]),
            (TaskParameterType.FLOAT, [0.0, 0.5, 1.0, "0.5"], [-0.1, 1.1, "half"]),
            (TaskParameterType.BOOL, [True, False, "true", "false"], ["yes", "no", 2]),
            (TaskParameterType.STR, ["test", "123", ""], []),
            (TaskParameterType.LIST, [[1, 2, 3], [1, 2, 62]], [[1, 2], [1, 2, 3, 4], "not_a_list"]),
            (TaskParameterType.DICT, [{"key": "value"}, {}], ["not_a_dict", [1, 2, 3]]),
            (TaskParameterType.CHOICE, ["A", "B", "C"], ["D", 1, True]),
        ],
    )
    def test_parameter_type_conversion(
        self, validator, task_config, task_spec, param_type, valid_values, invalid_values
    ):
        param_name = f"{param_type.value}_param"
        task_spec.input_parameters[param_name].type = param_type.value
        if param_type == TaskParameterType.CHOICE:
            task_spec.input_parameters[param_name].choices = ["A", "B", "C"]
        elif param_type == TaskParameterType.LIST:
            task_spec.input_parameters[param_name].element_type = "int"
            task_spec.input_parameters[param_name].length = 3

        for valid_value in valid_values:
            task_config.parameters[param_name] = valid_value
            validator.validate()  # Should not raise any exceptions

        for invalid_value in invalid_values:
            task_config.parameters[param_name] = invalid_value
            with pytest.raises((ValidationError, EosTaskValidationError)):
                validator.validate()

    @pytest.mark.parametrize(
        ("param_name", "invalid_value", "expected_error"),
        [
            ("int_param", "$.some_reference", (ValidationError, EosTaskValidationError)),
            ("int_param", "eos_dynamic", (ValidationError, EosTaskValidationError)),
            ("int_param", 150, (ValidationError, EosTaskValidationError)),
            ("list_param", [1, 2, 3, 4], (ValidationError, EosTaskValidationError)),
        ],
    )
    def test_specific_validation_cases(self, validator, task_config, param_name, invalid_value, expected_error):
        task_config.parameters[param_name] = invalid_value
        with pytest.raises(expected_error):
            validator.validate()
