from pathlib import Path
from typing import Annotated

import typer

from eos.cli._common import run

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"

services_app = typer.Typer(
    help="Manage infrastructure services",
    no_args_is_help=True,
)


def _auth_enabled() -> bool:
    """Whether the Zitadel auth services are active, per EOS_AUTH_ENABLED in .env."""
    if not ENV_PATH.exists():
        return False
    for line in ENV_PATH.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key == "EOS_AUTH_ENABLED":
            return value.strip().lower() == "true"
    return False


def _compose(*args: str, auth: bool | None = None) -> None:
    """Run `docker compose` from the repo root, adding the auth profile when enabled."""
    include_auth = _auth_enabled() if auth is None else auth
    profile = ["--profile", "auth"] if include_auth else []
    try:
        result = run(["docker", "compose", *profile, *args], cwd=REPO_ROOT, check=False)
    except FileNotFoundError:
        typer.echo("Error: docker not found on PATH.", err=True)
        raise typer.Exit(1) from None
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


@services_app.command(name="up")
def services_up(
    auth: Annotated[
        bool | None,
        typer.Option("--auth/--no-auth", help="Include the Zitadel auth services (default: from EOS_AUTH_ENABLED)"),
    ] = None,
) -> None:
    """Start the infrastructure services in the background."""
    _compose("up", "-d", auth=auth)


@services_app.command(name="down")
def services_down(
    volumes: Annotated[
        bool, typer.Option("--volumes", "-v", help="Also remove data volumes (permanently deletes data)")
    ] = False,
) -> None:
    """Stop and remove the infrastructure services."""
    _compose("down", *(["--volumes"] if volumes else []))


@services_app.command(name="restart")
def services_restart(
    service: Annotated[str | None, typer.Argument(help="Service to restart (default: all)")] = None,
) -> None:
    """Restart the infrastructure services."""
    _compose("restart", *([service] if service else []))


@services_app.command(name="logs")
def services_logs(
    service: Annotated[str | None, typer.Argument(help="Service to show logs for (default: all)")] = None,
    follow: Annotated[bool, typer.Option("--follow/--no-follow", "-f", help="Follow log output")] = True,
) -> None:
    """Show logs from the infrastructure services."""
    _compose("logs", *(["-f"] if follow else []), *([service] if service else []))


@services_app.command(name="ps")
def services_ps() -> None:
    """List the infrastructure services and their status."""
    _compose("ps")
