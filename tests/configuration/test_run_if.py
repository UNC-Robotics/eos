import pytest

from eos.configuration.entities.task_parameters import TaskParameterType
from eos.configuration.run_if import EosRunIfError, evaluate, parse, typecheck


def test_parse_collects_references():
    parsed = parse("prep.product > 10 and mode.value == 'high'")
    assert parsed.references == frozenset({"prep.product", "mode.value"})


@pytest.mark.parametrize(
    ("expr", "values", "expected"),
    [
        ("prep.product > 10", {"prep.product": 42}, True),
        ("prep.product > 10", {"prep.product": 5}, False),
        ("prep.product >= 0 and prep.product <= 10", {"prep.product": 5}, True),
        ("not flag.on", {"flag.on": False}, True),
        ("not flag.on", {"flag.on": True}, False),
        ("mode.value == 'high' or count.n >= 3", {"mode.value": "low", "count.n": 5}, True),
        ("mode.value == 'high' or count.n >= 3", {"mode.value": "low", "count.n": 1}, False),
    ],
)
def test_evaluate(expr, values, expected):
    assert evaluate(parse(expr), values) is expected


def test_typecheck_ok():
    parsed = parse("prep.product > 10")
    typecheck(parsed, {"prep.product": TaskParameterType.INT})


def test_typecheck_rejects_non_bool_top_level():
    parsed = parse("prep.product")
    with pytest.raises(EosRunIfError, match="must evaluate to bool"):
        typecheck(parsed, {"prep.product": TaskParameterType.INT})


def test_typecheck_rejects_mismatched_types():
    parsed = parse("prep.product == 'high'")
    with pytest.raises(EosRunIfError, match="Cannot compare"):
        typecheck(parsed, {"prep.product": TaskParameterType.INT})


def test_typecheck_rejects_unknown_ref():
    parsed = parse("prep.product > 10")
    with pytest.raises(EosRunIfError, match="Unknown reference"):
        typecheck(parsed, {})


@pytest.mark.parametrize(
    ("expr", "match"),
    [
        ("foo > 10", "Bare name"),
        ("a.b.c > 10", "Only `task.output`"),
        ("prep.product + 1 > 10", "Disallowed syntax"),
        ("len(prep.product) > 0", "Disallowed syntax"),
    ],
)
def test_parse_rejects_disallowed(expr, match):
    with pytest.raises(EosRunIfError, match=match):
        parse(expr)


def test_evaluate_missing_value_raises():
    parsed = parse("prep.product > 10")
    with pytest.raises(EosRunIfError, match="Missing value"):
        evaluate(parsed, {})


@pytest.mark.parametrize(
    ("expr", "values", "expected"),
    [
        ("prep.product < -5", {"prep.product": -10}, True),
        ("prep.product < -5", {"prep.product": 0}, False),
        ("prep.product >= -1.5", {"prep.product": -1.0}, True),
        ("prep.product == -2", {"prep.product": -2}, True),
    ],
)
def test_evaluate_negative_literals(expr, values, expected):
    assert evaluate(parse(expr), values) is expected


def test_typecheck_negative_literal_is_numeric():
    typecheck(parse("prep.product < -5"), {"prep.product": TaskParameterType.INT})


def test_evaluate_none_operand_raises_run_if_error():
    # A referenced output that is None at runtime must surface as EosRunIfError, not a raw TypeError.
    parsed = parse("prep.product > 0")
    with pytest.raises(EosRunIfError, match="Cannot compare"):
        evaluate(parsed, {"prep.product": None})
