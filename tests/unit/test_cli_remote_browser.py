"""CLI contract tests for ``co remote-browser``."""

import importlib
import json

from connectonion.cli.commands.remote_browser_commands import handle_remote_browser


class FakeRemote:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def remote_browser(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return self.result


def _result(ok=True, **extra):
    value = {
        "schema_version": "1",
        "ok": ok,
        "command": "remote-browser.start",
        "request_id": "req-1",
        "summary": "Remote browser session started.",
        "result": {"session_id": "rb_" + "1" * 32, "status": "active"},
        "state": {"session": "active"},
        "tips": [],
        "warnings": [],
        "next_actions": [],
    }
    value.update(extra)
    return value


def _install(monkeypatch, result):
    remote = FakeRemote(result)
    monkeypatch.setattr("connectonion.connect", lambda address, **kwargs: remote)
    connect_module = importlib.import_module("connectonion.network.connect")
    monkeypatch.setattr(
        connect_module, "_this_callers_identity", lambda: {"address": "0xme"}
    )
    return remote


def test_start_forwards_only_typed_start_options(monkeypatch, capsys):
    remote = _install(monkeypatch, _result())

    assert handle_remote_browser(["--headless", "--timeout", "5", "0xhost", "start"]) == 0

    assert remote.calls == [
        (
            "start",
            {
                "session_id": None,
                "timeout": 5.0,
                "headless": True,
                "proxy": "direct",
            },
        )
    ]
    assert "rb_" in capsys.readouterr().out


def test_json_is_the_stable_envelope(monkeypatch, capsys):
    expected = _result()
    _install(monkeypatch, expected)

    assert handle_remote_browser(["--json", "0xhost", "start"]) == 0

    assert json.loads(capsys.readouterr().out) == expected


def test_json_validation_failure_emits_only_one_json_envelope(capsys):
    assert handle_remote_browser(["--json", "0xhost", "status"]) == 2

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["ok"] is False
    assert result["code"] == "INVALID_ARGUMENT"
    assert captured.err == ""


def test_session_command_requires_exactly_one_session_id(capsys):
    assert handle_remote_browser(["0xhost", "status"]) == 2
    assert "session-id" in capsys.readouterr().err


def test_failure_is_exit_one_and_preserves_code(monkeypatch, capsys):
    _install(
        monkeypatch,
        _result(
            ok=False,
            code="SECURE_CHANNEL_UNAVAILABLE",
            message="direct endpoint required",
        ),
    )

    assert handle_remote_browser(["0xhost", "sessions"]) == 1

    assert "SECURE_CHANNEL_UNAVAILABLE" in capsys.readouterr().err


def test_proxy_option_is_not_accepted_by_non_start_command(monkeypatch):
    remote = _install(monkeypatch, _result())

    handle_remote_browser(["--proxy", "direct", "0xhost", "sessions"])

    assert remote.calls == [("sessions", {"session_id": None, "timeout": 60.0})]


def test_shared_start_names_the_mode_and_sends_no_endpoint(tmp_path, monkeypatch):
    """The share is attached to the host by `co proxy share`, not carried in
    the start request — the host already holds this identity's channel and
    answers REMOTE_SESSION_PROXY_NOT_ATTACHED when it does not."""
    remote = _install(monkeypatch, _result())

    assert handle_remote_browser(["--proxy", "shared", "0xhost", "start"]) == 0

    command, kwargs = remote.calls[0]
    assert command == "start"
    assert kwargs["proxy"] == "shared"
    assert "share" not in kwargs


# --- `config`: remember the remote once, then leave the address out (#1366) ---


import pytest


@pytest.fixture(autouse=True)
def _config_in_tmp(monkeypatch, tmp_path):
    from connectonion.cli.commands import remote_browser_commands as mod

    monkeypatch.setattr(mod, "CONFIG_PATH", tmp_path / "remote-browser.json")


def _install_capturing_address(monkeypatch, result):
    remote = FakeRemote(result)
    seen = []

    def connect(address, **kwargs):
        seen.append(address)
        return remote

    monkeypatch.setattr("connectonion.connect", connect)
    connect_module = importlib.import_module("connectonion.network.connect")
    monkeypatch.setattr(
        connect_module, "_this_callers_identity", lambda: {"address": "0xme"}
    )
    return remote, seen


def test_config_remembers_address_and_proxy_then_start_needs_neither(monkeypatch, capsys):
    remote, seen = _install_capturing_address(monkeypatch, _result())

    assert handle_remote_browser(["config", "0xhost", "--proxy", "direct"]) == 0
    assert "Now: co remote-browser start" in capsys.readouterr().out

    assert handle_remote_browser(["start"]) == 0

    assert seen == ["0xhost"]
    assert remote.calls[0][1]["proxy"] == "direct"


def test_config_shows_what_is_remembered(capsys):
    handle_remote_browser(["config", "0xhost", "--proxy", "shared"])
    capsys.readouterr()

    assert handle_remote_browser(["config"]) == 0
    assert capsys.readouterr().out.strip() == "0xhost  proxy: shared"

    assert handle_remote_browser(["--json", "config"]) == 0
    assert json.loads(capsys.readouterr().out) == {"address": "0xhost", "proxy": "shared"}


def test_config_rejects_unknown_proxy_mode(capsys):
    assert handle_remote_browser(["config", "0xhost", "--proxy", "tor"]) == 2
    assert "--proxy must be one of direct, shared" in capsys.readouterr().err


def test_without_config_and_without_address_it_says_how_to_configure(monkeypatch, capsys):
    _install(monkeypatch, _result())

    assert handle_remote_browser(["start"]) == 2

    err = capsys.readouterr().err
    assert "No remote browser configured." in err
    assert "co remote-browser config <address> --proxy shared" in err


def test_explicit_address_beats_the_remembered_one(monkeypatch):
    remote, seen = _install_capturing_address(monkeypatch, _result())
    handle_remote_browser(["config", "0xremembered"])

    assert handle_remote_browser(["0xexplicit", "sessions"]) == 0

    assert seen == ["0xexplicit"]


def test_explicit_proxy_flag_beats_the_remembered_mode(monkeypatch):
    remote, _ = _install_capturing_address(monkeypatch, _result())
    handle_remote_browser(["config", "0xhost", "--proxy", "direct"])

    handle_remote_browser(["--proxy", "direct", "start"])
    handle_remote_browser(["config", "0xhost", "--proxy", "shared"])
    handle_remote_browser(["--proxy", "direct", "start"])

    assert [call[1]["proxy"] for call in remote.calls] == ["direct", "direct"]


def test_co_proxy_share_and_stop_default_to_the_remembered_address(monkeypatch, capsys, tmp_path):
    from connectonion.cli.commands import proxy_commands

    monkeypatch.setattr(proxy_commands, "STATE_PATH", tmp_path / "proxy-shares.json")
    shared_with = []
    monkeypatch.setattr(
        proxy_commands, "_share", lambda address, *a: shared_with.append(address) or 0
    )

    assert proxy_commands.handle_proxy(["share"]) == 2
    assert "No remote browser configured." in capsys.readouterr().err

    handle_remote_browser(["config", "0xhost", "--proxy", "shared"])
    assert proxy_commands.handle_proxy(["share"]) == 0
    assert proxy_commands.handle_proxy(["share", "to", "0xother"]) == 0
    assert shared_with == ["0xhost", "0xother"]

    capsys.readouterr()
    assert proxy_commands.handle_proxy(["stop"]) == 1
    assert "not sharing your connection with 0xhost" in capsys.readouterr().out


def test_start_is_headed_by_default_like_co_browser(monkeypatch):
    """A visible window is the local default and the anti-detect default; a
    host without a display already falls back to headless on its own."""
    remote = _install(monkeypatch, _result())

    handle_remote_browser(["0xhost", "start"])

    assert remote.calls[0][1]["headless"] is False
