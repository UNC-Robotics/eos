from eos.configuration.utils import (
    is_device_reference,
    is_parameter_reference,
    is_resource_reference,
)


VALID_IDENTIFIERS = [
    "x",
    "_",
    "0",
    "foo_bar",
    "Move Beaker",
    "Move To Mixer",
    "flow rate 2",
    "026749f8f40342b38157f9824ae2f512",
]

INVALID_IDENTIFIERS = [
    "",
    " leading",
    "trailing ",
    "double  space",
    "has.dot",
    "tab\there",
    "a$b",
    "has-dash",
]


def test_dot_reference_accepts_valid_identifier_on_each_side():
    # The same regex gates both sides, so testing each side independently is sufficient.
    for ident in VALID_IDENTIFIERS:
        assert is_parameter_reference(f"{ident}.field"), ident
        assert is_parameter_reference(f"task.{ident}"), ident


def test_dot_reference_rejects_invalid_identifier_on_each_side():
    for bad in INVALID_IDENTIFIERS:
        assert not is_parameter_reference(f"{bad}.field"), bad
        assert not is_parameter_reference(f"task.{bad}"), bad


def test_dot_reference_rejects_non_references():
    cases = [
        "Move Beaker",  # no dot
        ".x",  # empty left
        "x.",  # empty right
        "a.b.c",  # too many dots
        123,  # not a string
        None,
        ["a", "b"],
    ]
    for value in cases:
        assert not is_parameter_reference(value), value
        assert not is_device_reference(value), value
        if isinstance(value, str):
            assert not is_resource_reference(value), value


def test_all_three_helpers_share_the_same_rule():
    # Sanity: parameter/resource/device references all delegate to the same identifier check.
    valid = "Move Beaker To Mixer.beaker"
    assert is_parameter_reference(valid)
    assert is_resource_reference(valid)
    assert is_device_reference(valid)