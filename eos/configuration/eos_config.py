from enum import Enum
from pathlib import Path
from pydantic import Field, field_validator, BaseModel, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WebApiConfig(BaseSettings):
    """Web API configuration."""

    host: str = Field("localhost", validation_alias="EOS_WEB_API_HOST")
    port: int = Field(8070, validation_alias="EOS_WEB_API_PORT")
    cors_origins: list[str] = Field(default_factory=lambda: ["*"], validation_alias="EOS_WEB_API_CORS_ORIGINS")

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore", populate_by_name=True)


class AccountProvider(Enum):
    """Who owns the accounts in the identity provider."""

    # EOS owns the identity provider's organization and may manage accounts in it
    SELF_HOSTED = "self_hosted"
    # A shared identity provider owned by someone else, so EOS holds no management credential
    EXTERNAL = "external"


class AuthConfig(BaseSettings):
    """Authentication and authorization configuration (OIDC)."""

    enabled: bool = Field(False, validation_alias="EOS_AUTH_ENABLED")
    provider: AccountProvider = Field(AccountProvider.SELF_HOSTED, validation_alias="EOS_AUTH_PROVIDER")
    issuer: str | None = Field(None, validation_alias="EOS_AUTH_ISSUER")

    # Accepted token audiences, defaulting to the Zitadel project ID
    audiences: list[str] = Field(default_factory=list, validation_alias="EOS_AUTH_AUDIENCES")

    # Account management via the 'eos auth' CLI, for the self_hosted provider only
    org_id: str | None = Field(None, validation_alias="EOS_AUTH_ORG_ID")
    project_id: str | None = Field(None, validation_alias="EOS_AUTH_PROJECT_ID")
    service_user_pat: str | None = Field(None, validation_alias="EOS_AUTH_PAT")

    # Credentials of an API app, used to introspect opaque tokens issued by the provider
    introspection_client_id: str | None = Field(None, validation_alias="EOS_AUTH_INTROSPECTION_CLIENT_ID")
    introspection_client_secret: str | None = Field(None, validation_alias="EOS_AUTH_INTROSPECTION_CLIENT_SECRET")

    # CA bundle for verifying the issuer's TLS, e.g. an internal CA root; None uses the system trust store
    ca_bundle: str | None = Field(None, validation_alias="EOS_AUTH_CA_BUNDLE")

    jwks_cache_ttl: int = 300
    introspection_cache_ttl: int = 60
    leeway_seconds: int = 30

    @property
    def can_manage_accounts(self) -> bool:
        """True when EOS owns the provider's accounts and may create or disable them."""
        return self.enabled and self.provider is AccountProvider.SELF_HOSTED

    @model_validator(mode="after")
    def validate_config(self) -> "AuthConfig":
        if not self.audiences and self.project_id:
            self.audiences = [self.project_id]
        if not self.enabled:
            return self
        if not self.issuer:
            raise ValueError("auth.issuer is required when auth is enabled")
        if not self.audiences:
            raise ValueError("auth.audiences or auth.project_id is required when auth is enabled")
        if self.provider is AccountProvider.EXTERNAL and (self.service_user_pat or self.org_id):
            raise ValueError(
                "Remove EOS_AUTH_PAT and EOS_AUTH_ORG_ID from .env. The external provider manages its own accounts."
            )
        return self

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
    connect_timeout: int = 10

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
    """File database (S3-compatible object storage) configuration."""

    bucket: str = Field("eos", validation_alias="EOS_S3_BUCKET")
    endpoint_url: str | None = Field(None, validation_alias="EOS_S3_ENDPOINT_URL")
    access_key_id: str = Field(..., validation_alias="EOS_S3_ACCESS_KEY_ID")
    secret_access_key: str = Field(..., validation_alias="EOS_S3_SECRET_ACCESS_KEY")
    region_name: str = Field("us-east-1", validation_alias="EOS_S3_REGION")
    connect_timeout: int = Field(10, validation_alias="EOS_S3_CONNECT_TIMEOUT")
    read_timeout: int = Field(30, validation_alias="EOS_S3_READ_TIMEOUT")

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore", populate_by_name=True)


class SchedulerType(Enum):
    """The type of scheduler to use for protocol run scheduling."""

    GREEDY = "greedy"
    CPSAT = "cpsat"


class SchedulerConfig(BaseModel):
    """Configuration for the scheduler."""

    type: SchedulerType = SchedulerType.GREEDY
    parameters: dict = Field(default_factory=dict)


class OrchestratorHzConfig(BaseModel):
    """Configuration for the orchestrator loop rate."""

    rate: float = 10
    maintenance_interval: float = 60.0


class EosConfig(BaseSettings):
    user_dir: Path = Field(default=Path("./user"))
    packages: set[str] = Field(default_factory=set)
    labs: set[str] = Field(default_factory=set)
    protocols: set[str] = Field(default_factory=set)

    orchestrator_hz: OrchestratorHzConfig = Field(default_factory=OrchestratorHzConfig)
    log_level: str = "INFO"
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    web_api: WebApiConfig = Field(default_factory=WebApiConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)

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
