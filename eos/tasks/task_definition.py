"""The Python API for declaring EOS tasks: the ``task`` decorator, ``Param``, and ``Context``."""

import asyncio
import inspect
import types
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel, Field, ValidationError
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from eos.configuration.entities.task_parameters import TaskParameterType
from eos.configuration.entities.task_spec_def import TaskSpecDef
from eos.database.file_db_interface import FileDbInterface
from eos.devices.base_device import BaseDevice
from eos.resources.entities.resource import Resource
from eos.tasks.exceptions import EosTaskExecutionError
from eos.tasks.file import File
from eos.utils.ray_utils import RayActorWrapper

_SCALAR_TYPES: dict[type, TaskParameterType] = {
    int: TaskParameterType.INT,
    float: TaskParameterType.FLOAT,
    str: TaskParameterType.STR,
    bool: TaskParameterType.BOOL,
}
_PARAM_METADATA_KEY = "eos"


def Param(  # noqa: N802
    default: Any = PydanticUndefined,
    *,
    desc: str | None = None,
    unit: str | None = None,
    min: Any = None,  # noqa: A002
    max: Any = None,  # noqa: A002
    group: str | None = None,
    file_name: str | None = None,
) -> Any:
    """
    Declare a task input or output's default and metadata. ``min``/``max`` are inclusive and ``group`` is
    presentational. ``file_name`` names an output file (default: the field name).
    """
    metadata = {"unit": unit, "min": min, "max": max, "group": group, "file_name": file_name}
    metadata = {key: _as_list(value) for key, value in metadata.items() if value is not None}
    return Field(default, description=desc, json_schema_extra={_PARAM_METADATA_KEY: metadata})


@dataclass(frozen=True)
class Context:
    """Runtime information about the executing task. Declare an argument of this type to receive it."""

    task_name: str
    protocol_run_name: str | None


def build_task_output_file_path(protocol_run_name: str | None, task_name: str, file_name: str) -> str:
    """Build the SeaweedFS key for a task output file."""
    prefix = protocol_run_name if protocol_run_name is not None else "on_demand"
    return f"{prefix}/{task_name}/{file_name}"


class _InputKind(Enum):
    DEVICE = auto()
    RESOURCE = auto()
    FILE = auto()
    PARAMETER = auto()
    CONTEXT = auto()


class _OutputKind(Enum):
    PARAMETER = auto()
    RESOURCE = auto()
    FILE = auto()
    FILES = auto()


@dataclass(frozen=True)
class _Input:
    name: str
    kind: _InputKind
    annotation: Any
    default: Any = PydanticUndefined


