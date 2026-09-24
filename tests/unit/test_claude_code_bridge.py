"""Scoped Claude Hooks identify a session before its Work Room input is accepted."""

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from connectonion.useful_tools.claude_code_bridge import (
    ClaudeTranscriptTailer,
    poll_bridge,
    scoped_bridge_settings,
    session_start,
)

claude = importlib.import_module("connectonion.useful_tools.claude_code")
SESSION = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _post_hook(hook, event, *, token=None):
    request = Request(
        hook["args"][1],
        data=json.dumps(event).encode(),
        headers={"Authorization": f"Bearer {token or hook['args'][2]}"},
    )
    with urlopen(request, timeout=2) as response:
        assert response.status == 204


def test_bridge_launch_adds_scoped_settings_to_native_sources(tmp_path):
    argv = claude._stream_command(
        ["claude"], "inspect", "", "default", "haiku", tmp_path / "settings.json"
    )
    assert "--safe-mode" not in argv
    assert "--setting-sources" not in argv
    assert argv[argv.index("--settings") + 1] == str(tmp_path / "settings.json")


def test_scoped_settings_record_only_session_identity(tmp_path):
    with scoped_bridge_settings() as (settings, events):
        hook = json.loads(settings.read_text())["hooks"]["SessionStart"][0]["hooks"][0]
        assert hook["command"]
        assert hook["args"][1].startswith("http://127.0.0.1:")
        assert not (settings.stat().st_mode & 0o077)
        _post_hook(hook, {
            "hook_event_name": "SessionStart",
            "session_id": SESSION,
            "transcript_path": str(tmp_path / "session.jsonl"),
            "cwd": str(tmp_path),
            "source": "startup",
            "prompt": "secret text must not be spooled",
        })
        assert "secret text" not in events.read_text()
        assert session_start(events, cwd=tmp_path, requested_session="")["session_id"] == SESSION
    assert not settings.exists()


def test_scoped_receiver_rejects_wrong_token_and_unknown_events():
    with scoped_bridge_settings() as (settings, events):
        hook = json.loads(settings.read_text())["hooks"]["SessionStart"][0]["hooks"][0]
        with pytest.raises(HTTPError) as wrong_token:
            _post_hook(hook, {"hook_event_name": "SessionStart"}, token="wrong")
        assert wrong_token.value.code == 403
        with pytest.raises(HTTPError) as unknown:
            _post_hook(hook, {"hook_event_name": "NotAClaudeEvent"})
        assert unknown.value.code == 400
        with pytest.raises(HTTPError) as nested_identity:
            _post_hook(hook, {"hook_event_name": "PreToolUse", "tool_name": {"secret": "x"}})
        assert nested_identity.value.code == 400
        assert events.read_text() == ""


def test_scoped_receiver_bounds_body_and_event_rate(monkeypatch):
    bridge = importlib.import_module("connectonion.useful_tools.claude_code_bridge")
    monkeypatch.setattr(bridge, "_MAX_EVENT_RATE", 1)
    with scoped_bridge_settings() as (settings, events):
        hook = json.loads(settings.read_text())["hooks"]["Stop"][0]["hooks"][0]
        _post_hook(hook, {"hook_event_name": "Stop"})
        with pytest.raises(HTTPError) as rate_limit:
            _post_hook(hook, {"hook_event_name": "Stop"})
        assert rate_limit.value.code == 429
        oversized = Request(
            hook["args"][1], data=b"x" * (64 * 1024 + 1),
            headers={"Authorization": f"Bearer {hook['args'][2]}"},
        )
        with pytest.raises(HTTPError) as body_limit:
            urlopen(oversized, timeout=2)
        assert body_limit.value.code == 413
        assert len(events.read_text().splitlines()) == 1


def test_command_hook_refuses_a_loopback_looking_remote_url():
    bridge = importlib.import_module("connectonion.useful_tools.claude_code_bridge")
    with pytest.raises(ValueError, match="loopback"):
        bridge.forward_hook("http://127.0.0.1:80@remote.example/hook", "secret")


def test_latest_session_start_tracks_an_interactive_fork(tmp_path):
    forked = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    with scoped_bridge_settings() as (settings, events):
        hook = json.loads(settings.read_text())["hooks"]["SessionStart"][0]["hooks"][0]
        for source, session_id, transcript in (
            ("startup", SESSION, "initial.jsonl"),
            ("fork", forked, "forked.jsonl"),
        ):
            _post_hook(hook, {
                "hook_event_name": "SessionStart", "session_id": session_id,
                "transcript_path": str(tmp_path / transcript),
                "cwd": str(tmp_path), "source": source,
            })
        assert session_start(events, cwd=tmp_path, requested_session=SESSION)["session_id"] == SESSION
        latest = session_start(events, cwd=tmp_path, requested_session="", latest=True)
        assert latest["session_id"] == forked
        assert latest["transcript_path"] == str(tmp_path / "forked.jsonl")


