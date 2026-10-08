from unittest.mock import Mock, patch

import pytest

from eos.configuration.entities.task_def import TaskDef
from eos.configuration.entities.task_spec_def import TaskSpecDef
from eos.configuration.exceptions import EosTaskValidationError
from eos.configuration.validation import TaskValidator


@pytest.fixture(autouse=True)
def isolated_spec_registry():
    with patch("eos.configuration.validation.TaskSpecRegistry"):
        yield


@pytest.mark.parametrize(
    ("resources", "error"),
    [
        ({"beaker": {"resource_type": "beaker"}}, None),
        ({"beaker": {"resource_type": "beaker"}, "destination": {"resource_type": "slot"}}, None),
        ({"destination": {"resource_type": "slot"}}, "Required resource 'beaker'"),
        ({"beaker": {"resource_type": "beaker"}, "destination": {"resource_type": "beaker"}}, "incorrect type"),
        ({"beaker": {"resource_type": "beaker"}, "unknown": {"resource_type": "slot"}}, "Unexpected resource"),
    ],
)
def test_optional_resources_preserve_required_names_and_types(resources, error):
    spec = TaskSpecDef(
        type="Place",
        input_resources={"beaker": {"type": "beaker"}, "destination": {"type": "slot", "optional": True}},
    )
    task = TaskDef(name="place", type="Place", resources=resources)
    validator = TaskValidator(Mock(), [])

    if error:
        with pytest.raises(EosTaskValidationError, match=error):
            validator._validate_task_resources(task, spec)
    else:
        validator._validate_task_resources(task, spec)


def test_task_can_omit_all_optional_resources():
    spec = TaskSpecDef(type="Place", input_resources={"destination": {"type": "slot", "optional": True}})
    task = TaskDef(name="place", type="Place")

    TaskValidator(Mock(), [])._validate_task_resources(task, spec)