class TaskDefinition:
    """A task function together with the spec EOS derives from its signature."""

    def __init__(self, task_type: str, fn: Callable[..., Awaitable[BaseModel | None]]):
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f"Task '{task_type}' must be an async function.")

        self.type = task_type
        self.fn = fn
        self._inputs: list[_Input] = []
        self._resource_classes: dict[str, type[Resource]] = {}
        self._outputs: dict[str, tuple[_OutputKind, str]] = {}
        self._output_model: type[BaseModel] | None = None
        self.spec = self._build_spec()

    async def __call__(self, *args: Any, **kwargs: Any) -> BaseModel | None:
        return await self.fn(*args, **kwargs)

    async def execute(
        self,
        context: Context,
        devices: dict[str, RayActorWrapper],
        parameters: dict[str, Any],
        resources: dict[str, Resource],
        files: dict[str, File],
        file_db_provider: Callable[[], FileDbInterface] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Resource], list[str]]:
        """Run the task and upload its output files. Returns output parameters, resources and file names."""
        try:
            typed_resources = {
                name: self._resource_classes.get(name, Resource).model_validate(resource.model_dump())
                for name, resource in resources.items()
            }
            kwargs = self._build_kwargs(context, devices, parameters, typed_resources, files)
            output_parameters, returned_resources, output_files = self._split_outputs(await self.fn(**kwargs))

            output_resources = {
                name: Resource.model_validate(res.model_dump())
                for name, res in {**typed_resources, **returned_resources}.items()
            }
            output_file_names = await self._upload_output_files(context, output_files, file_db_provider)
            return output_parameters, output_resources, output_file_names
        except Exception as e:
            raise EosTaskExecutionError(f"Error executing task {context.task_name}: {e!s}") from e

    def _build_kwargs(
        self,
        context: Context,
        devices: dict[str, RayActorWrapper],
        parameters: dict[str, Any],
        resources: dict[str, Resource],
        files: dict[str, File],
    ) -> dict[str, Any]:
        sources = {
            _InputKind.DEVICE: devices,
            _InputKind.RESOURCE: resources,
            _InputKind.FILE: files,
        }
        kwargs: dict[str, Any] = {}
        for task_input in self._inputs:
            if task_input.kind == _InputKind.CONTEXT:
                kwargs[task_input.name] = context
            elif task_input.kind == _InputKind.PARAMETER:
                value = parameters.get(task_input.name, task_input.default)
                if value is PydanticUndefined:
                    raise ValueError(f"Missing required parameter '{task_input.name}'.")
                kwargs[task_input.name] = _coerce_parameter(task_input.annotation, value)
            else:
                kwargs[task_input.name] = sources[task_input.kind].get(task_input.name)
        return kwargs

    def _split_outputs(
        self, result: BaseModel | None
    ) -> tuple[dict[str, Any], dict[str, Resource], dict[str, bytes | Path]]:
        if self._output_model is None:
            if result is not None:
                raise TypeError(f"Task '{self.type}' declares no outputs but returned a value.")
            return {}, {}, {}
        if not isinstance(result, self._output_model):
            raise TypeError(f"Task '{self.type}' must return {self._output_model.__name__}.")

        parameter_names = {name for name, (kind, _) in self._outputs.items() if kind == _OutputKind.PARAMETER}
        parameters = result.model_dump(mode="json", include=parameter_names)
        resources, output_files = {}, {}
        for name, (kind, output_name) in self._outputs.items():
            value = getattr(result, name)
            if value is None or kind == _OutputKind.PARAMETER:
                continue
            if kind == _OutputKind.RESOURCE:
                resources[output_name] = value
                continue
            files = value if kind == _OutputKind.FILES else {output_name: value}
            if duplicates := files.keys() & output_files.keys():
                raise ValueError(f"Task '{self.type}' returned duplicate output files {sorted(duplicates)}.")
            output_files.update(files)
        return parameters, resources, output_files

    async def _upload_output_files(
        self,
        context: Context,
        output_files: dict[str, bytes | Path],
        file_db_provider: Callable[[], FileDbInterface] | None,
    ) -> list[str]:
        """Upload all output files concurrently and return their names. Gates task completion."""
        if not output_files:
            return []
        if file_db_provider is None:
            raise EosTaskExecutionError(f"No file storage available to upload outputs of task '{context.task_name}'.")

        file_db = file_db_provider()
        await asyncio.gather(
            *(
                file_db.store_file(
                    build_task_output_file_path(context.protocol_run_name, context.task_name, name), data
                )
                for name, data in output_files.items()
            )
        )
        return list(output_files.keys())

    # Spec building

    def _build_spec(self) -> TaskSpecDef:
        hints = get_type_hints(self.fn, include_extras=True)
        spec: dict[str, Any] = {
            "type": self.type,
            "desc": inspect.getdoc(self.fn),
            "devices": {},
            "input_resources": {},
            "input_parameters": {},
            "input_files": {},
        }

        for name, param in inspect.signature(self.fn).parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                raise TypeError(f"Task '{self.type}' cannot take *args or **kwargs.")
            if name not in hints:
                raise TypeError(f"Task '{self.type}' input '{name}' needs a type annotation.")
            self._add_input(spec, name, hints[name], param.default)

        self._add_outputs(spec, hints.get("return"))

        try:
            return TaskSpecDef.model_validate(spec)
        except ValidationError as e:
            raise TypeError(f"Task '{self.type}' has an invalid spec: {e}") from e

    def _add_input(self, spec: dict[str, Any], name: str, annotation: Any, default: Any) -> None:
        inner, optional = _unwrap_optional(annotation)
        where = f"Task '{self.type}' input '{name}'"

        if inner is Context:
            self._inputs.append(_Input(name, _InputKind.CONTEXT, inner))
            return

        info = default if isinstance(default, FieldInfo) else Field(_default_or_undefined(default))

        if inspect.isclass(inner) and issubclass(inner, BaseDevice | Resource | File):
            if optional and info.default is not None:
                raise TypeError(f"{where} is optional and must default to None.")
            requirement: dict[str, Any] = {"optional": optional}
            if issubclass(inner, BaseDevice):
                kind, section = _InputKind.DEVICE, "devices"
                requirement["type"] = _declared_type(inner, inner.device_type, where)
            elif issubclass(inner, Resource):
                kind, section = _InputKind.RESOURCE, "input_resources"
                requirement["type"] = _declared_type(inner, inner.resource_type, where)
                self._resource_classes[name] = inner
            else:
                kind, section = _InputKind.FILE, "input_files"
                requirement["desc"] = info.description
            spec[section][name] = requirement
            self._inputs.append(_Input(name, kind, inner))
            return

        if optional:
            raise TypeError(f"{where} is a parameter and cannot be optional. Give it a default instead.")

        metadata = _param_metadata(info)
        parameter = {**_parameter_type(inner, where), "desc": info.description}
        values = {key: metadata.get(key) for key in ("unit", "min", "max")}
        if info.default is not PydanticUndefined:
            values["value"] = _as_list(info.default)
        parameter |= {key: _promote_ints(value, parameter) for key, value in values.items() if value is not None}

        parameters = spec["input_parameters"]
        group = metadata.get("group")
        if (group and "type" in parameters.get(group, {})) or (not group and name in parameters):
            raise TypeError(f"{where} conflicts with a parameter group of the same name.")
        (parameters.setdefault(group, {}) if group else parameters)[name] = parameter
        self._inputs.append(_Input(name, _InputKind.PARAMETER, inner, parameter.get("value", PydanticUndefined)))

    def _add_outputs(self, spec: dict[str, Any], annotation: Any) -> None:
        if annotation is None or annotation is type(None):
            return
        if not (inspect.isclass(annotation) and issubclass(annotation, BaseModel)):
            raise TypeError(f"Task '{self.type}' must return None or a pydantic model.")

        self._output_model = annotation
        spec["output_parameters"], spec["output_files"] = {}, {}
        spec["output_resources"] = {
            name: {"type": requirement["type"]} for name, requirement in spec["input_resources"].items()
        }

        for name, field in annotation.model_fields.items():
            inner, _ = _unwrap_optional(field.annotation)
            where = f"Task '{self.type}' output '{name}'"
            metadata = _param_metadata(field)
            if inner in (bytes, Path):
                file_name = metadata.get("file_name", name)
                if file_name in spec["output_files"]:
                    raise TypeError(f"{where} reuses output file name '{file_name}'.")
                spec["output_files"][file_name] = {"desc": field.description}
                self._outputs[name] = (_OutputKind.FILE, file_name)
            elif inner in (dict[str, bytes], dict[str, Path]):
                self._outputs[name] = (_OutputKind.FILES, name)  # File names known only at runtime
            elif inspect.isclass(inner) and issubclass(inner, Resource):
                spec["output_resources"][name] = {"type": _declared_type(inner, inner.resource_type, where)}
                self._outputs[name] = (_OutputKind.RESOURCE, name)
            else:
                parameter_type = _parameter_type(inner, where)["type"]
                unit = metadata.get("unit")
                spec["output_parameters"][name] = {"type": parameter_type, "desc": field.description, "unit": unit}
                self._outputs[name] = (_OutputKind.PARAMETER, name)


