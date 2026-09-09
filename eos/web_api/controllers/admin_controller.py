from typing import ClassVar

from litestar import delete, get, post, Controller
from pydantic import BaseModel, model_validator
from sqlalchemy import delete as sa_delete, select

from eos.auth.authorization import require_superuser
from eos.auth.entities.user_role import AuthenticatedUser, Role, UserRole, UserRoleModel
from eos.database.abstract_sql_db_interface import AsyncDbSession
from eos.web_api.exception_handling import APIError


class AssignRoleRequest(BaseModel):
    sub: str
    role: Role
    lab_name: str | None = None

    @model_validator(mode="after")
    def validate_lab_scope(self) -> "AssignRoleRequest":
        if (self.role == Role.LAB_ADMIN) != (self.lab_name is not None):
            raise ValueError("lab_name is required for the lab_admin role and not allowed for other roles")
        return self


class AdminController(Controller):
    """Controller for administration endpoints (role assignments)."""

    path = "/admin"
    guards: ClassVar = [require_superuser()]

    @get("/roles")
    async def list_roles(self, db: AsyncDbSession, sub: str | None = None) -> list[UserRole]:
        """List role assignments, optionally filtered by user sub."""
        query = select(UserRoleModel)
        if sub:
            query = query.where(UserRoleModel.sub == sub)
        result = await db.execute(query)
        return [UserRole.model_validate(role) for role in result.scalars().all()]

    @post("/roles")
    async def assign_role(self, data: AssignRoleRequest, db: AsyncDbSession, user: AuthenticatedUser) -> UserRole:
        """Assign a role to a user."""
        existing = await db.execute(
            select(UserRoleModel).where(
                UserRoleModel.sub == data.sub,
                UserRoleModel.role == data.role,
                UserRoleModel.lab_name == data.lab_name,
            )
        )
        if existing.scalar_one_or_none():
            raise APIError(status_code=409, detail="Role is already assigned")

        role = UserRoleModel(sub=data.sub, role=data.role, lab_name=data.lab_name, granted_by=user.sub)
        db.add(role)
        await db.commit()
        return UserRole.model_validate(role)

    @delete("/roles/{role_id:int}")
    async def revoke_role(self, role_id: int, db: AsyncDbSession) -> None:
        """Revoke a role assignment."""
        await db.execute(sa_delete(UserRoleModel).where(UserRoleModel.id == role_id))
        await db.commit()
