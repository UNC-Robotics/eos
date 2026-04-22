from unittest.mock import AsyncMock, MagicMock

import pytest

from eos.configuration.entities.task_def import TaskDef
from eos.configuration.entities.task_spec_def import TaskSpecDef
from eos.configuration.registries import TaskSpecRegistry
from eos.protocols.entities.protocol_run import ProtocolRun, ProtocolRunStatus
from eos.tasks.exceptions import EosTaskInputResolutionError
from eos.tasks.task_input_resolver import TaskInputResolver
from eos.utils.singleton import Singleton


TASK_TYPE = "test_task"
PROTOCOL_RUN_NAME = "test_run"
TASK_NAME = "test_task_1"

INT_SPEC = {"type": "int", "unit": "C", "value": 25}
FLOAT_SPEC = {"type": "float", "unit": "mL", "value": 1.5}
STR_SPEC = {"type": "str", "value": "hello"}
BOOL_SPEC = {"type": "bool", "value": True}
LIST_SPEC = {"type": "list", "element_type": "int", "length": 3, "value": [1, 2, 3]}
DICT_SPEC = {"type": "dict", "value": {"k": "v"}}
CHOICE_SPEC = {"type": "choice", "choices": ["A", "B", "C"], "value": "B"}

# (spec, task.yml default)
TYPE_SPECS = [
    ("int", INT_SPEC, 25),
    ("float", FLOAT_SPEC, 1.5),
    ("str", STR_SPEC, "hello"),
    ("bool", BOOL_SPEC, True),
    ("list", LIST_SPEC, [1, 2, 3]),
    ("dict", DICT_SPEC, {"k": "v"}),
    ("choice", CHOICE_SPEC, "B"),
]

NO_DEFAULT_SPECS = [
    {"type": "int", "unit": "C"},
    {"type": "float", "unit": "mL"},
    {"type": "str"},
    {"type": "bool"},
    {"type": "list", "element_type": "int", "length": 3},
    {"type": "dict"},
]


def _build_task_spec(input_parameters: dict) -> TaskSpecDef:
    return TaskSpecDef(type=TASK_TYPE, desc="A test task", input_parameters=input_parameters)


def _build_task(parameters: dict | None = None) -> TaskDef:
    return TaskDef(name=TASK_NAME, type=TASK_TYPE, parameters=parameters or {})


def _build_protocol_run(task_submission_params: dict[str, dict] | None = None) -> ProtocolRun:
    return ProtocolRun(
        name=PROTOCOL_RUN_NAME,
        type="test_protocol",
        owner="test",
        status=ProtocolRunStatus.CREATED,
        parameters=task_submission_params or {},
    )


@pytest.fixture
def reset_task_spec_registry():
    Singleton._instances.pop(TaskSpecRegistry, None)
    yield
    Singleton._instances.pop(TaskSpecRegistry, None)


async def _resolve(task_spec: TaskSpecDef, task: TaskDef, protocol_run: ProtocolRun) -> TaskDef:
    TaskSpecRegistry({TASK_TYPE: task_spec}, {})

    protocol_run_manager = MagicMock()
    protocol_run_manager.get_protocol_run = AsyncMock(return_value=protocol_run)
    resolver = TaskInputResolver(task_manager=MagicMock(), protocol_run_manager=protocol_run_manager)

    return await resolver.resolve_parameters(db=None, protocol_run_name=PROTOCOL_RUN_NAME, task=task)