def task(task_type: str) -> Callable[[Callable[..., Awaitable[BaseModel | None]]], TaskDefinition]:
    """Declare an async function as an EOS task of the given type. Its signature and docstring form the task spec."""

    def decorator(fn: Callable[..., Awaitable[BaseModel | None]]) -> TaskDefinition:
        return TaskDefinition(task_type, fn)

    return decorator


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    """Return ``(T, True)`` for ``T | None``, else ``(annotation, False)``."""
    if get_origin(annotation) in (Union, types.UnionType):
        args = get_args(annotation)
        non_none = [arg for arg in args if arg is not type(None)]
        if len(non_none) == 1 and len(args) == 2:  # noqa: PLR2004
            return non_none[0], True
    return annotation, False


def _declared_type(cls: type, declared: str | None, where: str) -> str:
    if not declared:
        raise TypeError(f"{where} is annotated with '{cls.__name__}', which declares no type.")
    return declared


def _default_or_undefined(default: Any) -> Any:
    return PydanticUndefined if default is inspect.Parameter.empty else default


def _param_metadata(info: FieldInfo) -> dict[str, Any]:
    extra = info.json_schema_extra
    return extra.get(_PARAM_METADATA_KEY, {}) if isinstance(extra, dict) else {}


def _parameter_type(annotation: Any, where: str) -> dict[str, Any]:
    """Map a Python annotation to a task parameter type spec."""
    if annotation in _SCALAR_TYPES:
        return {"type": _SCALAR_TYPES[annotation]}

    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Literal and args and all(isinstance(arg, str) for arg in args):
        return {"type": TaskParameterType.CHOICE, "choices": list(args)}
    if annotation is dict or origin is dict:
        return {"type": TaskParameterType.DICT}
    if origin is list and len(args) == 1 and args[0] in _SCALAR_TYPES:
        return {"type": TaskParameterType.LIST, "element_type": _SCALAR_TYPES[args[0]]}
    if origin is tuple and args and args[0] in _SCALAR_TYPES:
        if len(args) == 2 and args[1] is Ellipsis:  # noqa: PLR2004
            return {"type": TaskParameterType.LIST, "element_type": _SCALAR_TYPES[args[0]]}
        if all(arg is args[0] for arg in args):
            return {"type": TaskParameterType.LIST, "element_type": _SCALAR_TYPES[args[0]], "length": len(args)}

    raise TypeError(
        f"{where} has unsupported type '{annotation}'. "
        "Use int, float, str, bool, Literal[...], list[T], tuple[T, ...], or dict."
    )


def _as_list(value: Any) -> Any:
    return list(value) if isinstance(value, tuple) else value


def _promote_ints(value: Any, parameter: dict[str, Any]) -> Any:
    """Promote int literals to floats for float parameters and float list elements."""
    element_type = parameter.get("element_type", parameter["type"])
    if element_type != TaskParameterType.FLOAT:
        return value
    if isinstance(value, list):
        return [_promote_ints(element, {"type": element_type}) for element in value]
    return float(value) if isinstance(value, int) and not isinstance(value, bool) else value


def _coerce_parameter(annotation: Any, value: Any) -> Any:
    return tuple(value) if get_origin(annotation) is tuple and isinstance(value, list) else value
