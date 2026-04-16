import subprocess
from typing import Annotated

import typer

from eos.cli.db_cli import load_config, setup_alembic
from eos.database.alembic_commands import alembic_upgrade

DEFAULT_CONFIG_PATH = "./config.yml"
REQUIRED_BRANCH = "master"


def _run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=capture, text=True)


def _ensure_git_repo() -> None:
    try:
        _run(["git", "rev-parse", "--git-dir"], capture=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        typer.echo("Not inside a git repository (or `git` not installed).", err=True)
        raise typer.Exit(1) from e


def _fetch_master_and_count_behind() -> int:
    """Fetch origin/master and return how many commits local master is behind."""
    typer.echo("Checking for updates...")
    try:
        _run(["git", "fetch", "origin", REQUIRED_BRANCH, "--quiet"])
    except subprocess.CalledProcessError as e:
        typer.echo(f"git fetch failed: {e}", err=True)
        raise typer.Exit(1) from e
    try:
        behind = _run(
            ["git", "rev-list", "--count", f"{REQUIRED_BRANCH}..origin/{REQUIRED_BRANCH}"],
            capture=True,
        ).stdout.strip()
        return int(behind)
    except subprocess.CalledProcessError as e:
        typer.echo(f"Could not compare local '{REQUIRED_BRANCH}' against origin: {e}", err=True)
        raise typer.Exit(1) from e


def _check_pull_preconditions() -> None:
    """Abort if the repo is not on master, is dirty, or has no upstream."""
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True).stdout.strip()
    if branch != REQUIRED_BRANCH:
        typer.echo(
            f"Currently on branch '{branch}'; `eos update` only pulls on '{REQUIRED_BRANCH}'. "
            f"Checkout master or use --skip-pull.",
            err=True,
        )
        raise typer.Exit(1)

    dirty = _run(["git", "status", "--porcelain"], capture=True).stdout.strip()
    if dirty:
        typer.echo(
            "Working tree has uncommitted changes. Commit or stash them first, or use --skip-pull.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        _run(["git", "rev-parse", "--abbrev-ref", "@{upstream}"], capture=True)
    except subprocess.CalledProcessError as e:
        typer.echo(f"Branch '{branch}' has no upstream tracking configured.", err=True)
        raise typer.Exit(1) from e


def _do_pull() -> None:
    typer.echo("Pulling latest changes (git pull --ff-only)...")
    try:
        _run(["git", "pull", "--ff-only"])
    except subprocess.CalledProcessError as e:
        typer.echo("git pull failed (your branch may have diverged from upstream).", err=True)
        raise typer.Exit(1) from e


def _do_sync() -> None:
    typer.echo("Syncing dependencies (uv sync --inexact)...")
    try:
        _run(["uv", "sync", "--inexact"])
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        typer.echo(f"uv sync failed: {e}", err=True)
        raise typer.Exit(1) from e


def _do_migrate(config_path: str) -> None:
    typer.echo("Running database migrations (alembic upgrade head)...")
    try:
        eos_config = load_config(config_path)
        setup_alembic(eos_config)
        alembic_upgrade("head")
    except Exception as e:
        typer.echo(f"Database migration failed: {e}", err=True)
        raise typer.Exit(1) from e


def update(
    skip_pull: Annotated[bool, typer.Option("--skip-pull", help="Skip git pull")] = False,
    skip_sync: Annotated[bool, typer.Option("--skip-sync", help="Skip uv sync")] = False,
    skip_migrate: Annotated[bool, typer.Option("--skip-migrate", help="Skip database migrations")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt")] = False,
    config: Annotated[str, typer.Option("--config", "-c", help="Path to EOS config YAML")] = DEFAULT_CONFIG_PATH,
) -> None:
    """Update EOS: pull master, sync dependencies, and run database migrations.

    User package code in ``user/`` is gitignored and untouched. Dependencies installed via
    ``eos pkg install`` are preserved (``uv sync --inexact``). Each step fails closed — a
    failure in one step stops the rest.
    """
    if not skip_pull:
        _ensure_git_repo()
        behind = _fetch_master_and_count_behind()
        if behind == 0:
            typer.secho("EOS is already up to date.", fg="green")
            raise typer.Exit()
        typer.echo(f"{behind} new commit(s) available on origin/{REQUIRED_BRANCH}.")
        _check_pull_preconditions()

    steps = []
    if not skip_pull:
        steps.append(f"git pull --ff-only on '{REQUIRED_BRANCH}'")
    if not skip_sync:
        steps.append("uv sync --inexact")
    if not skip_migrate:
        steps.append("alembic upgrade head")

    if not steps:
        typer.echo("Nothing to do — all steps skipped.")
        raise typer.Exit()

    typer.echo("Plan:")
    for s in steps:
        typer.echo(f"  - {s}")

    if not yes and not typer.confirm("Proceed?", default=True):
        raise typer.Exit()

    if not skip_pull:
        _do_pull()
    if not skip_sync:
        _do_sync()
    if not skip_migrate:
        _do_migrate(config)

    typer.secho("EOS update complete.", fg="green")
