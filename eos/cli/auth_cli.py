import asyncio
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import delete as sa_delete, func, or_, select
from typer import Context

from eos.auth.entities.user_identity import UserIdentityModel
from eos.auth.entities.user_role import Role, UserRoleModel
from eos.auth.zitadel_client import ZitadelClient, generate_complexity_password
from eos.cli._common import cli_command, config_callback
from eos.cli.db_cli import create_db_interface

if TYPE_CHECKING:
    from eos.configuration.eos_config import EosConfig

auth_app = typer.Typer(help="Manage accounts and roles", no_args_is_help=True)
console = Console()

CLI_GRANTED_BY = "cli"

# Load the config once into ctx.obj for every auth subcommand.
auth_app.callback(invoke_without_command=True)(config_callback)


def _parse_role(role: str) -> Role:
    try:
        return Role(role.upper())
    except ValueError as e:
        valid = ", ".join(r.value.lower() for r in Role)
        typer.secho(f"Invalid role '{role}'. Valid roles: {valid}", fg="red", err=True)
        raise typer.Exit(1) from e


async def _insert_role(eos_config: "EosConfig", sub: str, role: Role, lab: str | None) -> bool:
    """Insert a role assignment for a user in this instance. Returns False if it already exists."""
    async with create_db_interface(eos_config).get_async_session() as db:
        existing = await db.execute(
            select(UserRoleModel).where(
                UserRoleModel.sub == sub, UserRoleModel.role == role, UserRoleModel.lab_name == lab
            )
        )
        if existing.scalar_one_or_none():
            return False
        db.add(UserRoleModel(sub=sub, role=role, lab_name=lab, granted_by=CLI_GRANTED_BY))
        return True


def _match_user_id(users: list[dict], identifier: str) -> str:
    """Find a user's Zitadel ID by username, email, or ID among already-fetched users. Exits if no match."""
    wanted = identifier.lower()
    for user in users:
        email = user.get("human", {}).get("email", {}).get("email", "")
        if identifier == user.get("userId") or wanted in (user.get("username", "").lower(), email.lower()):
            return user["userId"]
    typer.secho(
        f"No user found matching '{identifier}'. Run 'eos auth list-users' to see accounts.", fg="red", err=True
    )
    raise typer.Exit(1)


async def _find_identities(eos_config: "EosConfig", identifier: str) -> list[UserIdentityModel]:
    """Find users EOS has already seen, matching a sub, email, or name."""
    wanted = identifier.strip().lower()
    async with create_db_interface(eos_config).get_async_session() as db:
        result = await db.execute(
            select(UserIdentityModel).where(
                or_(
                    UserIdentityModel.sub == identifier,
                    func.lower(UserIdentityModel.email) == wanted,
                    func.lower(UserIdentityModel.name) == wanted,
                )
            )
        )
        return list(result.scalars().all())


async def _identity_names(eos_config: "EosConfig") -> dict[str, str]:
    """Map each known sub to something readable."""
    async with create_db_interface(eos_config).get_async_session() as db:
        result = await db.execute(select(UserIdentityModel))
        return {identity.sub: identity.email or identity.name or "" for identity in result.scalars().all()}


def _resolve_sub(eos_config: "EosConfig", identifier: str) -> str:
    """Resolve a sub, email, or name to a user's sub. Prefers users EOS has already seen, so
    assigning roles needs no credential against the identity provider."""
    matches = asyncio.run(_find_identities(eos_config, identifier))
    if len(matches) == 1:
        return matches[0].sub
    if len(matches) > 1:
        listed = ", ".join(f"{m.sub} ({m.email or 'no email'})" for m in matches)
        typer.secho(f"'{identifier}' matches several users: {listed}. Pass a sub instead.", fg="red", err=True)
        raise typer.Exit(1)
    if eos_config.auth.can_manage_accounts:
        with ZitadelClient(eos_config.auth) as client:
            return _match_user_id(client.list_users(), identifier)
    typer.secho(f"No user matching '{identifier}'. They must sign in to EOS once first.", fg="red", err=True)
    raise typer.Exit(1)


@auth_app.command("create-user")
@cli_command("Failed to create user")
def create_user(
    ctx: Context,
    username: str = typer.Argument(..., help="Username (login name)"),
    email: str = typer.Argument(..., help="Email address"),
    given_name: str = typer.Option(None, "--given", help="Given name (defaults to username)"),
    family_name: str = typer.Option(None, "--family", help="Family name (defaults to username)"),
    superuser: bool = typer.Option(False, "--superuser", help="Also grant the superuser role in this instance"),
) -> None:
    """Create a Zitadel account with a temporary password that must be changed at first login."""
    eos_config: EosConfig = ctx.obj
    password = generate_complexity_password()
    with ZitadelClient(eos_config.auth) as client:
        user_id = client.create_user(username, email, given_name or username, family_name or username, password)
    if superuser:
        asyncio.run(_insert_role(eos_config, user_id, Role.SUPERUSER, None))

    typer.secho(f"Created user '{username}' (id: {user_id}){' with superuser role' if superuser else ''}", fg="green")
    typer.echo(f"Temporary password (must be changed at first login): {password}")


