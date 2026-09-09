from datetime import datetime, UTC

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from eos.database.abstract_sql_db_interface import Base


class ApiToken(BaseModel):
    """An API token a user created for REST API access. Never carries the secret."""

    id: int
    owner_sub: str
    label: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CreatedApiToken(ApiToken):
    """A freshly created token. The secret is revealed here once and never stored."""

    token: str


class ApiTokenModel(Base):
    """A user's API token. EOS issues the secret and stores only its hash."""

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    owner_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("ix_api_tokens_owner_sub", "owner_sub"),
        Index("uq_api_tokens_token_hash", "token_hash", unique=True),
    )
