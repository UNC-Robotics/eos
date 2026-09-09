import pytest
from sqlalchemy import select

from eos.auth.api_tokens import EOS_TOKEN_PREFIX
from eos.auth.entities.user_identity import UserIdentityModel
from eos.auth.entities.user_role import AuthenticatedUser
from eos.auth.identity import record_identity, reset_sync_cache
from eos.configuration.eos_config import DatabaseType, DbConfig, SqliteDbConfig
from eos.database.sqlite_db_interface import SqliteDbInterface


class Validator:
    """Stands in for the token validator, counting userinfo lookups."""

    def __init__(self, claims: dict | None = None, fail: bool = False):
        self.claims = claims
        self.fail = fail
        self.calls = 0

    async def fetch_userinfo(self, token: str) -> dict | None:
        self.calls += 1
        if self.fail:
            raise RuntimeError("userinfo is unavailable")
        return self.claims


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_sync_cache()
    yield
    reset_sync_cache()


@pytest.fixture
async def db_interface():
    db_interface = SqliteDbInterface(DbConfig(type=DatabaseType.SQLITE, sqlite=SqliteDbConfig(in_memory=True)))
    await db_interface.initialize_database()
    yield db_interface
    await db_interface._async_engine.dispose()


async def identities(db_interface) -> list[UserIdentityModel]:
    async with db_interface.get_async_session() as db:
        return list((await db.execute(select(UserIdentityModel))).scalars().all())


async def test_records_a_user_from_token_claims(db_interface):
    user = AuthenticatedUser(sub="alice", email="Alice@Lab.Example", name="Alice")
    await record_identity(db_interface, Validator(), user, "jwt-token")

    rows = await identities(db_interface)
    assert len(rows) == 1
    assert rows[0].sub == "alice"
    assert rows[0].email == "alice@lab.example"
    assert rows[0].name == "Alice"


async def test_falls_back_to_userinfo_when_the_token_has_no_email(db_interface):
    validator = Validator(claims={"email": "bob@lab.example", "name": "Bob"})
    await record_identity(db_interface, validator, AuthenticatedUser(sub="bob"), "jwt-token")

    rows = await identities(db_interface)
    assert (rows[0].email, rows[0].name) == ("bob@lab.example", "Bob")
    assert validator.calls == 1


async def test_no_userinfo_lookup_when_the_token_already_has_email(db_interface):
    validator = Validator()
    user = AuthenticatedUser(sub="alice", email="alice@lab.example")
    await record_identity(db_interface, validator, user, "jwt-token")
    assert validator.calls == 0


async def test_eos_api_tokens_never_trigger_a_userinfo_lookup(db_interface):
    validator = Validator()
    await record_identity(db_interface, validator, AuthenticatedUser(sub="alice"), EOS_TOKEN_PREFIX + "secret")
    assert validator.calls == 0
    assert (await identities(db_interface))[0].sub == "alice"


async def test_records_once_per_process(db_interface):
    validator = Validator(claims={"email": "bob@lab.example"})
    for _ in range(3):
        await record_identity(db_interface, validator, AuthenticatedUser(sub="bob"), "jwt-token")

    assert validator.calls == 1
    assert len(await identities(db_interface)) == 1


async def test_a_failing_userinfo_lookup_still_records_the_user(db_interface):
    validator = Validator(fail=True)
    await record_identity(db_interface, validator, AuthenticatedUser(sub="bob"), "jwt-token")

    rows = await identities(db_interface)
    assert rows[0].sub == "bob"
    assert rows[0].email is None
    # The sub is marked as seen, so a provider without userinfo does not cost a lookup per request
    await record_identity(db_interface, validator, AuthenticatedUser(sub="bob"), "jwt-token")
    assert validator.calls == 1


async def test_later_claims_fill_in_missing_fields(db_interface):
    await record_identity(db_interface, Validator(), AuthenticatedUser(sub="bob"), "jwt-token")
    reset_sync_cache()
    await record_identity(db_interface, Validator(), AuthenticatedUser(sub="bob", name="Bob"), "jwt-token")

    rows = await identities(db_interface)
    assert len(rows) == 1
    assert rows[0].name == "Bob"
