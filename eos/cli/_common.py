"""Shared helpers for the EOS CLI: config loading, subprocess running, and uniform error handling."""

import functools
import inspect
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypeVar

import click
import typer
import yaml

from eos.configuration.eos_config import EosConfig
from eos.logging.logger import log

DEFAULT_CONFIG_PATH = "./config.yml"

ConfigOption = Annotated[str, typer.Option("--config", "-c", help="Path to EOS config YAML")]
UserDirOption = Annotated[str | None, typer.Option("--user-dir", "-u", help="Override the EOS user directory")]

F = TypeVar("F", bound=Callable[..., object])


def load_config(config_path: str = DEFAULT_CONFIG_PATH) -> EosConfig:
    """Load and validate the EOS configuration file, applying its log level."""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with config_file.open() as f:
        config_data = yaml.safe_load(f) or {}
    eos_config = EosConfig.model_validate(config_data)
    log.set_level(eos_config.log_level)
    return eos_config


def config_callback(ctx: typer.Context, config: ConfigOption = DEFAULT_CONFIG_PATH) -> None:
    """Group callback that loads the EOS config once into ctx.obj and shows help when no subcommand is given."""
    try:
        ctx.obj = load_config(config)
    except Exception as e:
        typer.secho(f"Failed to load configuration: {e}", fg="red", err=True)
        raise typer.Exit(1) from e
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    capture: bool = False,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run a subprocess with text I/O. With check=True, a non-zero exit raises CalledProcessError."""
    return subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True, check=check, env=env)


def cli_command(fail_message: str) -> Callable[[F], F]:
    """Wrap a command so any error becomes a clean '<fail_message>: <error>' and a non-zero exit.

    Control-flow exceptions raised by Typer/Click (Exit, Abort, BadParameter, ...) pass through unchanged.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> object:
            try:
                return fn(*args, **kwargs)
            except (typer.Exit, typer.Abort, click.ClickException):
                raise
            except Exception as e:
                typer.secho(f"{fail_message}: {e}", fg="red", err=True)
                raise typer.Exit(1) from e

        # Preserve the original signature so Typer still sees the command's parameters.
        wrapper.__signature__ = inspect.signature(fn)
        return wrapper  # type: ignore[return-value]

    return decorator
