import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from typer import Context

from eos.cli._common import cli_command, config_callback
from eos.configuration.eos_config import EosConfig, DatabaseType
from eos.utils.di.di_container import get_di_container
from eos.database.abstract_sql_db_interface import AbstractSqlDbInterface
from eos.database.postgresql_db_interface import PostgresqlDbInterface
from eos.database.sqlite_db_interface import SqliteDbInterface
from eos.database.alembic_commands import (
    alembic_upgrade,
    alembic_downgrade,
    alembic_revision,
    alembic_stamp,
)

if TYPE_CHECKING:
    from alembic.config import Config

db_app = typer.Typer(help="Manage the EOS database", no_args_is_help=True)

# Load the config once into ctx.obj for every db subcommand.
db_app.callback(invoke_without_command=True)(config_callback)

ConfirmOption = typer.Option(False, "--force", "-f", "--yes", help="Skip the confirmation prompt")


def create_db_interface(eos_config: EosConfig) -> AbstractSqlDbInterface:
    """Build the configured SQL database interface."""
    return (
        PostgresqlDbInterface(eos_config.db)
        if eos_config.db.type == DatabaseType.POSTGRESQL
        else SqliteDbInterface(eos_config.db)
    )


def initialize_database_core(eos_config: EosConfig) -> None:
    """Create the database and tables and run migrations. Shared by 'db init' and 'eos setup'."""
    di = get_di_container()
    db_interface = create_db_interface(eos_config)
    di.register(AbstractSqlDbInterface, db_interface)
    asyncio.run(db_interface.initialize_database())
    alembic_upgrade("head")


def setup_alembic(eos_config: EosConfig) -> "Config":
    """Register the database interface for Alembic and return its config."""
    from alembic.config import Config

    di = get_di_container()
    di.register(AbstractSqlDbInterface, create_db_interface(eos_config))

    migrations_path = Path(__file__).parent.parent / "database" / "_migrations" / "alembic.ini"
    if not migrations_path.exists():
        raise FileNotFoundError(f"Alembic configuration not found at: {migrations_path}")

    return Config(str(migrations_path))


@db_app.command("init")
@cli_command("Failed to initialize database")
def initialize_database(ctx: Context) -> None:
    """Initialize the database and create all tables."""
    initialize_database_core(ctx.obj)
    typer.secho("Database initialized successfully", fg="green")


@db_app.command()
@cli_command("Failed to create migration")
def migrate(
    ctx: Context,
    message: str = typer.Argument(..., help="Migration message"),
    autogenerate: bool = typer.Option(True, "--autogenerate", "-a", help="Detect schema changes automatically"),
) -> None:
    """Create a new database migration."""
    setup_alembic(ctx.obj)
    alembic_upgrade("head")
    alembic_revision(message=message, autogenerate=autogenerate)
    typer.secho(f"Created new migration: {message}", fg="green")


@db_app.command()
@cli_command("Failed to upgrade database")
def upgrade(
    ctx: Context,
    revision: str = typer.Option("head", "--revision", "-r", help="Target revision (default: head)"),
) -> None:
    """Upgrade the database to the given revision."""
    setup_alembic(ctx.obj)
    alembic_upgrade(revision)
    typer.secho(f"Successfully upgraded to: {revision}", fg="green")


@db_app.command()
@cli_command("Failed to downgrade database")
def downgrade(
    ctx: Context,
    revision: str = typer.Option("-1", "--revision", "-r", help="Target revision (default: -1)"),
    force: bool = ConfirmOption,
) -> None:
    """Downgrade the database to the given revision."""
    if not force and not typer.confirm(f"Downgrade to {revision}?"):
        raise typer.Exit()
    setup_alembic(ctx.obj)
    alembic_downgrade(revision)
    typer.secho(f"Successfully downgraded to: {revision}", fg="green")


@db_app.command()
@cli_command("Failed to show history")
def history(ctx: Context) -> None:
    """Show the migration history."""
    from alembic import command

    command.history(setup_alembic(ctx.obj))


@db_app.command()
@cli_command("Failed to show current revision")
def current(ctx: Context) -> None:
    """Show the current revision."""
    from alembic import command

    command.current(setup_alembic(ctx.obj))


@db_app.command()
@cli_command("Failed to clear database")
def clear(ctx: Context, force: bool = ConfirmOption) -> None:
    """Clear all data from the database tables while preserving the schema."""
    import eos.database.models  # noqa: F401  (register models before clearing)

    if not force and not typer.confirm("WARNING: this will delete *all* data but keep the schema - continue?"):
        raise typer.Exit()
    asyncio.run(create_db_interface(ctx.obj).clear_db())
    typer.secho("Cleared all data from database tables", fg="green")


@db_app.command()
@cli_command("Failed to stamp database")
def stamp(
    ctx: Context,
    revision: str = typer.Argument(..., help="Target revision to stamp (e.g. 'head', revision hash)"),
    force: bool = ConfirmOption,
) -> None:
    """Stamp the database with a revision without running migrations."""
    if not force and not typer.confirm(f"Stamp database to {revision}?"):
        raise typer.Exit()
    setup_alembic(ctx.obj)
    alembic_stamp(revision)
    typer.secho(f"Successfully stamped to: {revision}", fg="green")


@db_app.command("check")
@cli_command("Failed to check database connection")
def check_connection(ctx: Context) -> None:
    """Test database connectivity."""
    if asyncio.run(create_db_interface(ctx.obj).check_connection()):
        typer.secho("Database connection OK", fg="green")
    else:
        typer.secho("Database connection FAILED", fg="red", err=True)
        raise typer.Exit(1)
