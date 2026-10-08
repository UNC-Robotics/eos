import os
import sys
from pathlib import Path

import pytest

from eos.configuration.configuration_manager import ConfigurationManager
from eos.configuration.exceptions import EosDevicePluginError, EosTaskPluginError
from eos.configuration.packages import EntityType

DEVICE = '''from eos import Device


class Stirrer(Device, type="stirrer"):
    """A stirrer."""

    class Config(Device.Config):
        speed: int = 10
'''

TASK = '''from pydantic import BaseModel

from eos import Param, task

from {package}.devices.stirrer.device import Stirrer


class StirOutputs(BaseModel):
    speed: int


@task("{task_type}")
async def stir(stirrer: Stirrer, speed: int = Param(5, unit="rpm")) -> StirOutputs:
    """Stir."""
    return StirOutputs(speed=speed)
'''


def _write_package(user_dir: Path, name: str, task_source: str | None = None) -> Path:
    package = user_dir / name
    (package / "devices" / "stirrer").mkdir(parents=True)
    (package / "tasks" / "stir").mkdir(parents=True)
    (package / "pyproject.toml").write_text(f'[project]\nname = "{name}"\n')
    (package / "devices" / "stirrer" / "device.py").write_text(DEVICE)
    source = task_source or TASK.format(package=name, task_type="Stir")
    (package / "tasks" / "stir" / "task.py").write_text(source)
    return package


@pytest.fixture
def user_dir(tmp_path):
    yield tmp_path
    for name in [name for name in sys.modules if name.startswith("plugin_pkg")]:
        del sys.modules[name]


class TestPluginLoading:
    def test_loads_specs_and_implementations(self, user_dir):
        _write_package(user_dir, "plugin_pkg_a")
        manager = ConfigurationManager(str(user_dir))

        spec = manager.task_specs.get_spec_by_type("Stir")
        assert spec.devices["stirrer"].type == "stirrer"
        assert spec.get_parameter("speed").value == 5
        assert manager.task_specs.get_dir_by_type("Stir") == Path("plugin_pkg_a/stir")
        assert manager.device_specs.get_spec_by_type("stirrer").init_parameters["speed"].default == 10
        assert manager.tasks.get_plugin_class_type("Stir").type == "Stir"
        assert manager.devices.get_plugin_class_type("stirrer").__name__ == "Stirrer"

    def test_reload_picks_up_changes(self, user_dir):
        package = _write_package(user_dir, "plugin_pkg_b")
        manager = ConfigurationManager(str(user_dir))

        task_file = package / "tasks" / "stir" / "task.py"
        task_file.write_text(task_file.read_text().replace("Param(5,", "Param(7,"))
        _bump_mtime(task_file)
        manager.tasks.reload_plugin("Stir")

        assert manager.task_specs.get_spec_by_type("Stir").get_parameter("speed").value == 7

    def test_module_must_define_one_task(self, user_dir):
        _write_package(user_dir, "plugin_pkg_c", task_source="x = 1\n")
        with pytest.raises(EosTaskPluginError, match="exactly one task"):
            ConfigurationManager(str(user_dir))

    def test_duplicate_task_types_fail(self, user_dir):
        _write_package(user_dir, "plugin_pkg_d")
        _write_package(user_dir, "plugin_pkg_e", task_source=TASK.format(package="plugin_pkg_e", task_type="Stir"))
        (user_dir / "plugin_pkg_e" / "tasks" / "stir").rename(user_dir / "plugin_pkg_e" / "tasks" / "stir_2")
        (user_dir / "plugin_pkg_e" / "devices" / "stirrer").rename(user_dir / "plugin_pkg_e" / "devices" / "s2")
        task_file = user_dir / "plugin_pkg_e" / "tasks" / "stir_2" / "task.py"
        task_file.write_text(task_file.read_text().replace("devices.stirrer.device", "devices.s2.device"))

        with pytest.raises(Exception, match="Duplicate"):
            ConfigurationManager(str(user_dir))

    def test_package_name_cannot_shadow_installed_modules(self, user_dir):
        _write_package(user_dir, "json")
        with pytest.raises(EosDevicePluginError, match="clashes"):
            ConfigurationManager(str(user_dir))


