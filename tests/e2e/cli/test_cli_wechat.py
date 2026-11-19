"""CLI routing and key-storage tests for `co wechat` (#3146).

These cover the surface that lands before decryption: macOS gating, the
prerequisite check, saving/validating a key, and that the not-yet-implemented
read commands fail with a clear exit code. No WeChat and no decryption here.
"""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.cli.commands import wechat_commands as wc

runner = CliRunner()

VALID_KEY = "x'" + "0f" * 32 + "'"


@pytest.fixture
def macos():
    """Pretend we are on macOS so the command runs anywhere CI does."""
    with patch.object(wc.platform, "system", return_value="Darwin"):
        yield


@pytest.fixture
def keys_env(tmp_path, monkeypatch):
    """Point WECHAT_DB_KEY storage at an isolated keys.env, and clear the env var."""
    path = tmp_path / "keys.env"
    monkeypatch.setattr(wc, "KEYS_ENV", path)
    monkeypatch.delenv(wc.KEY_NAME, raising=False)
    return path


def test_wechat_is_macos_only():
    with patch.object(wc.platform, "system", return_value="Linux"):
        result = runner.invoke(app, ["wechat", "doctor"])
    assert result.exit_code == 2
    assert "macOS-only" in result.output


def test_key_set_saves_valid_key_0600(macos, keys_env):
    result = runner.invoke(app, ["wechat", "key", "set", VALID_KEY])
    assert result.exit_code == 0
    assert keys_env.exists()
    assert f"{wc.KEY_NAME}={VALID_KEY}" in keys_env.read_text()
    assert (keys_env.stat().st_mode & 0o777) == 0o600


def test_key_set_rejects_malformed_key(macos, keys_env):
    result = runner.invoke(app, ["wechat", "key", "set", "not-a-key"])
    assert result.exit_code == 2
    assert not keys_env.exists()


def test_key_set_then_read_round_trips(macos, keys_env):
    runner.invoke(app, ["wechat", "key", "set", VALID_KEY])
    assert wc._read_key() == VALID_KEY


def test_key_set_replaces_existing_line(macos, keys_env):
    keys_env.write_text(f"OTHER=1\n{wc.KEY_NAME}=x'" + "aa" * 32 + "'\n")
    runner.invoke(app, ["wechat", "key", "set", VALID_KEY])
    text = keys_env.read_text()
    assert text.count(wc.KEY_NAME) == 1
    assert VALID_KEY in text
    assert "OTHER=1" in text  # unrelated keys are preserved


def test_key_no_subcommand_explains_how_to_get_it(macos):
    result = runner.invoke(app, ["wechat", "key"])
    assert result.exit_code == 0
    assert "re-signed copy" in result.output.lower() or "re-signed" in result.output.lower()


@pytest.mark.parametrize("command", ["chats", "export"])
def test_read_commands_not_implemented_yet(macos, command):
    result = runner.invoke(app, ["wechat", command])
    assert result.exit_code == 2
    assert "not implemented yet" in result.output


def test_doctor_blocks_when_unready(macos, keys_env):
    with patch.object(wc, "_container_status", return_value=("missing", None)):
        result = runner.invoke(app, ["wechat", "doctor"])
    assert result.exit_code == 2  # no key and no data


def test_doctor_ok_when_ready(macos, keys_env, tmp_path):
    runner.invoke(app, ["wechat", "key", "set", VALID_KEY])
    account = tmp_path / "account"
    with patch.object(wc, "_container_status", return_value=("ok", account)):
        result = runner.invoke(app, ["wechat", "doctor"])
    assert result.exit_code == 0
