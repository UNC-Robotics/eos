from datetime import datetime, UTC

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from eos.database.abstract_sql_db_interface import Base


class UserIdentity(BaseModel):
    """What EOS has seen of a user, recorded from their own tokens."""

    sub: str
    email: str | None = None
    name: str | None = None
    first_seen_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserIdentityModel(Base):
    """A user EOS has seen. Lets an instance show and look up users without querying the
    identity provider, which is what keeps it free of a management credential."""

    __tablename__ = "user_identities"

    sub: Mapped[str] = mapped_column(String(255), primary_key=True)

    # Not unique: two subs can share an email across an identity provider migration
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("ix_user_identities_email", "email"),)
