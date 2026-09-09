from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, Enum as sa_Enum, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from eos.database.abstract_sql_db_interface import Base


class Role(Enum):
    """Roles assignable in the local EOS instance. All authorization is per-instance."""

    SUPERUSER = "SUPERUSER"
    LAB_ADMIN = "LAB_ADMIN"
    EDITOR = "EDITOR"
    SUBMITTER = "SUBMITTER"
    VIEWER = "VIEWER"


@dataclass(frozen=True)
class AuthenticatedUser:
    """The identity extracted from a validated token. Authorization comes from local roles, not the token."""

    sub: str
    email: str | None = None
    name: str | None = None


class UserRole(BaseModel):
    """A role assignment for a user (identified by Zitadel sub) in this EOS instance."""

    id: int
    sub: str
    role: Role
    lab_name: str | None = None
    granted_by: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserRoleModel(Base):
    """The database model for user role assignments."""

    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    sub: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(sa_Enum(Role), nullable=False)
    lab_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    granted_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("sub", "role", "lab_name", name="uq_user_roles_sub_role_lab"),
        Index("ix_user_roles_sub", "sub"),
    )
