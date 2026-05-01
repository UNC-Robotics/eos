import pytest
from pydantic import ValidationError

from eos.configuration.entities.task_parameters import (
    NumericTaskParameter,
    TaskParameterGroup,
)
from eos.configuration.entities.task_spec_def import TaskSpecDef


def _leaf_int(**overrides) -> dict:
    return {"type": "int", "unit": "n/a", "desc": "int leaf", **overrides}


def _leaf_float(**overrides) -> dict:
    return {"type": "float", "unit": "n/a", "desc": "float leaf", **overrides}


class TestTaskParameterGroup:
    def test_group_parsed(self):
        group = TaskParameterGroup(params={"diameter": _leaf_float(value=300.0), "thickness": _leaf_float(value=0.5)})
        assert isinstance(group.params["diameter"], NumericTaskParameter)
        assert group.params["diameter"].value == 300.0

    def test_empty_group_rejected(self):
        with pytest.raises(ValidationError):
            TaskParameterGroup(params={})

    def test_nested_group_rejected(self):
        with pytest.raises(ValidationError, match="Nested"):
            TaskParameterGroup(params={"inner_group": {"x": _leaf_int()}})

    def test_invalid_child_type_propagates(self):
        with pytest.raises(ValidationError):
            TaskParameterGroup(params={"bad": {"type": "not_a_type"}})

    def test_group_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            TaskParameterGroup(params={"x": _leaf_int(value=1)}, desc="not allowed")


class TestTaskSpecDefWithGroups:
    def test_mixed_top_level_and_group(self):
        spec = TaskSpecDef(
            type="t",
            input_parameters={
                "number": _leaf_int(value=1),
                "wafer_parameters": {
                    "diameter": _leaf_float(value=300.0),
                    "thickness": _leaf_float(value=0.5),
                },
            },
        )
        assert isinstance(spec.input_parameters["wafer_parameters"], TaskParameterGroup)
        assert isinstance(spec.input_parameters["number"], NumericTaskParameter)

    def test_iter_parameters_preserves_order(self):
        spec = TaskSpecDef(
            type="t",
            input_parameters={
                "a": _leaf_int(value=1),
                "g": {"x": _leaf_int(value=2), "y": _leaf_int(value=3)},
                "b": _leaf_int(value=4),
            },
        )
        assert [name for name, _ in spec.iter_parameters()] == ["a", "x", "y", "b"]

    def test_get_parameter_across_groups(self):
        spec = TaskSpecDef(
            type="t",
            input_parameters={
                "top": _leaf_int(value=1),
                "g": {"inner": _leaf_int(value=2)},
            },
        )
        assert spec.get_parameter("top").value == 1
        assert spec.get_parameter("inner").value == 2
        assert spec.get_parameter("missing") is None
        # Group names are not leaf names.
        assert spec.get_parameter("g") is None

    def test_duplicate_leaf_across_groups_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate"):
            TaskSpecDef(
                type="t",
                input_parameters={
                    "g1": {"x": _leaf_int(value=1)},
                    "g2": {"x": _leaf_int(value=2)},
                },
            )

    def test_duplicate_leaf_top_level_and_group_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate"):
            TaskSpecDef(
                type="t",
                input_parameters={
                    "x": _leaf_int(value=1),
                    "g": {"x": _leaf_int(value=2)},
                },
            )

    def test_empty_group_rejected_via_spec(self):
        with pytest.raises(ValidationError):
            TaskSpecDef(type="t", input_parameters={"g": {}})

    def test_nested_group_rejected_via_spec(self):
        with pytest.raises(ValidationError, match="Nested"):
            TaskSpecDef(
                type="t",
                input_parameters={"g": {"inner_group": {"x": _leaf_int()}}},
            )

    def test_group_name_allows_internal_spaces(self):
        spec = TaskSpecDef(
            type="t",
            input_parameters={"liquid pumps": {"x": _leaf_int(value=1)}},
        )
        assert "liquid pumps" in spec.input_parameters

    def test_child_name_allows_internal_spaces(self):
        spec = TaskSpecDef(
            type="t",
            input_parameters={"g": {"flow rate": _leaf_int(value=1)}},
        )
        assert "flow rate" in [name for name, _ in spec.iter_parameters()]

    @pytest.mark.parametrize("bad_name", [" leading", "trailing ", "double  space", "has.dot", ""])
    def test_group_name_pattern_rejects_invalid(self, bad_name):
        with pytest.raises(ValidationError):
            TaskSpecDef(
                type="t",
                input_parameters={bad_name: {"x": _leaf_int(value=1)}},
            )

    @pytest.mark.parametrize("bad_name", [" leading", "trailing ", "double  space", "has.dot", ""])
    def test_child_name_pattern_rejects_invalid(self, bad_name):
        with pytest.raises(ValidationError):
            TaskSpecDef(
                type="t",
                input_parameters={"g": {bad_name: _leaf_int(value=1)}},
            )

    def test_ungrouped_only_still_works(self):
        spec = TaskSpecDef(
            type="t",
            input_parameters={"a": _leaf_int(value=1), "b": _leaf_int(value=2)},
        )
        assert [name for name, _ in spec.iter_parameters()] == ["a", "b"]

    def test_group_serializes_with_children_directly(self):
        """Wire shape matches authored YAML: group name -> {child_name: leaf_spec} (no `params:` wrapper)."""
        spec = TaskSpecDef(
            type="t",
            input_parameters={"g": {"x": _leaf_int(value=1), "y": _leaf_int(value=2)}},
        )
        dumped = spec.model_dump(mode="json")
        entry = dumped["input_parameters"]["g"]
        assert "type" not in entry
        assert "params" not in entry
        assert set(entry) == {"x", "y"}
        assert entry["x"]["value"] == 1

    def test_dumped_spec_round_trips(self):
        """model_dump output can be re-validated back into a TaskSpecDef."""
        original = TaskSpecDef(
            type="t",
            input_parameters={
                "top": _leaf_int(value=5),
                "g": {"x": _leaf_int(value=1), "y": _leaf_int(value=2)},
            },
        )
        rebuilt = TaskSpecDef.model_validate(original.model_dump(mode="json"))
        assert [name for name, _ in rebuilt.iter_parameters()] == ["top", "x", "y"]
        assert rebuilt.get_parameter("x").value == 1
