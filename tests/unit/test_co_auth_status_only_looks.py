"""`co auth status` must look, not sign in.

`co auth` took one optional word and only recognised google, microsoft,
feishu and lark. Every other word fell through to full OpenOnion
authentication. On a fresh machine `co auth status` printed "Welcome" and
minted a keypair and an account; `co auth logout` logged you *in*. Shipped
text told people to run `co auth status` (the `co wiki init` recovery tip),
so the one command offered as a safe look was the one that wrote secrets.

These run against the isolated HOME tests/conftest.py gives every test.
The network is blocked there too, so a status that tried to authenticate
would fail loudly rather than pass by accident.
"""

import os
import re
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from connectonion.cli.main import app


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _co_dir() -> Path:
    return Path.home() / ".co"


def _fail_if_called(*_args, **_kwargs):
    raise AssertionError("this word must never authenticate")


def test_status_on_a_fresh_home_creates_nothing_and_says_not_signed_in():
    with patch("connectonion.cli.commands.auth_commands.authenticate", _fail_if_called):
        result = CliRunner().invoke(app, ["auth", "status"])
    out = _plain(result.output)
    assert result.exit_code == 0, out
    assert not (_co_dir() / "keys").exists()
    assert not (_co_dir() / "keys.env").exists()
    assert "not signed in" in out.lower()
    assert "co auth login" in out


def test_status_reports_identity_token_and_oauth_without_writing():
    from connectonion import address
    identity = address.generate()
    address.save(identity, _co_dir())
    keys_env = _co_dir() / "keys.env"
    keys_env.write_text("OPENONION_API_KEY=tok\nGOOGLE_ACCESS_TOKEN=a\n"
                        "GOOGLE_REFRESH_TOKEN=r\nGOOGLE_SCOPES=gmail\n", encoding="utf-8")
    before = keys_env.read_bytes()
    with patch("connectonion.cli.commands.auth_commands.authenticate", _fail_if_called):
        result = CliRunner().invoke(app, ["auth", "status"])
    out = _plain(result.output)
    assert result.exit_code == 0, out
    assert identity["address"] in out
    assert "Google" in out and "connected" in out
    assert "not signed in" not in out.lower()
    assert keys_env.read_bytes() == before


def test_unknown_service_exits_2_names_the_services_and_writes_nothing():
    with patch("connectonion.cli.commands.auth_commands.authenticate", _fail_if_called):
        result = CliRunner().invoke(app, ["auth", "foo"])
    out = _plain(result.output)
    assert result.exit_code == 2, out
    for word in ("google", "microsoft", "feishu", "lark", "login", "status", "logout"):
        assert word in out
    assert not _co_dir().exists() or not any(_co_dir().iterdir())


def test_login_is_what_bare_auth_did():
    with patch("connectonion.cli.commands.auth_commands.handle_auth") as handle:
        result = CliRunner().invoke(app, ["auth", "login"])
    assert result.exit_code == 0, result.output
    handle.assert_called_once_with()


def test_logout_removes_only_the_token_after_confirmation():
    from connectonion import address
    address.save(address.generate(), _co_dir())
    key_file = _co_dir() / "keys" / "agent.key"
    key_bytes = key_file.read_bytes()
    keys_env = _co_dir() / "keys.env"
    keys_env.write_text("OPENONION_API_KEY=tok\nOTHER=kept\n", encoding="utf-8")

    declined = CliRunner().invoke(app, ["auth", "logout"], input="n\n")
    assert declined.exit_code != 0
    assert "OPENONION_API_KEY=tok" in keys_env.read_text(encoding="utf-8")

    with patch("connectonion.cli.commands.auth_commands.authenticate", _fail_if_called):
        result = CliRunner().invoke(app, ["auth", "logout"], input="y\n")
    assert result.exit_code == 0, _plain(result.output)
    text = keys_env.read_text(encoding="utf-8")
    assert "OPENONION_API_KEY" not in text
    assert "OTHER=kept" in text
    assert key_file.read_bytes() == key_bytes


def test_logout_with_nothing_signed_in_creates_nothing():
    result = CliRunner().invoke(app, ["auth", "logout"], input="y\n")
    assert result.exit_code == 0, _plain(result.output)
    assert not (_co_dir() / "keys.env").exists()
    assert not (_co_dir() / "keys").exists()