@pytest.mark.asyncio
class TestTaskInputResolverDefaults:
    @pytest.mark.parametrize(("type_name", "param_spec", "default_value"), TYPE_SPECS)
    async def test_task_default_fills_when_protocol_and_submission_omit_param(
        self, reset_task_spec_registry, type_name, param_spec, default_value
    ):
        spec = _build_task_spec({"p": param_spec})
        resolved = await _resolve(spec, _build_task(), _build_protocol_run())
        assert resolved.parameters == {"p": default_value}

    @pytest.mark.parametrize("param_spec", NO_DEFAULT_SPECS)
    async def test_no_default_and_no_value_leaves_param_absent(self, reset_task_spec_registry, param_spec):
        spec = _build_task_spec({"p": param_spec})
        resolved = await _resolve(spec, _build_task(), _build_protocol_run())
        assert "p" not in resolved.parameters

    # Falsy defaults must still be applied (guards against `if not spec.value`).
    @pytest.mark.parametrize(
        ("param_spec", "expected"),
        [
            ({"type": "int", "unit": "n/a", "value": 0}, 0),
            ({"type": "float", "unit": "n/a", "value": 0.0}, 0.0),
            ({"type": "bool", "value": False}, False),
            ({"type": "list", "element_type": "int", "length": 0, "value": []}, []),
            ({"type": "dict", "value": {}}, {}),
        ],
    )
    async def test_falsy_defaults_are_applied(self, reset_task_spec_registry, param_spec, expected):
        spec = _build_task_spec({"p": param_spec})
        resolved = await _resolve(spec, _build_task(), _build_protocol_run())
        assert resolved.parameters == {"p": expected}

    # eos_dynamic requires a submission value — task.yml default must not substitute.
    @pytest.mark.parametrize(("type_name", "param_spec", "_default"), TYPE_SPECS)
    async def test_eos_dynamic_in_protocol_does_not_fall_back_to_task_default(
        self, reset_task_spec_registry, type_name, param_spec, _default
    ):
        spec = _build_task_spec({"p": param_spec})
        task = _build_task({"p": "eos_dynamic"})
        with pytest.raises(EosTaskInputResolutionError):
            await _resolve(spec, task, _build_protocol_run())

    async def test_eos_dynamic_resolved_when_submission_provides_value(self, reset_task_spec_registry):
        spec = _build_task_spec({"p": INT_SPEC})
        task = _build_task({"p": "eos_dynamic"})
        protocol_run = _build_protocol_run({TASK_NAME: {"p": 80}})
        resolved = await _resolve(spec, task, protocol_run)
        assert resolved.parameters == {"p": 80}

    async def test_eos_dynamic_without_task_default_raises_when_unprovided(self, reset_task_spec_registry):
        spec = _build_task_spec({"p": {"type": "int", "unit": "C"}})
        task = _build_task({"p": "eos_dynamic"})
        with pytest.raises(EosTaskInputResolutionError):
            await _resolve(spec, task, _build_protocol_run())

    async def test_task_default_that_looks_like_a_reference_is_applied_as_is(self, reset_task_spec_registry):
        spec = _build_task_spec({"p": {"type": "str", "value": "prev_task.output_temp"}})
        resolved = await _resolve(spec, _build_task(), _build_protocol_run())
        assert resolved.parameters == {"p": "prev_task.output_temp"}

    # Integration: covers protocol-overrides-default, submission-overrides-protocol, and default fill-in together.
    async def test_multiple_parameters_of_mixed_types_resolve_together(self, reset_task_spec_registry):
        spec = _build_task_spec(
            {
                "temperature": INT_SPEC,
                "volume": FLOAT_SPEC,
                "label": STR_SPEC,
                "enabled": BOOL_SPEC,
                "mode": CHOICE_SPEC,
                "tags": LIST_SPEC,
                "meta": DICT_SPEC,
            }
        )
        task = _build_task({"volume": 2.5, "label": "from_protocol"})
        protocol_run = _build_protocol_run({TASK_NAME: {"label": "from_submission", "enabled": False}})
        resolved = await _resolve(spec, task, protocol_run)

        assert resolved.parameters == {
            "temperature": 25,
            "volume": 2.5,
            "label": "from_submission",
            "enabled": False,
            "mode": "B",
            "tags": [1, 2, 3],
            "meta": {"k": "v"},
        }

    async def test_unknown_task_type_skips_default_fill(self, reset_task_spec_registry):
        spec = _build_task_spec({"p": INT_SPEC})
        task = TaskDef(name=TASK_NAME, type="unregistered_type", parameters={})
        resolved = await _resolve(spec, task, _build_protocol_run())
        assert resolved.parameters == {}


@pytest.mark.asyncio
class TestTaskInputResolverWithGroups:
    """Resolver flattens groups: defaults and overrides apply to grouped leaves by leaf name."""

    async def test_defaults_fill_grouped_leaf(self, reset_task_spec_registry):
        spec = _build_task_spec(
            {
                "top": INT_SPEC,
                "wafer_parameters": {
                    "diameter": FLOAT_SPEC,
                    "thickness": {"type": "float", "unit": "mm", "value": 0.5},
                },
            }
        )
        resolved = await _resolve(spec, _build_task(), _build_protocol_run())
        assert resolved.parameters == {"top": 25, "diameter": 1.5, "thickness": 0.5}

    async def test_protocol_override_applies_to_grouped_leaf(self, reset_task_spec_registry):
        spec = _build_task_spec({"g": {"x": {"type": "int", "unit": "n/a", "value": 1}}})
        task = _build_task({"x": 7})
        resolved = await _resolve(spec, task, _build_protocol_run())
        assert resolved.parameters == {"x": 7}

    async def test_run_submission_override_applies_to_grouped_leaf(self, reset_task_spec_registry):
        spec = _build_task_spec({"g": {"x": {"type": "int", "unit": "n/a", "value": 1}}})
        protocol_run = _build_protocol_run({TASK_NAME: {"x": 9}})
        resolved = await _resolve(spec, _build_task(), protocol_run)
        assert resolved.parameters == {"x": 9}

    async def test_required_grouped_leaf_without_value_stays_absent(self, reset_task_spec_registry):
        spec = _build_task_spec({"g": {"needs_value": {"type": "int", "unit": "n/a"}}})
        resolved = await _resolve(spec, _build_task(), _build_protocol_run())
        assert "needs_value" not in resolved.parameters