@auth_app.command("list-users")
@cli_command("Failed to list users")
def list_users(ctx: Context) -> None:
    """List Zitadel accounts in the organization."""
    with ZitadelClient(ctx.obj.auth) as client:
        users = client.list_users()

    table = Table("ID", "Username", "Email", "State")
    for user in users:
        human = user.get("human", {})
        table.add_row(
            user.get("userId", ""),
            user.get("username", ""),
            human.get("email", {}).get("email", ""),
            user.get("state", "").removeprefix("USER_STATE_"),
        )
    console.print(table)


@auth_app.command("deactivate-user")
@cli_command("Failed to deactivate user")
def deactivate_user(ctx: Context, user: str = typer.Argument(..., help="Username, email, or Zitadel user ID")) -> None:
    """Deactivate a Zitadel account."""
    with ZitadelClient(ctx.obj.auth) as client:
        client.deactivate_user(_match_user_id(client.list_users(), user))
    typer.secho(f"Deactivated user {user}", fg="green")


@auth_app.command("reactivate-user")
@cli_command("Failed to reactivate user")
def reactivate_user(ctx: Context, user: str = typer.Argument(..., help="Username, email, or Zitadel user ID")) -> None:
    """Reactivate a deactivated Zitadel account."""
    with ZitadelClient(ctx.obj.auth) as client:
        client.reactivate_user(_match_user_id(client.list_users(), user))
    typer.secho(f"Reactivated user {user}", fg="green")


@auth_app.command("assign-role")
@cli_command("Failed to assign role")
def assign_role(
    ctx: Context,
    user: str = typer.Argument(..., help="Username, email, or Zitadel user ID"),
    role: str = typer.Argument(..., help="Role: superuser, lab_admin, editor, submitter, or viewer"),
    lab: str = typer.Option(None, "--lab", help="Lab name (required for lab_admin)"),
) -> None:
    """Assign a local role to a user in this EOS instance."""
    parsed_role = _parse_role(role)
    if (parsed_role == Role.LAB_ADMIN) != (lab is not None):
        typer.secho("--lab is required for lab_admin and not allowed for other roles", fg="red", err=True)
        raise typer.Exit(1)

    sub = _resolve_sub(ctx.obj, user)
    if asyncio.run(_insert_role(ctx.obj, sub, parsed_role, lab)):
        typer.secho(f"Assigned {role} to {user}" + (f" for lab '{lab}'" if lab else ""), fg="green")
    else:
        typer.secho("Role is already assigned", fg="yellow")


@auth_app.command("revoke-role")
@cli_command("Failed to revoke role")
def revoke_role(
    ctx: Context,
    user: str = typer.Argument(..., help="Username, email, or Zitadel user ID"),
    role: str = typer.Argument(..., help="Role: superuser, lab_admin, editor, submitter, or viewer"),
    lab: str = typer.Option(None, "--lab", help="Lab name (for lab_admin)"),
) -> None:
    """Revoke a local role from a user in this EOS instance."""
    parsed_role = _parse_role(role)
    sub = _resolve_sub(ctx.obj, user)

    async def _revoke() -> None:
        async with create_db_interface(ctx.obj).get_async_session() as db:
            await db.execute(
                sa_delete(UserRoleModel).where(
                    UserRoleModel.sub == sub, UserRoleModel.role == parsed_role, UserRoleModel.lab_name == lab
                )
            )

    asyncio.run(_revoke())
    typer.secho(f"Revoked {role} from {user}", fg="green")


@auth_app.command("list-roles")
@cli_command("Failed to list roles")
def list_roles(
    ctx: Context,
    user: str = typer.Argument(None, help="Filter by username, email, or Zitadel user ID"),
) -> None:
    """List local role assignments in this EOS instance."""
    names = asyncio.run(_identity_names(ctx.obj))
    sub_filter = _resolve_sub(ctx.obj, user) if user else None

    async def _list() -> list[UserRoleModel]:
        async with create_db_interface(ctx.obj).get_async_session() as db:
            query = select(UserRoleModel)
            if sub_filter:
                query = query.where(UserRoleModel.sub == sub_filter)
            result = await db.execute(query)
            return list(result.scalars().all())

    roles = asyncio.run(_list())
    table = Table("ID", "User", "Role", "Lab", "Granted by", "Created at")
    for role in roles:
        table.add_row(
            str(role.id),
            names.get(role.sub) or role.sub,
            role.role.value.lower(),
            role.lab_name or "-",
            role.granted_by,
            role.created_at.strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)
