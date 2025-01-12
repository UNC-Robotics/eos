import asyncio
from pathlib import Path
from typing import Annotated
import typer
import yaml
from alembic import command
from alembic.config import Config
from alembic.util import CommandError

from eos.configuration.entities.eos_config import DatabaseType, EosConfig
from eos.database.abstract_sql_db_interface import AbstractSqlDbInterface
from eos.database.postgresql_db_interface import PostgresqlDbInterface
from eos.database.sqlite_db_interface import SqliteDbInterface
from eos.logging.logger import log
from eos.utils.di.di_container import get_di_container

db_app = typer.Typer(help="Database management commands", no_args_is_help=True)


def load_config(config_path: str) -> EosConfig:
    """
    Load and validate the EOS configuration file.

    :param config_path: Path to the configuration YAML file
    :return: Parsed configuration object
    """
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


def setup_alembic(eos_config: EosConfig) -> Config:
    """
    Initialize database interface and create Alembic configuration.

    :param eos_config: Parsed EOS configuration object
    :return: Configured Alembic Config object
    """
    # Initialize database interface
    di = get_di_container()
    db_interface = (
        PostgresqlDbInterface(eos_config.db)
        if eos_config.db.db_type == DatabaseType.POSTGRESQL
        else SqliteDbInterface(eos_config.db)
    )
    di.register(AbstractSqlDbInterface, db_interface)

    # Configure Alembic
    migrations_path = Path(__file__).parent.parent / "database" / "_migrations" / "alembic.ini"
    if not migrations_path.exists():
        raise FileNotFoundError(f"Alembic configuration not found at: {migrations_path}")

    return Config(str(migrations_path))


def handle_db_operation(operation_name: str, operation_func: callable, *args, **kwargs) -> None:
    """
    Execute a database operation.

    :param operation_name: Name of the operation for logging
    :param operation_func: Alembic command function to execute
    :param args: Positional arguments for the operation
    :param kwargs: Keyword arguments for the operation
    """
    try:
        operation_func(*args, **kwargs)
    except CommandError as e:
        log.error(f"Alembic command error during {operation_name}: {e}")
        raise typer.Exit(1) from e
    except Exception as e:
        log.error(f"Unexpected error during {operation_name}: {e}")
        raise typer.Exit(1) from e


# Common option for config file path
ConfigOption = Annotated[
    str,
    typer.Option(
        "--config",
        "-c",
        help="Path to config.yml",
        show_default=True,
    ),
]


@db_app.command()
def migrate(
    message: Annotated[str, typer.Argument(help="Migration message")],
    config: ConfigOption = "./config.yml",
    autogenerate: Annotated[bool, typer.Option(help="Enable autogeneration")] = True,
) -> None:
    """
    Create a new database migration.

    This command performs the following steps:

    1. Loads the configuration
    2. Initializes the database connection
    3. Creates a new migration file with the provided message

    :param message: Description of the migration changes
    :param config: Path to configuration file
    :param autogenerate: Whether to detect schema changes automatically
    """
    try:
        eos_config = load_config(config)
        alembic_cfg = setup_alembic(eos_config)

        # Ensure database is up to date before creating new migration
        handle_db_operation("upgrade to head", command.upgrade, alembic_cfg, "head")

        handle_db_operation("migration creation", command.revision, alembic_cfg, message, autogenerate=autogenerate)

        typer.echo(f"Created new migration: {message}")
    except Exception as e:
        typer.echo(f"Failed to create migration: {e}", err=True)
        raise typer.Exit(1) from e


@db_app.command()
def upgrade(
    config: ConfigOption = "./config.yml",
    revision: Annotated[str, typer.Option(help="Target revision (default: head)")] = "head",
) -> None:
    """
    Upgrade database to specified revision.

    :param config: Path to configuration file
    :param revision: Target revision identifier
    """
    try:
        alembic_cfg = setup_alembic(load_config(config))
        handle_db_operation("database upgrade", command.upgrade, alembic_cfg, revision)
        typer.echo(f"Successfully upgraded database to: {revision}")
    except Exception as e:
        typer.echo(f"Failed to upgrade database: {e}", err=True)
        raise typer.Exit(1) from e


@db_app.command()
def downgrade(
    config: ConfigOption = "./config.yml",
    revision: Annotated[str, typer.Option(help="Target revision (default: -1)")] = "-1",
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation prompt")] = False,
) -> None:
    """
    Downgrade database to specified revision.

    :param config: Path to configuration file
    :param revision: Target revision identifier
    :param force: Skip confirmation prompt if True
    """
    if not force:
        confirmed = typer.confirm(
            f"Are you sure you want to downgrade the database to revision {revision}?", abort=True
        )
        if not confirmed:
            return

    try:
        alembic_cfg = setup_alembic(load_config(config))
        handle_db_operation("database downgrade", command.downgrade, alembic_cfg, revision)
        typer.echo(f"Successfully downgraded database to: {revision}")
    except Exception as e:
        typer.echo(f"Failed to downgrade database: {e}", err=True)
        raise typer.Exit(1) from e


@db_app.command()
def history(
    config: ConfigOption = "./config.yml",
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show detailed history")] = False,
) -> None:
    """
    Show migration history.

    :param config: Path to configuration file
    :param verbose: Show detailed history if True
    """
    try:
        alembic_cfg = setup_alembic(load_config(config))
        if verbose:
            alembic_cfg.print_stdout = True
        handle_db_operation("show history", command.history, alembic_cfg)
    except Exception as e:
        typer.echo(f"Failed to show history: {e}", err=True)
        raise typer.Exit(1) from e


@db_app.command()
def current(config: ConfigOption = "./config.yml") -> None:
    """
    Show current revision.

    :param config: Path to configuration file
    :raises typer.Exit: If current revision display fails
    """
    try:
        alembic_cfg = setup_alembic(load_config(config))
        handle_db_operation("show current revision", command.current, alembic_cfg)
    except Exception as e:
        typer.echo(f"Failed to show current revision: {e}", err=True)
        raise typer.Exit(1) from e


@db_app.command()
def clear(
    config: ConfigOption = "./config.yml",
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation prompt")] = False,
) -> None:
    """
    Clear all data from database tables while preserving the schema.

    :param config: Path to configuration file
    :param force: Skip confirmation prompt if True
    """
    if not force:
        confirmed = typer.confirm(
            "WARNING: This will delete all data in the database tables. The database structure will be preserved. "
            "Are you sure?",
            abort=True,
        )
        if not confirmed:
            return

    try:
        # Setup database interface
        eos_config = load_config(config)
        db_interface = (
            PostgresqlDbInterface(eos_config.db)
            if eos_config.db.db_type == DatabaseType.POSTGRESQL
            else SqliteDbInterface(eos_config.db)
        )

        # Clear all tables
        asyncio.run(db_interface.clear_db())
        typer.echo("Successfully cleared all data from database tables")
    except Exception as e:
        typer.echo(f"Failed to clear database: {e}", err=True)
        raise typer.Exit(1) from e
