from pathlib import Path
from typing import Annotated, Literal
import typer

pkg_app = typer.Typer()
add_app = typer.Typer()
pkg_app.add_typer(add_app, name="add", help="Add entities to an existing package")

EntityType = Literal["lab", "device", "task", "experiment"]


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
        str, typer.Option("--user-dir", "-u", help="The directory containing EOS user configurations")
    ] = "./user",
) -> None:
    """Create a new package with the specified name in the user directory."""
    package_dir = Path(user_dir) / name
    subdirs = ["devices", "tasks", "labs", "experiments"]

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

        typer.echo(f"Successfully created package '{name}' in {package_dir}")
    except FileExistsError:
        typer.echo(f"Error: Package '{name}' already exists in {user_dir}", err=True)
    except Exception as e:
        typer.echo(f"Error creating package: {e!s}", err=True)


@add_app.command(name="lab")
def add_lab(
    package: Annotated[str, typer.Argument(help="Name of the target package")],
    name: Annotated[str, typer.Argument(help="Name of the lab to create")],
    user_dir: Annotated[
        str, typer.Option("--user-dir", "-u", help="The directory containing EOS user configurations")
    ] = "./user",
) -> None:
    """Add a new lab to an existing package."""
    package_dir = Path(user_dir) / package
    _validate_package_exists(package_dir)

    files = {"lab.yml": ""}
    _add_entity(package_dir, "lab", name, files)


@add_app.command(name="device")
def add_device(
    package: Annotated[str, typer.Argument(help="Name of the target package")],
    name: Annotated[str, typer.Argument(help="Name of the device to create")],
    user_dir: Annotated[
        str, typer.Option("--user-dir", "-u", help="The directory containing EOS user configurations")
    ] = "./user",
) -> None:
    """Add a new device to an existing package."""
    package_dir = Path(user_dir) / package
    _validate_package_exists(package_dir)

    files = {"device.yml": "", "device.py": ""}
    _add_entity(package_dir, "device", name, files)


@add_app.command(name="task")
def add_task(
    package: Annotated[str, typer.Argument(help="Name of the target package")],
    name: Annotated[str, typer.Argument(help="Name of the task to create")],
    user_dir: Annotated[
        str, typer.Option("--user-dir", "-u", help="The directory containing EOS user configurations")
    ] = "./user",
) -> None:
    """Add a new task to an existing package."""
    package_dir = Path(user_dir) / package
    _validate_package_exists(package_dir)

    files = {"task.yml": "", "task.py": ""}
    _add_entity(package_dir, "task", name, files)


@add_app.command(name="experiment")
def add_experiment(
    package: Annotated[str, typer.Argument(help="Name of the target package")],
    name: Annotated[str, typer.Argument(help="Name of the experiment to create")],
    user_dir: Annotated[
        str, typer.Option("--user-dir", "-u", help="The directory containing EOS user configurations")
    ] = "./user",
) -> None:
    """Add a new experiment to an existing package."""
    package_dir = Path(user_dir) / package
    _validate_package_exists(package_dir)

    files = {"experiment.yml": "", "optimizer.py": ""}
    _add_entity(package_dir, "experiment", name, files)


if __name__ == "__main__":
    pkg_app()