def test_exact_path_tailer_handles_partial_lines_and_duplicate_replay(tmp_path):
    path = tmp_path / "session.jsonl"
    tailer = ClaudeTranscriptTailer(path)
    user = json.dumps({
        "type": "user", "uuid": "user-1", "message": {"content": "hello"},
    })
    assistant = json.dumps({
        "type": "assistant", "uuid": "assistant-1",
        "message": {"content": [
            {"type": "thinking", "thinking": "private"},
            {"type": "text", "text": "world"},
        ]},
    })
    path.write_text(user + "\n" + assistant[:20])
    assert tailer.read_available() == [{
        "message_id": "user-1", "role": "user", "text": "hello",
    }]
    with path.open("a") as output:
        output.write(assistant[20:] + "\n")
    assert tailer.read_available() == [{
        "message_id": "assistant-1", "role": "assistant", "text": "world",
    }]
    assert tailer.read_available() == []
    assert "private" not in str(tailer.read_available())

    replacement = tmp_path / "replacement.jsonl"
    replacement.write_text(user + "\n")
    replacement.replace(path)
    assert tailer.read_available() == []


def test_exact_path_tailer_switches_on_fork_and_ignores_unknown_records(tmp_path):
    first = tmp_path / "first.jsonl"
    forked = tmp_path / "forked.jsonl"
    tailer = ClaudeTranscriptTailer(first)
    first.write_text(json.dumps({"type": "queue-operation", "content": "private"}) + "\n")
    assert tailer.read_available() == []
    assert tailer.unknown_records == 1
    forked.write_text(json.dumps({
        "type": "assistant", "uuid": "fork-answer",
        "message": {"content": [{"type": "text", "text": "new path"}]},
    }) + "\n")
    tailer.follow(forked)
    assert tailer.read_available() == [{
        "message_id": "fork-answer", "role": "assistant", "text": "new path",
    }]


def test_hook_path_switch_drains_old_transcript_before_following_new_one(tmp_path):
    events = tmp_path / "events.jsonl"
    first = tmp_path / "first.jsonl"
    forked = tmp_path / "forked.jsonl"
    first.write_text(json.dumps({
        "type": "user", "uuid": "first-user", "sessionId": SESSION,
        "message": {"content": "before fork"},
    }) + "\n")
    forked_session = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    forked.write_text(json.dumps({
        "type": "assistant", "uuid": "fork-answer", "sessionId": forked_session,
        "message": {"content": [{"type": "text", "text": "after fork"}]},
    }) + "\n")
    events.write_text("".join(json.dumps({
        "hook_event_name": "SessionStart", "session_id": session_id,
        "transcript_path": str(path), "cwd": str(tmp_path), "source": source,
    }) + "\n" for source, session_id, path in (
        ("startup", SESSION, first), ("fork", forked_session, forked),
    )))

    offset, tailer, facts, messages = poll_bridge(events, 0, tmp_path, None)

    assert offset == events.stat().st_size
    assert tailer.path == forked
    assert [fact["source"] for fact in facts] == ["startup", "fork"]
    assert [message["text"] for message in messages] == ["before fork", "after fork"]


@pytest.mark.parametrize("changed", ["session_id", "cwd", "transcript_path"])
def test_bridge_rejects_hook_identity_change(tmp_path, changed):
    transcript = tmp_path / "owned.jsonl"
    session = {
        "session_id": SESSION, "cwd": str(tmp_path),
        "transcript_path": str(transcript),
    }
    altered = dict(session)
    altered[changed] = str(tmp_path / "other")
    events = tmp_path / "events.jsonl"
    events.write_text("".join(json.dumps({"hook_event_name": kind, **identity}) + "\n"
                              for kind, identity in (("SessionStart", session),
                                                     ("PreToolUse", altered))))
    with pytest.raises(ValueError, match="owned session identity"):
        poll_bridge(events, 0, tmp_path, None)


def test_interactive_launch_uses_native_tui_and_scoped_hook(tmp_path, monkeypatch):
    fake_cli = tmp_path / "fake_claude.py"
    fake_cli.write_text("""
import json
import subprocess
import sys
from pathlib import Path

argv = sys.argv[1:]
settings = json.loads(Path(argv[argv.index('--settings') + 1]).read_text())
hook = settings['hooks']['SessionStart'][0]['hooks'][0]
subprocess.run(
    [hook['command'], *hook['args']],
    input=json.dumps({
        'hook_event_name': 'SessionStart',
        'session_id': 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        'transcript_path': str(Path.cwd() / 'transcript.jsonl'),
        'cwd': str(Path.cwd()),
        'source': 'startup',
    }),
    text=True,
    check=True,
)
Path('launch.json').write_text(json.dumps(argv))
Path('transcript.jsonl').write_text(json.dumps({
    'type': 'assistant', 'uuid': 'reply-1',
    'sessionId': 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    'message': {'content': [
        {'type': 'thinking', 'thinking': 'private'},
        {'type': 'text', 'text': 'hello from Claude'},
    ]},
}) + '\\n')
""")
    monkeypatch.setattr(claude, "_claude_command", lambda: ([sys.executable, str(fake_cli)], ""))

    facts = []
    messages = []
    exit_code, session_id = claude.run_interactive_claude(
        cwd=str(tmp_path), model="haiku", on_private_fact=facts.append,
        on_message=messages.append,
    )

    assert exit_code == 0
    assert session_id == SESSION
    argv = json.loads((tmp_path / "launch.json").read_text())
    assert "-p" not in argv
    assert argv[argv.index("--model") + 1] == "haiku"
    assert facts[0]["hook_event_name"] == "SessionStart"
    assert messages == [{
        "message_id": "reply-1", "role": "assistant", "text": "hello from Claude",
    }]


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
        _post_hook(hook, {
            "hook_event_name": "SessionStart",
            "session_id": SESSION,
            "transcript_path": str(tmp_path / "session.jsonl"),
            "cwd": str(tmp_path),
        })
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
