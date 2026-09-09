from eos.cli import setup_cli
from eos.cli.setup_cli import (
    _defaults_from_env,
    _read_existing_env,
    _update_env_file,
)


def test_update_env_preserves_comments_and_order(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# A comment\nKEEP=untouched\nEOS_AUTH_ENABLED=false\n")

    _update_env_file(env, {"EOS_AUTH_ENABLED": "true"})

    assert env.read_text() == "# A comment\nKEEP=untouched\nEOS_AUTH_ENABLED=true\n"


def test_update_env_appends_missing_keys(tmp_path):
    env = tmp_path / ".env"
    env.write_text("EXISTING=1\n")

    _update_env_file(env, {"NEW_KEY": "value"})

    assert env.read_text() == "EXISTING=1\nNEW_KEY=value\n"


def test_update_env_creates_file_when_absent(tmp_path):
    env = tmp_path / "sub" / ".env"

    _update_env_file(env, {"KEY": "val"})

    assert env.read_text() == "KEY=val\n"


def test_read_existing_env_ignores_comments_and_blanks(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment\n\nA=1\nB=two\n")

    assert _read_existing_env(env) == {"A": "1", "B": "two"}


def test_defaults_reuse_existing_secrets(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("EOS_POSTGRES_USER=alice\nEOS_POSTGRES_PASSWORD=existing-pw\nZITADEL_MASTERKEY=mk\n")
    monkeypatch.setattr(setup_cli, "ENV_PATH", env)
    monkeypatch.setattr(setup_cli, "WEB_UI_ENV_PATH", tmp_path / "web.env")

    defaults = _defaults_from_env()

    assert defaults.pg_user == "alice"
    assert defaults.pg_password == "existing-pw"
    assert defaults.zitadel_masterkey == "mk"
