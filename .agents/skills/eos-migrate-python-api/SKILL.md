---
name: eos-migrate-python-api
description: Migrate EOS packages from the YAML + BaseTask/BaseDevice API (EOS 0.30 and earlier) to the Python-only API of EOS 0.31 (`@task`, `Param`, `Device`, `Resource`, `File`, `Context`). Use when a package still has `task.yml` or `device.yml` files, imports `eos.tasks.base_task` or `eos.devices.base_device`, or fails to load on EOS 0.31.
---

# Migrate an EOS package to the Python-only API

EOS 0.31 removed `task.yml` and `device.yml`. Each task is now one decorated async function in `task.py`, and each device is one `Device` subclass in `device.py`. EOS derives the spec from the code. Labs, protocols and optimizers keep their YAML/Python format.

## Workflow

1. Inventory the package: every `devices/*/device.yml` + `device.py` and `tasks/*/task.yml` + `task.py`. Read each pair fully before rewriting.
2. Migrate devices first, then resource types, then tasks (tasks import both).
3. Delete each `task.yml` / `device.yml` once its Python file carries all of its information.
4. Validate (see below) and fix every error.
5. Report anything you could not map exactly, such as old tasks that accepted undeclared devices.

Preserve names exactly. Task types, device types, resource types, and the names of devices, resources, parameters and files are referenced by labs, protocols, saved protocol runs and campaigns. Renaming any of them breaks those references.

## Package imports

Packages are now importable Python packages named after their directory. Replace `run_path`, `spec_from_file_location`, `sys.path` hacks and `user.<pkg>...` imports with regular imports:

```python
from my_package.devices.mixer.device import Mixer
from my_package.common.bridge import Bridge
```

The package directory name must be a valid Python identifier and must not clash with an installed module. Suggest a rename to the user if it doesn't qualify. Do not rename silently.

## Devices

Old:

```yaml
# device.yml
type: magnetic_mixer
desc: Magnetic mixer for mixing the contents of a container
init_parameters:
  port: 5004
  host: localhost
```

```python
class MagneticMixer(BaseDevice):
    async def _initialize(self, init_parameters: dict[str, Any]) -> None:
        self.client = DeviceClient(init_parameters["host"], int(init_parameters["port"]))
```

New:

```python
from eos import Device

from my_package.common.device_client import DeviceClient


class MagneticMixer(Device, type="magnetic_mixer"):
    """Magnetic mixer for mixing the contents of a container."""

    class Config(Device.Config):
        port: int = 5004
        host: str = "localhost"

    async def _initialize(self, config: Config) -> None:
        self.client = DeviceClient(config.host, config.port)
```

- `type` from `device.yml` becomes the `type=` class keyword. `desc` becomes the docstring.
- Each `init_parameters` entry becomes a typed `Config` field. The YAML value becomes the default. Infer the type from the value and from how the code uses it, and drop the casts (`int(...)`) the old code needed. A field with no sensible default has no default, which makes it required in the lab.
- `Config` forbids unknown fields. Check every lab that uses this device type: each `init_parameters` key must exist in `Config` and have a valid type.
- `_initialize(self, config: Config)` replaces `_initialize(self, init_parameters)`. `_cleanup` and `_report` are optional now. Delete empty ones.
- Each `device.py` must define exactly one class with a `type`. Shared connection code goes in a base `Device` subclass without a `type`, in a shared module, and the base `Config` is extended by subclassing it.
- If a library only exists on the computer that runs the device (such as a Windows-only SDK), import it inside `_initialize` so the orchestrator can still load the device.

## Resource types

Tasks now declare resources with `Resource` subclasses. Create one per resource type used in the old `input_resources`/`output_resources`, in a shared module such as `<package>/resources.py`:

```python
from eos import Resource


class Beaker500(Resource, type="beaker_500"): ...
```

`Resource` subclasses cannot add fields. Data lives in `meta`. Keep the `resource_types` in `lab.yml` as they are.

## Tasks

Old:

```yaml
# task.yml
type: Magnetic Mixing
desc: Mix the contents of a beaker.
devices:
  mixer:
    type: magnetic_mixer
input_resources:
  beaker:
    type: beaker_500
input_parameters:
  mixing_time:
    type: int
    unit: sec
    value: 60
    min: 1
    max: 3600
    desc: Mixing duration
output_parameters:
  final_speed:
    type: int
    unit: rpm
    desc: Speed at the end of mixing
output_files:
  log.csv:
    desc: Mixing log
```

```python
class MagneticMixing(BaseTask):
    async def _execute(self, devices, parameters, resources):
        mixer = devices["mixer"]
        speed = mixer.mix(resources["beaker"].name, parameters["mixing_time"])
        resources["beaker"].meta["mixed"] = True
        return {"final_speed": speed}, resources, {"log.csv": mixer.get_log()}
```

