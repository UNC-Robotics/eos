from enum import Enum

from pydantic import BaseModel, Field, field_validator
from pathlib import Path


class WebApiConfig(BaseModel):
    host: str = "localhost"
    port: int = 8070


class DatabaseType(Enum):
    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"


class DbConfig(BaseModel):
    db_type: DatabaseType = DatabaseType.POSTGRESQL

    db_name: str = "eos"

    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None

    echo: bool = False

    # PostgreSQL specific
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 60

    # SQLite specific
    sqlite_db_dir: Path = Field(default=Path("./"))
    sqlite_in_memory: bool = False


class EosConfig(BaseModel):
    user_dir: Path = Field(default=Path("./user"))
    labs: set[str] = Field(default_factory=set)
    experiments: set[str] = Field(default_factory=set)

    orchestrator_min_hz: float = 0.5
    orchestrator_max_hz: float = 15

    log_level: str = "INFO"

    web_api: WebApiConfig = Field(default_factory=WebApiConfig)
    db: DbConfig = Field(default_factory=lambda: DbConfig(port=27017))
    file_db: DbConfig = Field(default_factory=lambda: DbConfig(port=9004))

    @field_validator("user_dir")
    def _validate_user_dir(cls, user_dir: Path) -> Path:
        if not user_dir.name == "user":
            raise ValueError(
                f"EOS requires that the directory containing packages is named 'user'. The configured user_dir is "
                f"currently named '{user_dir.name}', which is invalid."
            )
        return user_dir

    class Config:
        validate_assignment = True
