"""Parse, type-check, and evaluate whitelisted boolean expressions for task `run_if`.

References are `task_name.output_name` (single-level attribute access). Allowed: literals
(including negative numbers), comparisons (==, !=, <, <=, >, >=), boolean and/or/not. No
binary arithmetic, calls, indexing, attribute chains, or bare identifiers.
"""

import ast
from collections.abc import Mapping
from dataclasses import dataclass

from eos.configuration.entities.task_parameters import TaskParameterType
from eos.configuration.exceptions import EosConfigurationError


class EosRunIfError(EosConfigurationError):
    """Raised when a run_if expression fails to parse, type-check, or evaluate."""


INT, FLOAT, STR, BOOL, LIST, DICT = "int", "float", "str", "bool", "list", "dict"
_NUMERIC = frozenset({INT, FLOAT})

_PARAM_TYPE_TO_EXPR_TYPE: Mapping[TaskParameterType, str] = {
    TaskParameterType.INT: INT,
    TaskParameterType.FLOAT: FLOAT,
    TaskParameterType.STR: STR,
    TaskParameterType.BOOL: BOOL,
    TaskParameterType.CHOICE: STR,
    TaskParameterType.LIST: LIST,
    TaskParameterType.DICT: DICT,
}

_ALLOWED_NODES: tuple[type, ...] = (
    ast.Expression,
    ast.BoolOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Constant,
    ast.Name,
    ast.Attribute,
    ast.Load,
    ast.And,
    ast.Or,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


@dataclass(frozen=True)
class ParsedExpr:
    """A whitelisted expression AST plus the `task.output` references it touches."""

    source: str
    tree: ast.AST
    references: frozenset[str]


def parse(source: str) -> ParsedExpr:
    """Parse `source`, enforce the whitelist, collect `task.output` references."""
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as e:
        raise EosRunIfError(f"Invalid run_if expression '{source}': {e.msg}") from e

    refs: set[str] = set()
    attribute_owners: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise EosRunIfError(f"Disallowed syntax {type(node).__name__} in run_if '{source}'.")
        if isinstance(node, ast.Attribute):
            if not isinstance(node.value, ast.Name):
                raise EosRunIfError(f"Only `task.output` references are allowed in run_if '{source}'.")
            attribute_owners.add(id(node.value))
            refs.add(f"{node.value.id}.{node.attr}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and id(node) not in attribute_owners:
            raise EosRunIfError(f"Bare name '{node.id}' is not allowed; use `task.output` in run_if '{source}'.")

    return ParsedExpr(source=source, tree=tree, references=frozenset(refs))


def typecheck(parsed: ParsedExpr, ref_types: Mapping[str, TaskParameterType]) -> None:
    """Verify `parsed` is type-correct. The top expression must be bool."""
    top = _type_of(parsed.tree, ref_types, parsed.source)
    if top != BOOL:
        raise EosRunIfError(f"run_if '{parsed.source}' must evaluate to bool, got {top}.")


def evaluate(parsed: ParsedExpr, values: Mapping[str, object]) -> bool:
    """Evaluate `parsed` using `values["task.output"] -> value`."""
    return bool(_eval(parsed.tree, values, parsed.source))


def _literal_type(value: object, source: str) -> str:
    if isinstance(value, bool):
        return BOOL
    if isinstance(value, int):
        return INT
    if isinstance(value, float):
        return FLOAT
    if isinstance(value, str):
        return STR
    raise EosRunIfError(f"Unsupported literal {value!r} in run_if '{source}'.")


def _check_compare(op: ast.cmpop, left: str, right: str, source: str) -> str:
    if isinstance(op, ast.Eq | ast.NotEq):
        if left != right and not (left in _NUMERIC and right in _NUMERIC):
            raise EosRunIfError(f"Cannot compare {left} to {right} for equality in '{source}'.")
        return BOOL
    if not ((left in _NUMERIC and right in _NUMERIC) or (left == STR and right == STR)):
        raise EosRunIfError(f"Cannot order-compare {left} to {right} in '{source}'.")
    return BOOL


def _unaryop_type(op: ast.unaryop, operand_type: str, source: str) -> str:
    if isinstance(op, ast.Not):
        if operand_type != BOOL:
            raise EosRunIfError(f"'not' requires a bool operand, got {operand_type} in '{source}'.")
        return BOOL
    if operand_type not in _NUMERIC:  # unary +/- (e.g. negative literals)
        sign = "-" if isinstance(op, ast.USub) else "+"
        raise EosRunIfError(f"Unary '{sign}' requires a numeric operand, got {operand_type} in '{source}'.")
    return operand_type


def _type_of(node: ast.AST, ref_types: Mapping[str, TaskParameterType], source: str) -> str:
    if isinstance(node, ast.Expression):
        return _type_of(node.body, ref_types, source)
    if isinstance(node, ast.Constant):
        return _literal_type(node.value, source)
    if isinstance(node, ast.Attribute):
        ref = f"{node.value.id}.{node.attr}"  # type: ignore[attr-defined]
        param_type = ref_types.get(ref)
        if param_type is None:
            raise EosRunIfError(f"Unknown reference '{ref}' in run_if '{source}'.")
        return _PARAM_TYPE_TO_EXPR_TYPE[param_type]
    if isinstance(node, ast.UnaryOp):
        return _unaryop_type(node.op, _type_of(node.operand, ref_types, source), source)
    if isinstance(node, ast.BoolOp):
        op_name = "and" if isinstance(node.op, ast.And) else "or"
        for value in node.values:
            value_type = _type_of(value, ref_types, source)
            if value_type != BOOL:
                raise EosRunIfError(f"'{op_name}' operand must be bool, got {value_type} in '{source}'.")
        return BOOL
    if isinstance(node, ast.Compare):
        left = _type_of(node.left, ref_types, source)
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            right = _type_of(comparator, ref_types, source)
            _check_compare(op, left, right, source)
            left = right
        return BOOL
    raise EosRunIfError(f"Disallowed node {type(node).__name__} in '{source}'.")


def _eval(node: ast.AST, values: Mapping[str, object], source: str) -> object:  # noqa: PLR0911
    if isinstance(node, ast.Expression):
        return _eval(node.body, values, source)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Attribute):
        ref = f"{node.value.id}.{node.attr}"  # type: ignore[attr-defined]
        if ref not in values:
            raise EosRunIfError(f"Missing value for reference '{ref}' in '{source}'.")
        return values[ref]
    if isinstance(node, ast.UnaryOp):
        operand = _eval(node.operand, values, source)
        if isinstance(node.op, ast.Not):
            return not operand
        return -operand if isinstance(node.op, ast.USub) else +operand
    if isinstance(node, ast.BoolOp):
        reducer = all if isinstance(node.op, ast.And) else any
        return reducer(_eval(v, values, source) for v in node.values)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, values, source)
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            right = _eval(comparator, values, source)
            try:
                matched = _COMPARE_OPS[type(op)](left, right)
            except TypeError as e:
                raise EosRunIfError(f"Cannot compare {left!r} and {right!r} in '{source}': {e}") from e
            if not matched:
                return False
            left = right
        return True
    raise EosRunIfError(f"Cannot evaluate node {type(node).__name__} in '{source}'.")


_COMPARE_OPS = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}
