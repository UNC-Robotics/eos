from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, field_validator, model_validator, Field
from typing_extensions import Self

from eos.configuration.validation.validation_utils import is_dynamic_parameter


class TaskParameterType(str, Enum):
    """Enumeration of supported parameter types."""

    INT = "int"
    FLOAT = "float"
    STR = "str"
    BOOL = "bool"
    CHOICE = "choice"
    LIST = "list"
    DICT = "dict"

    @property
    def python_type(self) -> type:
        """Returns the corresponding Python type for the parameter type."""
        return {
            self.INT: int,
            self.FLOAT: float,
            self.STR: str,
            self.BOOL: bool,
            self.CHOICE: str,
            self.LIST: list,
            self.DICT: dict,
        }[self]

    @property
    def is_numeric(self) -> bool:
        return self in (self.INT, self.FLOAT)


class TaskParameter(BaseModel):
    """Base class for all task parameters."""

    type: TaskParameterType
    desc: str | None = None
    value: Any | None = None

    class Config:
        extra = "forbid"

    @model_validator(mode="after")
    def _validate_type(self) -> Self:
        if self.value is not None and not is_dynamic_parameter(self.value):
            expected_type = self.type.python_type
            if not isinstance(self.value, expected_type):
                raise ValueError(
                    f"Task parameter value '{self.value}' has type '{type(self.value).__name__}' "
                    f"but declared parameter type is '{self.type}'."
                )
        return self


class NumericTaskParameter(TaskParameter):
    """Parameter type for numeric values (int or float)."""

    unit: str
    min: int | float | None = None
    max: int | float | None = None

    @field_validator("unit")
    def validate_unit(cls, unit: str) -> str:
        if not unit.strip():
            raise ValueError("Task numeric parameter requires a unit to be specified.")
        return unit.strip()

    @model_validator(mode="after")
    def _validate_bounds(self) -> Self:
        if self.min is not None and self.max is not None and self.min >= self.max:
            raise ValueError("Task parameter 'min' is greater than or equal to 'max'.")

        if self.value is not None and not is_dynamic_parameter(self.value):
            if not isinstance(self.value, int | float):
                raise ValueError("Task parameter value is not numerical.")

            if self.min is not None and self.value < self.min:
                raise ValueError("Task parameter value is less than 'min'.")
            if self.max is not None and self.value > self.max:
                raise ValueError("Task parameter value is greater than 'max'.")

        return self


class StringTaskParameter(TaskParameter):
    """Parameter type for string values."""

    @field_validator("value")
    def _validate_string(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip() and not is_dynamic_parameter(value):
            raise ValueError("Task parameter value cannot be empty or consist only of whitespace.")
        return value


class BooleanTaskParameter(TaskParameter):
    """Parameter type for boolean values."""

    @field_validator("value")
    def _validate_boolean(cls, value: Any) -> Any:
        if not isinstance(value, bool) and not is_dynamic_parameter(value):
            raise ValueError(
                f"Task parameter value '{value}' is declared as 'boolean' but its value is not true/false."
            )
        return value


class ChoiceTaskParameter(TaskParameter):
    """Parameter type for list values."""

    choices: list[str] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_choice(self) -> Self:
        if not self.value or (self.value not in self.choices and not is_dynamic_parameter(self.value)):
            raise ValueError(f"Task parameter value '{self.value}' is not one of the choices {self.choices}.")
        return self


class ListTaskParameter(TaskParameter):
    """Parameter type for list values."""

    element_type: TaskParameterType
    length: int | None = None
    min: list[int | float] | None = None
    max: list[int | float] | None = None

    @field_validator("element_type")
    def _validate_element_type(cls, element_type: str | TaskParameterType) -> TaskParameterType:
        if isinstance(element_type, str):
            try:
                element_type = TaskParameterType(element_type)
            except ValueError as e:
                raise ValueError(f"Invalid list parameter element type '{element_type}'") from e

        if element_type == TaskParameterType.LIST:
            raise ValueError("Nested lists are not supported. List parameter element type cannot be 'list'.")

        return element_type

    def _check_lengths_match(self, label: str, lst: list[Any] | None) -> None:
        if self.length is not None and lst is not None and len(lst) != self.length:
            raise ValueError(f"List parameter '{label}' length must be {self.length}.")

    def _check_element_types(self, label: str, lst: list[Any] | None) -> None:
        if lst is not None and not all(isinstance(item, self.element_type.python_type) for item in lst):
            raise ValueError(
                f"All elements of list parameter '{label}' must be of "
                f"type {self.element_type.python_type.__name__}."
            )

    def _check_within_bounds(self) -> None:
        if self.value is None or is_dynamic_parameter(self.value):
            return

        if self.length is None and (self.min or self.max):
            raise ValueError("List parameter 'min' and 'max' can only be specified when 'length' is set.")

        if self.length is None:
            return

        bounds_min = (self.min or []) + [float("-inf")] * (self.length or 0)
        bounds_max = (self.max or []) + [float("inf")] * (self.length or 0)

        for idx, val in enumerate(self.value):
            if not bounds_min[idx] <= val <= bounds_max[idx]:
                raise ValueError(
                    f"Element {idx} of the list with value {val} is not within "
                    f"the bounds [{bounds_min[idx]}, {bounds_max[idx]}]."
                )

    @model_validator(mode="after")
    def _validate_list(self) -> Self:
        if is_dynamic_parameter(self.value):
            return self

        for label in ("value", "min", "max"):
            attr_value = getattr(self, label)
            if attr_value is not None and not isinstance(attr_value, list):
                raise ValueError(f"List parameter '{label}' must be a list for 'list' type parameters.")

        for label in ("min", "max", "value"):
            self._check_lengths_match(label, getattr(self, label))
            self._check_element_types(label, getattr(self, label))

        self._check_within_bounds()

        return self


class DictionaryTaskParameter(TaskParameter):
    pass


class TaskParameterFactory:
    _PARAMETER_CLASSES: ClassVar = {
        TaskParameterType.INT: NumericTaskParameter,
        TaskParameterType.FLOAT: NumericTaskParameter,
        TaskParameterType.STR: StringTaskParameter,
        TaskParameterType.BOOL: BooleanTaskParameter,
        TaskParameterType.CHOICE: ChoiceTaskParameter,
        TaskParameterType.LIST: ListTaskParameter,
        TaskParameterType.DICT: DictionaryTaskParameter,
    }

    @classmethod
    def create(cls, parameter_type: TaskParameterType | str, **kwargs) -> TaskParameter:
        """Create a task parameter instance of the specified type."""
        if isinstance(parameter_type, str):
            parameter_type = TaskParameterType(parameter_type)

        parameter_class = cls._PARAMETER_CLASSES.get(parameter_type)
        if not parameter_class:
            raise ValueError(f"Unsupported parameter type: {parameter_type}")

        kwargs.setdefault("type", parameter_type)

        return parameter_class(**kwargs)