def _bump_mtime(path: Path) -> None:
    mtime = path.stat().st_mtime + 2  # Bytecode caches compare whole-second mtimes
    os.utime(path, (mtime, mtime))


class TestPackageModules:
    def test_relative_user_dir_resolves_entity_paths(self, user_dir, monkeypatch):
        _write_package(user_dir, "plugin_pkg_f")
        (user_dir / "plugin_pkg_f" / "labs" / "lab_f").mkdir(parents=True)
        (user_dir / "plugin_pkg_f" / "labs" / "lab_f" / "lab.yml").write_text("name: lab_f\n")
        monkeypatch.chdir(user_dir.parent)
        manager = ConfigurationManager(user_dir.name)

        package_manager = manager.package_manager
        lab_dir = package_manager.get_entity_dir("lab_f", EntityType.LAB)
        assert lab_dir.relative_to(package_manager._user_dir) == Path("plugin_pkg_f/labs/lab_f")

    def test_load_plugins_reruns_package_init(self, user_dir):
        package = _write_package(user_dir, "plugin_pkg_g")
        (package / "__init__.py").write_text("VERSION = 1\n")
        manager = ConfigurationManager(str(user_dir))
        assert sys.modules["plugin_pkg_g"].VERSION == 1

        (package / "__init__.py").write_text("VERSION = 2\n")
        _bump_mtime(package / "__init__.py")
        manager.load_plugins()
        assert sys.modules["plugin_pkg_g"].VERSION == 2

    def test_nested_entity_files_are_ignored(self, user_dir):
        package = _write_package(user_dir, "plugin_pkg_h")
        (package / "tasks" / "stir" / "vendored").mkdir()
        (package / "tasks" / "stir" / "vendored" / "task.py").write_text("x = 1\n")

        manager = ConfigurationManager(str(user_dir))
        assert list(manager.task_specs.get_all_specs()) == ["Stir"]

    def test_reload_rejects_renaming_to_existing_type(self, user_dir):
        package = _write_package(user_dir, "plugin_pkg_i")
        other = package / "tasks" / "stir_fast"
        other.mkdir()
        (other / "task.py").write_text(TASK.format(package="plugin_pkg_i", task_type="Stir Fast"))
        manager = ConfigurationManager(str(user_dir))

        task_file = package / "tasks" / "stir" / "task.py"
        task_file.write_text(TASK.format(package="plugin_pkg_i", task_type="Stir Fast"))
        _bump_mtime(task_file)
        with pytest.raises(EosTaskPluginError, match="already exists"):
            manager.tasks.reload_plugin("Stir")
        assert manager.task_specs.get_dir_by_type("Stir Fast") == Path("plugin_pkg_i/stir_fast")

    def test_campaign_optimizer_reloads_from_disk(self, user_dir):
        package = _write_package(user_dir, "plugin_pkg_j")
        protocol_dir = package / "protocols" / "proto_j"
        protocol_dir.mkdir(parents=True)
        (protocol_dir / "protocol.yml").write_text("type: proto_j\n")
        optimizer = protocol_dir / "optimizer.py"
        optimizer.write_text("def eos_create_campaign_optimizer():\n    return {'v': 1}, None\n")
        manager = ConfigurationManager(str(user_dir))

        assert manager.campaign_optimizers.get_campaign_optimizer_creation_parameters("proto_j")[0] == {"v": 1}
        optimizer.write_text("def eos_create_campaign_optimizer():\n    return {'v': 2}, None\n")
        _bump_mtime(optimizer)
        manager.campaign_optimizers.unload_campaign_optimizer("proto_j")
        assert manager.campaign_optimizers.get_campaign_optimizer_creation_parameters("proto_j")[0] == {"v": 2}
