import subprocess
from pathlib import Path
from typing import Annotated, Literal

import typer
import yaml

from eos.configuration.exceptions import EosConfigurationError
from eos.configuration.packages import Package, discover_packages
from eos.logging.logger import log

pkg_app = typer.Typer(no_args_is_help=True)
add_app = typer.Typer(no_args_is_help=True)
pkg_app.add_typer(add_app, name="add", help="Add entities to an existing package")

EntityType = Literal["lab", "device", "task", "protocol"]

DEFAULT_CONFIG_PATH = "./config.yml"
DEFAULT_USER_DIR = "./user"


def _resolve_user_dir(user_dir: str | None, config: str) -> Path:
    """Resolve the user directory with precedence: --user-dir > config.yml's user_dir > ./user."""
    if user_dir is not None:
        return Path(user_dir)
    config_path = Path(config)
    if config_path.is_file():
        try:
            with config_path.open() as f:
                data = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError) as e:
            log.warning(f"Could not read user_dir from {config_path}: {e}")
        else:
            configured = data.get("user_dir")
            if configured:
                return Path(configured)
    return Path(DEFAULT_USER_DIR)


def _discover_or_exit(user_dir: Path) -> dict[str, Package]:
    """Run discover_packages, converting EosConfigurationError into a clean CLI exit."""
    try:
        return discover_packages(user_dir)
    except EosConfigurationError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from e


def _run_uv_install(pyproject: Path, extra_args: list[str]) -> None:
    cmd = ["uv", "pip", "install", "-r", str(pyproject), *extra_args]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        typer.echo(f"Failed to install dependencies from {pyproject}: {e}", err=True)
        raise typer.Exit(1) from e


_GITIGNORE = """\
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[codz]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# PyInstaller
*.manifest
*.spec

# Installer logs
pip-log.txt
pip-delete-this-directory.txt

# Unit test / coverage reports
htmlcov/
.tox/
.nox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.py.cover
.hypothesis/
.pytest_cache/
cover/

# Translations
*.mo
*.pot

# Django stuff:
*.log
local_settings.py
db.sqlite3
db.sqlite3-journal

# Flask stuff:
instance/
.webassets-cache

# Scrapy stuff:
.scrapy

# Sphinx documentation
docs/_build/

# PyBuilder
.pybuilder/
target/

# Jupyter Notebook
.ipynb_checkpoints

# IPython
profile_default/
ipython_config.py

# pyenv
# .python-version

# pipenv
# Pipfile.lock

# UV
# uv.lock

# poetry
# poetry.lock
# poetry.toml

# pdm
# pdm.lock
# pdm.toml
.pdm-python
.pdm-build/

# pixi
# pixi.lock
.pixi

# PEP 582
__pypackages__/

# Celery stuff
celerybeat-schedule
celerybeat.pid

# Redis
*.rdb
*.aof
*.pid

# RabbitMQ
mnesia/
rabbitmq/
rabbitmq-data/

# ActiveMQ
activemq-data/

# SageMath parsed files
*.sage.py

# Environments
.env
.envrc
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# Spyder project settings
.spyderproject
.spyproject

# Rope project settings
.ropeproject

# mkdocs documentation
/site

# mypy
.mypy_cache/
.dmypy.json
dmypy.json

# Pyre type checker
.pyre/

# pytype static type analyzer
.pytype/

# Cython debug symbols
cython_debug/

# PyCharm
# .idea/

# Abstra
.abstra/

# Visual Studio Code
# .vscode/

# Ruff stuff:
.ruff_cache/

# PyPI configuration file
.pypirc

# Marimo
marimo/_static/
marimo/_lsp/
__marimo__/

# Streamlit
.streamlit/secrets.toml
"""


def _validate_package_exists(package_dir: Path) -> None:
    """Validate that the package exists and has the expected structure."""
    if not package_dir.exists():
        raise typer.BadParameter(f"Package directory {package_dir} does not exist")
    if not package_dir.is_dir():
        raise typer.BadParameter(f"{package_dir} is not a directory")


def _add_entity(package_dir: Path, entity_type: EntityType, name: str, files: dict[str, str] | None = None) -> None:
    """Add a new entity to the package with specified files."""
    base_dir = package_dir / f"{entity_type}s" / name

    try:
        base_dir.mkdir(parents=True, exist_ok=False)

        if files:
            for filename, content in files.items():
                file_path = base_dir / filename
                file_path.write_text(content or "")

        typer.echo(f"Successfully created {entity_type} '{name}' in {base_dir}")
    except FileExistsError:
        typer.echo(f"Error: {entity_type.title()} '{name}' already exists", err=True)
    except Exception as e:
        typer.echo(f"Error creating {entity_type}: {e!s}", err=True)


@pkg_app.command(name="create")
def create_package(
    name: Annotated[str, typer.Argument(help="Name of the package to create")],
    user_dir: Annotated[
        str | None,
        typer.Option("--user-dir", "-u", help="Override user directory (defaults to config.yml or ./user)"),
    ] = None,
    config: Annotated[str, typer.Option("--config", "-c", help="Path to EOS config YAML")] = DEFAULT_CONFIG_PATH,
) -> None:
    """Create a new package with the specified name in the user directory."""
    resolved_user_dir = _resolve_user_dir(user_dir, config)
    package_dir = resolved_user_dir / name
    subdirs = ["devices", "tasks", "labs", "protocols"]

    try:
        package_dir.mkdir(parents=True, exist_ok=False)
        for subdir in subdirs:
            (package_dir / subdir).mkdir()

        readme_content = f"# {name}"
        readme_path = package_dir / "README.md"
        readme_path.write_text(readme_content)

        pyproject_content = f"""[project]
name = "{name}"
version = "0.1.0"
description = f"EOS package {name}"
readme = "README.md"
dependencies = [
  "eos",
]
"""
        pyproject_path = package_dir / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        gitignore_path = package_dir / ".gitignore"
        gitignore_path.write_text(_GITIGNORE)

        typer.echo(f"Successfully created package '{name}' in {package_dir}")
    except FileExistsError:
        typer.echo(f"Error: Package '{name}' already exists in {resolved_user_dir}", err=True)
    except Exception as e:
        typer.echo(f"Error creating package: {e!s}", err=True)


