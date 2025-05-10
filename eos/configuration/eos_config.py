from enum import Enum
from pathlib import Path
from pydantic import Field, field_validator, BaseModel, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WebApiConfig(BaseSettings):
    """Web API configuration."""

    host: str = Field("localhost", validation_alias="EOS_WEB_API_HOST")
    port: int = Field(8070, validation_alias="EOS_WEB_API_PORT")

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore", populate_by_name=True)


class DatabaseType(Enum):
    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"


class PostgresDbConfig(BaseSettings):
    """PostgreSQL specific configuration."""

    host: str = Field("localhost", validation_alias="EOS_POSTGRES_HOST")
    port: int = Field(5432, validation_alias="EOS_POSTGRES_PORT")
    name: str = Field("eos", validation_alias="EOS_POSTGRES_DB")
    username: str = Field(..., validation_alias="EOS_POSTGRES_USER")
    password: str = Field(..., validation_alias="EOS_POSTGRES_PASSWORD")

    # Connection pool settings
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore", populate_by_name=True)


class SqliteDbConfig(BaseSettings):
    """SQLite specific configuration."""

    db_dir: Path = Path("./")
    db_name: str = "eos"
    in_memory: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore", populate_by_name=True)


class DbConfig(BaseSettings):
    """Database configuration."""

    type: DatabaseType = DatabaseType.POSTGRESQL
    postgres: PostgresDbConfig | None = None
    sqlite: SqliteDbConfig | None = None

    echo: bool = False

    @model_validator(mode="after")
    def validate_config(self) -> "DbConfig":
        if self.type == DatabaseType.POSTGRESQL:
            if self.postgres is None:
                self.postgres = PostgresDbConfig()
            self.sqlite = None

        elif self.type == DatabaseType.SQLITE:
            if self.sqlite is None:
                self.sqlite = SqliteDbConfig()
            self.postgres = None

        return self

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore", populate_by_name=True)


class FileDbConfig(BaseSettings):
    """File database (object storage) configuration."""

    bucket: str = Field("eos", validation_alias="EOS_MINIO_BUCKET")

    host: str = Field("localhost", validation_alias="EOS_MINIO_HOST")
    port: int = Field(9000, validation_alias="EOS_MINIO_PORT")

    username: str = Field(..., validation_alias="EOS_MINIO_USER")
    password: str = Field(..., validation_alias="EOS_MINIO_PASSWORD")

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore", populate_by_name=True)


class SchedulerType(Enum):
    """The type of scheduler to use for experiment scheduling."""

    GREEDY = "greedy"
    CPSAT = "cpsat"


class SchedulerConfig(BaseModel):
    """Configuration for the scheduler."""

    type: SchedulerType = SchedulerType.GREEDY
    parameters: dict = Field(default_factory=dict)


class OrchestratorHzConfig(BaseModel):
    """Configuration for the orchestrator loop rate."""

    min: float = 0.5
    max: float = 10


class EosConfig(BaseSettings):
    user_dir: Path = Field(default=Path("./user"))
    labs: set[str] = Field(default_factory=set)
    experiments: set[str] = Field(default_factory=set)

    orchestrator_hz: OrchestratorHzConfig = Field(default_factory=OrchestratorHzConfig)
    log_level: str = "INFO"
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    web_api: WebApiConfig = Field(default_factory=WebApiConfig)

    db: DbConfig = Field(default_factory=DbConfig)
    file_db: FileDbConfig = Field(default_factory=FileDbConfig)

    @field_validator("user_dir")
    def _validate_user_dir(cls, user_dir: Path) -> Path:
        if user_dir.name != "user":
            raise ValueError(
                f"EOS requires that the directory containing packages is named 'user'. "
                f"The configured user_dir is currently named '{user_dir.name}', which is invalid."
            )
        return user_dir

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="EOS_", env_ignore_empty=True, extra="ignore", populate_by_name=True
    )
