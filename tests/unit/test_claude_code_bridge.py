"""Scoped Claude Hooks identify a session before its Work Room input is accepted."""

import importlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from connectonion.useful_tools.claude_code_bridge import (
    record_session_start,
    scoped_bridge_settings,
    session_start,
)

claude = importlib.import_module("connectonion.useful_tools.claude_code")
SESSION = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def test_bridge_launch_adds_scoped_settings_to_native_sources(tmp_path):
    argv = claude._stream_command(
        ["claude"], "inspect", "", "default", "haiku", tmp_path / "settings.json"
    )
    assert "--safe-mode" not in argv
    assert "--setting-sources" not in argv
    assert argv[argv.index("--settings") + 1] == str(tmp_path / "settings.json")


def test_scoped_settings_record_only_session_identity(tmp_path, monkeypatch):
    with scoped_bridge_settings() as (settings, events):
        hook = json.loads(settings.read_text())["hooks"]["SessionStart"][0]["hooks"][0]
        assert hook["command"]
        assert hook["args"][-1] == str(events)
        assert not (settings.stat().st_mode & 0o077)
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({
            "hook_event_name": "SessionStart",
            "session_id": SESSION,
            "transcript_path": str(tmp_path / "session.jsonl"),
            "cwd": str(tmp_path),
            "source": "startup",
            "prompt": "secret text must not be spooled",
        })))
        record_session_start(events)
        assert "secret text" not in events.read_text()
        assert session_start(events, cwd=tmp_path, requested_session="")["session_id"] == SESSION
    assert not settings.exists()


@pytest.mark.parametrize("changed", ["session", "cwd", "transcript"])
def test_session_start_rejects_wrong_identity(tmp_path, changed):
    event = {
        "hook_event_name": "SessionStart",
        "session_id": SESSION,
        "transcript_path": str(tmp_path / "session.jsonl"),
        "cwd": str(tmp_path),
    }
    if changed == "session":
        event["session_id"] = "another-session"
    elif changed == "cwd":
        event["cwd"] = str(tmp_path.parent)
    else:
        event["transcript_path"] = "relative.jsonl"
    events = tmp_path / "events.jsonl"
    events.write_text(json.dumps(event) + "\n")

    with pytest.raises(ValueError):
        session_start(events, cwd=tmp_path, requested_session=SESSION)


def test_bridge_acknowledges_web_input_only_after_session_hook(tmp_path, monkeypatch):
    agent = SimpleNamespace(
        io=MagicMock(),
        current_session={
            "_active_tool_call_id": "outer",
            "_provider_direct_message_id": "request-1",
            "_provider_continuation_of": "claude_code:outer",
            "_provider_direct_state_revision": 1,
        },
    )
    monkeypatch.setattr(claude, "_claude_command", lambda: (["claude"], ""))

    def run_process(argv, *, on_event, on_started, **kwargs):
        assert on_started is None
        agent.io.send.assert_not_called()
        settings = Path(argv[argv.index("--settings") + 1])
        hook = json.loads(settings.read_text())["hooks"]["SessionStart"][0]["hooks"][0]
        events = Path(hook["args"][-1])
        events.write_text(json.dumps({
            "hook_event_name": "SessionStart",
            "session_id": SESSION,
            "transcript_path": str(tmp_path / "session.jsonl"),
            "cwd": str(tmp_path),
        }) + "\n")
        on_event({"type": "system", "subtype": "init", "session_id": SESSION})
        assert agent.io.send.call_args.args[0]["type"] == "PROVIDER_INPUT_ACK"
        return SimpleNamespace(
            payload={"type": "result", "session_id": SESSION, "result": "done"},
            returncode=0,
            stderr="",
            invalid_output="",
        )

    monkeypatch.setattr(claude, "_run_process", run_process)
    result = json.loads(claude.run_co_claude(
        "fix it", cwd=str(tmp_path), workspace=tmp_path, agent=agent
    ))
    assert result["status"] == "completed"
    assert result["session_id"] == SESSION


def test_missing_session_hook_never_acknowledges_web_input(tmp_path, monkeypatch):
    agent = SimpleNamespace(
        io=MagicMock(),
        current_session={
            "_active_tool_call_id": "outer",
            "_provider_direct_message_id": "request-1",
            "_provider_continuation_of": "claude_code:outer",
            "_provider_direct_state_revision": 1,
        },
    )
    monkeypatch.setattr(claude, "_claude_command", lambda: (["claude"], ""))

    def run_process(argv, *, on_event, **kwargs):
        on_event({"type": "system", "subtype": "init", "session_id": SESSION})

    monkeypatch.setattr(claude, "_run_process", run_process)
    result = json.loads(claude.run_co_claude(
        "fix it", cwd=str(tmp_path), workspace=tmp_path, agent=agent
    ))
    assert result["status"] == "error"
    agent.io.send.assert_not_called()
