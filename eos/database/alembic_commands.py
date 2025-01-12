from functools import wraps
from pathlib import Path
from threading import Lock

import eos.database

from alembic.config import Config

ALEMBIC_LOCK = Lock()


def alembic_lock(func) -> callable:
    """Decorator to prevent alembic commands from running concurrently."""

    @wraps(func)
    def wrapper(*args, **kwargs) -> None:
        with ALEMBIC_LOCK:
            return func(*args, **kwargs)

    return wrapper


def alembic_config() -> Config:
    """Create and return an Alembic configuration object for the EOS database."""

    alembic_dir = Path(eos.database.__file__).parent
    alembic_ini_path = alembic_dir / "_migrations" / "alembic.ini"

    if not alembic_ini_path.exists():
        raise ValueError(f"Couldn't find alembic.ini at {alembic_ini_path}")

    return Config(alembic_ini_path)


@alembic_lock
def alembic_upgrade(revision: str = "head") -> None:
    """Run alembic upgrade on the EOS database."""
    import alembic.command

    alembic.command.upgrade(alembic_config(), revision)


@alembic_lock
def alembic_downgrade(revision: str = "-1") -> None:
    """Run alembic downgrade on EOS database."""
    import alembic.command

    alembic.command.downgrade(alembic_config(), revision)


@alembic_lock
def alembic_revision(message: str | None = None, autogenerate: bool = False, **kwargs) -> None:
    """Create a new revision file for the database."""
    import alembic.command

    alembic.command.revision(alembic_config(), message=message, autogenerate=autogenerate, **kwargs)


@alembic_lock
def alembic_stamp(revision: str) -> None:
    """Stamp the revision table with the given revision."""
    import alembic.command

    alembic.command.stamp(alembic_config(), revision=revision)


@alembic_lock
def alembic_current() -> None:
    """Get the current revision of the database."""
    import alembic.command

    alembic_cfg = alembic_config()
    alembic_cfg.print_stdout = lambda *args, **kwargs: None

    alembic.command.current(alembic_cfg)
