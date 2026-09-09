import pytest

from eos.auth.api_tokens import EOS_TOKEN_PREFIX, generate_api_token, hash_api_token, resolve_api_token
from eos.auth.entities.api_token import ApiTokenModel
from eos.auth.entities.user_identity import UserIdentityModel
from eos.configuration.eos_config import DatabaseType, DbConfig, SqliteDbConfig
from eos.database.sqlite_db_interface import SqliteDbInterface

KNOWN_TOKEN = EOS_TOKEN_PREFIX + "known-secret"


@pytest.fixture
async def db_interface():
    db_interface = SqliteDbInterface(DbConfig(type=DatabaseType.SQLITE, sqlite=SqliteDbConfig(in_memory=True)))
    await db_interface.initialize_database()
    async with db_interface.get_async_session() as db:
        db.add(ApiTokenModel(owner_sub="alice", token_hash=hash_api_token(KNOWN_TOKEN)))
        db.add(UserIdentityModel(sub="alice", email="alice@lab.example", name="Alice"))
    return db_interface


def test_generated_token_is_prefixed_and_unique():
    first, first_hash = generate_api_token()
    second, second_hash = generate_api_token()
    assert first.startswith(EOS_TOKEN_PREFIX)
    assert first != second
    assert first_hash != second_hash
    assert first_hash == hash_api_token(first)


def test_hash_is_stable():
    assert hash_api_token(KNOWN_TOKEN) == hash_api_token(KNOWN_TOKEN)


def test_secret_is_not_recoverable_from_hash():
    token, token_hash = generate_api_token()
    assert token not in token_hash


async def test_resolves_to_owner_with_identity(db_interface):
    async with db_interface.get_async_session() as db:
        user = await resolve_api_token(db, KNOWN_TOKEN)
    assert user.sub == "alice"
    assert user.email == "alice@lab.example"
    assert user.name == "Alice"


async def test_resolves_without_an_identity_row(db_interface):
    async with db_interface.get_async_session() as db:
        db.add(ApiTokenModel(owner_sub="stranger", token_hash=hash_api_token(EOS_TOKEN_PREFIX + "other")))
    async with db_interface.get_async_session() as db:
        user = await resolve_api_token(db, EOS_TOKEN_PREFIX + "other")
    assert user.sub == "stranger"
    assert user.email is None
    assert user.name is None


async def test_unknown_token_resolves_to_none(db_interface):
    async with db_interface.get_async_session() as db:
        assert await resolve_api_token(db, EOS_TOKEN_PREFIX + "nonesuch") is None