New:

```python
from pydantic import BaseModel

from eos import Param, task

from my_package.devices.magnetic_mixer.device import MagneticMixer
from my_package.resources import Beaker500


class MagneticMixingOutputs(BaseModel):
    final_speed: int = Param(unit="rpm", desc="Speed at the end of mixing")
    log: bytes = Param(file_name="log.csv", desc="Mixing log")


@task("Magnetic Mixing")
async def magnetic_mixing(
    mixer: MagneticMixer,
    beaker: Beaker500,
    mixing_time: int = Param(60, unit="sec", min=1, max=3600, desc="Mixing duration"),
) -> MagneticMixingOutputs:
    """Mix the contents of a beaker."""
    speed = mixer.mix(beaker.name, mixing_time)
    beaker.meta["mixed"] = True
    return MagneticMixingOutputs(final_speed=speed, log=mixer.get_log())
```

### Inputs

Argument names must equal the old YAML keys. EOS sorts arguments by annotation:

| Old `task.yml` | New argument |
|---|---|
| `devices: {name: {type: t}}` | `name: DeviceClass` (the class whose `type` is `t`) |
| `input_resources: {name: {type: t}}` | `name: ResourceClass` (the class whose `type` is `t`) |
| `input_files: {name: {desc}}` | `name: File = Param(desc=...)` |
| `input_parameters` entry | `name: T = Param(...)` (see below) |
| `self._task_name`, `self._protocol_run_name` | an argument annotated `Context` (`ctx.task_name`, `ctx.protocol_run_name`) |

Devices, resources and files can be optional with `X | None = None`. Parameters cannot be optional. Give them a default instead.

### Parameters

| Old | New |
|---|---|
| `type: int` / `float` / `str` / `bool` | `int` / `float` / `str` / `bool` |
| `type: choice`, `choices: [a, b]` | `Literal["a", "b"]` |
| `type: list`, `element_type: T` | `list[T]` |
| `type: list`, `element_type: T`, `length: n` | `tuple[T, T, ...]` with n elements (the task receives a tuple) |
| `type: dict` | `dict` |
| `value` | first positional argument of `Param` (no `value` means required) |
| `unit`, `min`, `max`, `desc` | `Param(unit=..., min=..., max=..., desc=...)`. Drop `unit: n/a`. |
| list `min`/`max` lists | tuples, e.g. `min=(0.5, 0.5)` |
| group (a top-level key with no `type:`) | `Param(group="<group key>")` on each child parameter |

A plain default (`speed: int = 5`) also works when there is no metadata.

### Outputs

Return a pydantic `BaseModel`, or `None` when the old task returned nothing. Each field is one output:

| Old | New field |
|---|---|
| `output_parameters` entry | `name: T = Param(unit=..., desc=...)` |
| `output_files` entry `name.ext` | `field: bytes = Param(file_name="name.ext", desc=...)` (`Param` is not needed when the field name is the file name) |
| file names only known at runtime | `files: dict[str, bytes]` |
| large files | `Path` or `dict[str, Path]`, streamed from disk |
| optional outputs | `X | None = None` |
| returned resource replaced by a device | `beaker: Beaker500` |

Input resources are outputs automatically, and `meta` changes are saved, so tasks that only returned their input resources need no resource field. A device method that returns a new resource object needs a resource output field with the same name as the input.

### Input files

`InputFileHandle` is now `File`, with the same `read()`, `stream()` and `download_to(path)` methods. Protocol file references (`task_name.file_name`) are unchanged.

## Protocols

Validation is stricter now. A protocol may only assign the devices and resources the task declares, and each device must have the declared type. Old tasks without a `devices` section that still received devices in protocols, or that accepted several device types under one name, will now fail validation. Tell the user which tasks are affected and propose a fix, for example one task per device type, or optional arguments. Do not change protocol YAML without approval.

## Validate

Run from the EOS repository root with the package name, then load every lab and protocol of the package:

```bash
uv run python -c "
from eos.configuration.configuration_manager import ConfigurationManager
cm = ConfigurationManager('user', allowed_packages={'my_package'})
cm.load_labs({'my_lab'})
cm.load_protocols({'my_protocol'})
print('ok')
"
```

Use the `user_dir` from `config.yml` if it isn't `user`. Errors name the file and the problem. Fix them all, then run `uv run ruff check` and `uv run ruff format` on the package if the project uses ruff.

## Checklist

- No `task.yml`, `device.yml`, `BaseTask`, `eos.tasks.base_task`, `InputFileHandle` or `init_parameters: dict` left (grep for them).
- All public API imports come from `eos`: `task`, `Param`, `Context`, `File`, `Device`, `Resource`.
- Every type string, input name and output name matches the old YAML.
- Every lab and protocol of the package loads.