@add_app.command(name="lab")
def add_lab(
    package: Annotated[str, typer.Argument(help="Name of the target package")],
    name: Annotated[str, typer.Argument(help="Name of the lab to create")],
    user_dir: Annotated[
        str | None,
        typer.Option("--user-dir", "-u", help="Override user directory (defaults to config.yml or ./user)"),
    ] = None,
    config: Annotated[str, typer.Option("--config", "-c", help="Path to EOS config YAML")] = DEFAULT_CONFIG_PATH,
) -> None:
    """Add a new lab to an existing package."""
    package_dir = _resolve_user_dir(user_dir, config) / package
    _validate_package_exists(package_dir)

    files = {"lab.yml": ""}
    _add_entity(package_dir, "lab", name, files)


@add_app.command(name="device")
def add_device(
    package: Annotated[str, typer.Argument(help="Name of the target package")],
    name: Annotated[str, typer.Argument(help="Name of the device to create")],
    user_dir: Annotated[
        str | None,
        typer.Option("--user-dir", "-u", help="Override user directory (defaults to config.yml or ./user)"),
    ] = None,
    config: Annotated[str, typer.Option("--config", "-c", help="Path to EOS config YAML")] = DEFAULT_CONFIG_PATH,
) -> None:
    """Add a new device to an existing package."""
    package_dir = _resolve_user_dir(user_dir, config) / package
    _validate_package_exists(package_dir)

    files = {"device.yml": "", "device.py": ""}
    _add_entity(package_dir, "device", name, files)


@add_app.command(name="task")
def add_task(
    package: Annotated[str, typer.Argument(help="Name of the target package")],
    name: Annotated[str, typer.Argument(help="Name of the task to create")],
    user_dir: Annotated[
        str | None,
        typer.Option("--user-dir", "-u", help="Override user directory (defaults to config.yml or ./user)"),
    ] = None,
    config: Annotated[str, typer.Option("--config", "-c", help="Path to EOS config YAML")] = DEFAULT_CONFIG_PATH,
) -> None:
    """Add a new task to an existing package."""
    package_dir = _resolve_user_dir(user_dir, config) / package
    _validate_package_exists(package_dir)

    files = {"task.yml": "", "task.py": ""}
    _add_entity(package_dir, "task", name, files)


@add_app.command(name="protocol")
def add_protocol(
    package: Annotated[str, typer.Argument(help="Name of the target package")],
    name: Annotated[str, typer.Argument(help="Name of the protocol to create")],
    user_dir: Annotated[
        str | None,
        typer.Option("--user-dir", "-u", help="Override user directory (defaults to config.yml or ./user)"),
    ] = None,
    config: Annotated[str, typer.Option("--config", "-c", help="Path to EOS config YAML")] = DEFAULT_CONFIG_PATH,
) -> None:
    """Add a new protocol to an existing package."""
    package_dir = _resolve_user_dir(user_dir, config) / package
    _validate_package_exists(package_dir)

    files = {"protocol.yml": "", "optimizer.py": ""}
    _add_entity(package_dir, "protocol", name, files)


@pkg_app.command(
    name="install",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def install_package(
    ctx: typer.Context,
    all_packages: Annotated[bool, typer.Option("--all", "-a", help="Install deps for every package")] = False,
    user_dir: Annotated[
        str | None,
        typer.Option("--user-dir", "-u", help="Override user directory (defaults to config.yml or ./user)"),
    ] = None,
    config: Annotated[str, typer.Option("--config", "-c", help="Path to EOS config YAML")] = DEFAULT_CONFIG_PATH,
) -> None:
    """Install the Python dependencies of one or more EOS user packages via uv.

    Pass one or more package names, or ``--all`` for every discovered package. Any arguments
    starting with ``-`` (and everything after them) are forwarded to ``uv pip install``.
    Example: ``eos pkg install cahoon_lab color_lab --upgrade``.
    """
    # Split raw args: everything up to the first flag is a package name, the rest goes to uv.
    raw = list(ctx.args)
    split = next((i for i, a in enumerate(raw) if a.startswith("-")), len(raw))
    names = raw[:split]
    extra = raw[split:]

    if not names and not all_packages:
        raise typer.BadParameter("Provide one or more package names, or use --all.")
    if names and all_packages:
        raise typer.BadParameter("Cannot combine package names with --all.")

    resolved = _resolve_user_dir(user_dir, config)
    packages = _discover_or_exit(resolved)

    if all_packages:
        if not packages:
            typer.echo(f"No packages found in {resolved}.", err=True)
            raise typer.Exit(1)
        selected = list(packages.values())
    else:
        missing = [n for n in names if n not in packages]
        if missing:
            available = ", ".join(sorted(packages)) or "<none>"
            raise typer.BadParameter(
                f"Package(s) not found in {resolved}: {', '.join(missing)}. Available: {available}"
            )
        selected = [packages[n] for n in names]

    for pkg in selected:
        typer.echo(f"Installing {pkg.name} ({pkg.path})...")
        _run_uv_install(pkg.path / "pyproject.toml", extra)


if __name__ == "__main__":
    pkg_app()
