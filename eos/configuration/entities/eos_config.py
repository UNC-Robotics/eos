from pydantic import BaseModel, Field, field_validator
from pathlib import Path


class WebApiConfig(BaseModel):
    host: str = "localhost"
    port: int = 8070


class DbConfig(BaseModel):
    host: str = "localhost"
    port: int
    username: str | None = None
    password: str | None = None


class EosConfig(BaseModel):
    user_dir: Path = Field(default=Path("./user"))
    labs: set[str] = Field(default_factory=set)
    experiments: set[str] = Field(default_factory=set)

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
