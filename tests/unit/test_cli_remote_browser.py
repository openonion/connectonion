"""CLI contract tests for ``co remote-browser``."""

import json
import importlib

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

    assert handle_remote_browser(["--headed", "--timeout", "5", "0xhost", "start"]) == 0

    assert remote.calls == [
        (
            "start",
            {
                "session_id": None,
                "timeout": 5.0,
                "headless": False,
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
