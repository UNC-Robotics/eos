import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from typer import Context

from eos.configuration.eos_config import EosConfig, DatabaseType
from eos.logging.logger import log
from eos.utils.di.di_container import get_di_container
from eos.database.abstract_sql_db_interface import AbstractSqlDbInterface
from eos.database.postgresql_db_interface import PostgresqlDbInterface
from eos.database.sqlite_db_interface import SqliteDbInterface
from eos.database.alembic_commands import (
    alembic_upgrade,
    alembic_downgrade,
    alembic_revision,
)

if TYPE_CHECKING:
    from alembic.config import Config

db_app = typer.Typer(help="Database management commands", no_args_is_help=True)


def load_config(config_path: str) -> EosConfig:
    """
    Load and validate the EOS configuration file.
    """
    import yaml

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with config_file.open() as f:
            config_data = yaml.safe_load(f) or {}
            eos_config = EosConfig.model_validate(config_data)
            log.set_level(eos_config.log_level)
            return eos_config
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Invalid YAML in config file: {e}") from e
    except ValueError as e:
        raise ValueError(f"Invalid configuration: {e}") from e


def setup_alembic(eos_config: EosConfig) -> "Config":
    """
    Initialize database interface and register it for Alembic.
    """
    from alembic.config import Config

    di = get_di_container()
    db_interface = (
        PostgresqlDbInterface(eos_config.db)
        if eos_config.db.type == DatabaseType.POSTGRESQL
        else SqliteDbInterface(eos_config.db)
    )
    di.register(AbstractSqlDbInterface, db_interface)

    migrations_path = Path(__file__).parent.parent / "database" / "_migrations" / "alembic.ini"
    if not migrations_path.exists():
        raise FileNotFoundError(f"Alembic configuration not found at: {migrations_path}")

    return Config(str(migrations_path))


@db_app.command("init")
def initialize_database(ctx: Context) -> None:
    """
    Initialize database and create all tables.
    """
    eos_config: EosConfig = ctx.obj

    try:
        di = get_di_container()
        db_interface = (
            PostgresqlDbInterface(eos_config.db)
            if eos_config.db.type == DatabaseType.POSTGRESQL
            else SqliteDbInterface(eos_config.db)
        )
        di.register(AbstractSqlDbInterface, db_interface)

        asyncio.run(db_interface.initialize_database())

        alembic_upgrade("head")

        typer.secho("Database initialized successfully", fg="green")
    except Exception as e:
        typer.secho(f"Failed to initialize database: {e}", fg="red", err=True)
        raise typer.Exit(1) from e


@db_app.callback(invoke_without_command=True)
def _global(
    ctx: Context,
    config: str = typer.Option("./config.yml", "--config", "-c", help="Path to EOS config YAML"),
) -> None:
    """
    Load EOS config once and set up logging.
    """
    try:
        eos_config = load_config(config)
    except Exception as e:
        typer.secho(f"Failed to load configuration: {e}", fg="red", err=True)
        raise typer.Exit(1) from e

    ctx.obj = eos_config
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@db_app.command()
def migrate(
    ctx: Context,
    message: str = typer.Argument(..., help="Migration message"),
    autogenerate: bool = typer.Option(True, "--autogenerate", "-a", help="Detect schema changes automatically"),
) -> None:
    """
    Create a new database migration.
    """
    eos_config: EosConfig = ctx.obj
    try:
        setup_alembic(eos_config)
        alembic_upgrade("head")
        alembic_revision(message=message, autogenerate=autogenerate)
        typer.secho(f"Created new migration: {message}", fg="green")
    except Exception as e:
        typer.secho(f"Failed to create migration: {e}", fg="red", err=True)
        raise typer.Exit(1) from e


@db_app.command()
def upgrade(
    ctx: Context,
    revision: str = typer.Option("head", "--revision", "-r", help="Target revision (default: head)"),
) -> None:
    """
    Upgrade database to specified revision.
    """
    eos_config: EosConfig = ctx.obj
    try:
        setup_alembic(eos_config)
        alembic_upgrade(revision)
        typer.secho(f"Successfully upgraded to: {revision}", fg="green")
    except Exception as e:
        typer.secho(f"Failed to upgrade database: {e}", fg="red", err=True)
        raise typer.Exit(1) from e


@db_app.command()
def downgrade(
    ctx: Context,
    revision: str = typer.Option("-1", "--revision", "-r", help="Target revision (default: -1)"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        "--yes",
        help="Skip confirmation prompt (yes/force)",
    ),
) -> None:
    """
    Downgrade database to specified revision.
    """
    if not force and not typer.confirm(f"Downgrade to {revision}?"):
        raise typer.Exit()

    eos_config: EosConfig = ctx.obj
    try:
        setup_alembic(eos_config)
        alembic_downgrade(revision)
        typer.secho(f"Successfully downgraded to: {revision}", fg="green")
    except Exception as e:
        typer.secho(f"Failed to downgrade database: {e}", fg="red", err=True)
        raise typer.Exit(1) from e


@db_app.command()
def history(ctx: Context) -> None:
    """
    Show migration history.
    """
    from alembic import command

    eos_config: EosConfig = ctx.obj
    try:
        cfg = setup_alembic(eos_config)
        command.history(cfg)
    except Exception as e:
        typer.secho(f"Failed to show history: {e}", fg="red", err=True)
        raise typer.Exit(1) from e


@db_app.command()
def current(ctx: Context) -> None:
    """
    Show current revision.
    """
    from alembic import command

    eos_config: EosConfig = ctx.obj
    try:
        cfg = setup_alembic(eos_config)
        command.current(cfg)
    except Exception as e:
        typer.secho(f"Failed to show current revision: {e}", fg="red", err=True)
        raise typer.Exit(1) from e


@db_app.command()
def clear(
    ctx: Context,
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        "--yes",
        help="Skip confirmation prompt (yes/force)",
    ),
) -> None:
    """
    Clear all data from database tables while preserving schema.
    """
    # ruff: noqa: F401
    import eos.database.models

    if not force and not typer.confirm("WARNING: this will delete *all* data but keep the schema - continue?"):
        raise typer.Exit()

    eos_config: EosConfig = ctx.obj
    db_interface: AbstractSqlDbInterface = (
        PostgresqlDbInterface(eos_config.db)
        if eos_config.db.type == DatabaseType.POSTGRESQL
        else SqliteDbInterface(eos_config.db)
    )

    try:
        asyncio.run(db_interface.clear_db())
        typer.secho("Cleared all data from database tables", fg="green")
    except Exception as e:
        typer.secho(f"Failed to clear database: {e}", fg="red", err=True)
        raise typer.Exit(1) from e


@db_app.command("check")
def check_connection(ctx: Context) -> None:
    """
    Test database connectivity.
    """
    eos_config: EosConfig = ctx.obj
    db_interface: AbstractSqlDbInterface = (
        PostgresqlDbInterface(eos_config.db)
        if eos_config.db.type == DatabaseType.POSTGRESQL
        else SqliteDbInterface(eos_config.db)
    )

    ok = asyncio.run(db_interface.check_connection())
    if ok:
        typer.secho("Database connection OK", fg="green")
    else:
        typer.secho("Database connection FAILED", fg="red", err=True)
        raise typer.Exit(1)
