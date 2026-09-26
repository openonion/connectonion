"""A paired browser may take and release the exact terminal Claude session."""

import threading
import time
from types import SimpleNamespace

from connectonion.cli.co_ai import claude_station
from connectonion.network.host.http_router import session_handler, sessions_handler
from connectonion.network.host.session.storage import SessionStorage, session_owner
from connectonion.network.host.session.ui import session_to_chat_items
from connectonion.useful_tools.claude_code import _approve_claude_permission
from connectonion.plugins.coding_agents import _provider_permission_for_event


def test_terminal_browser_terminal_handover(tmp_path, monkeypatch):
    native_session = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    storage = SessionStorage(tmp_path / "station" / "session_results.jsonl")
    station = claude_station.ClaudeStation(tmp_path, storage)
    assert session_handler(storage, station.session_id) is None
    assert sessions_handler(storage)["sessions"] == []
    launched = []
    history_modes = []

    def terminal(**options):
        launched.append(options["session_id"])
        history_modes.append(options["skip_existing_messages"])
        options["on_private_fact"]({
            "hook_event_name": "SessionStart", "session_id": native_session,
        })
        if len(launched) == 1:
            control_revision = station._revision
            options["on_private_fact"]({"hook_event_name": "UserPromptSubmit"})
            options["on_private_fact"]({"hook_event_name": "Stop"})
            assert station._revision == control_revision
            assert options["stop_event"].wait(3)
        return 0, native_session

    monkeypatch.setattr(claude_station, "run_interactive_claude", terminal)
    worker = threading.Thread(target=station.run)
    worker.start()
    deadline = time.monotonic() + 3
    while station._phase != "local_observing" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert station.attach("0xowner", "bad")["accepted"] is False
    assert station.attach("0xowner", station.pairing_code)["accepted"] is True
    assert session_owner(storage.get(station.session_id)) == "0xowner"
    assert station.can_continue("0xowner", station.session_id) is False
    taken = station.take_control("0xowner", station._revision)
    assert taken["accepted"] is True
    assert station.can_continue("0xowner", station.session_id) is True
    cards = session_to_chat_items(storage.get(station.session_id).session)
    provider = next(item for item in cards if item.get("type") == "provider_invocation")
    assert provider["status"] == "completed"
    assert provider["controlOwner"] == "browser"
    assert provider["controlPhase"] == "remote_controlling"
    revisions = [event["stateRevision"] for event in storage.get(station.session_id).session["trace"]
                 if event["type"] == "provider_invocation"]
    assert revisions == sorted(set(revisions))
    assert station.take_control("0xowner", taken["stateRevision"])["accepted"] is False
    released = station.release_control("0xowner", taken["stateRevision"])
    assert released["accepted"] is True
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert launched == ["", native_session]
    assert history_modes == [False, True]


def test_invocation_revision_advances_from_persisted_trace(tmp_path):
    storage = SessionStorage(tmp_path / "station" / "session_results.jsonl")
    station = claude_station.ClaudeStation(tmp_path, storage)
    station._append(station._invocation("running"))
    station._invocation_revision = 0

    completed = station._invocation("completed")

    assert completed["stateRevision"] == 2


def test_browser_approval_requires_owned_workspace_edit(tmp_path):
    class ApprovalIO:
        def __init__(self):
            self.requests = []
            self.live = []

        def send_live_trace(self, entry):
            self.live.append(entry)

        def request_approval(self, tool, arguments, *, context):
            assert self.live[-1]["status"] == "awaiting_approval"
            assert self.live[-1]["invocationId"] == context["invocationId"]
            self.requests.append((tool, arguments, context))
            return True

    io = ApprovalIO()
    trace = []
    agent = SimpleNamespace(
        io=io,
        _record_trace=trace.append,
        current_session={
            "requester": {"address": "0xowner", "level": "admin"},
            "_active_tool_call_id": "task-1",
        },
    )
    edit = {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "note.txt")}}
    assert _approve_claude_permission(edit, agent, tmp_path)
    assert io.requests[0][2]["providerApproval"]["files"] == ["note.txt"]
    assert [item["status"] for item in trace] == ["awaiting_approval", "running"]
    assert trace[0]["stateRevision"] < trace[1]["stateRevision"]
    assert not _approve_claude_permission(
        {"tool_name": "Write", "tool_input": {"file_path": "/etc/passwd"}},
        agent, tmp_path,
    )
    assert not _approve_claude_permission(
        {"tool_name": "Bash", "tool_input": {"command": "curl example.com"}},
        agent, tmp_path,
    )
    assert len(io.requests) == 1


def test_a_long_turn_is_written_once_not_once_per_tool_call(tmp_path):
    """#1654: each commit appends the whole session, so per-event commits were quadratic."""
    storage = SessionStorage(tmp_path / "station" / "session_results.jsonl")
    station = claude_station.ClaudeStation(tmp_path, storage)
    station._on_fact({"hook_event_name": "SessionStart", "session_id": "abc"})
    written = len(storage.path.read_text().splitlines())
    station._on_fact({"hook_event_name": "UserPromptSubmit"})
    for index in range(200):
        for kind in ("PreToolUse", "PostToolUse"):
            station._on_fact({
                "hook_event_name": kind, "tool_name": "Bash", "tool_use_id": f"t{index}",
            })

    assert len(storage.path.read_text().splitlines()) == written
    live, _ = station.events_since(0)
    assert sum(event["type"] == "provider_activity" for event in live) == 400

    station._on_fact({"hook_event_name": "Stop"})

    assert len(storage.path.read_text().splitlines()) == written + 1
    trace = storage.get(station.session_id).session["trace"]
    assert sum(event["type"] == "provider_activity" for event in trace) == 400
    assert trace[-1]["status"] == "completed"


def test_browser_started_turns_route_every_claude_permission_to_the_owner(tmp_path, monkeypatch):
    """1.8.8b4 promised owner approval for edits and refusal for shell commands.

    Claude's native `auto` lets its own classifier run Bash without ever asking
    our PermissionRequest Hook, so a Station turn must launch in the manual
    (`default`) mode whatever the Host ceiling or a Work Room pick says.
    """
    import json

    import connectonion.plugins.coding_agents as coding_agents

    seen = []

    def fake_claude(**kwargs):
        seen.append(kwargs["permission_mode"])
        return json.dumps({"provider": "claude_code", "exit_code": 0})

    monkeypatch.setattr(coding_agents, "run_co_claude", fake_claude)
    plugin = claude_station.station_claude_plugin(tmp_path)
    for session in (
        {"mode": "auto"},
        {"mode": "full-access", "turns_left": 3},
        {
            "mode": "full-access", "turns_left": 3,
            "_provider_workroom_id": "room-1",
            "_provider_permission_options": {"room-1": "claude:bypass-permissions"},
        },
    ):
        agent = SimpleNamespace(
            current_session={"_active_tool_call_id": "call-1", **session},
            io=SimpleNamespace(log=lambda *a, **k: None),
        )
        plugin.claude_code("continue", cwd=str(tmp_path), agent=agent)

    assert seen == ["default", "default", "default"]


def test_station_does_not_advertise_selectable_permission_profiles():
    agent = SimpleNamespace(current_session={"mode": "auto"})

    assert _provider_permission_for_event(
        agent, "claude_code", "claude_code:station:session-1", 1,
    ) is None


_NO_TRANSCRIPT = "Claude SessionStart did not provide an absolute transcript path."


def _terminal_without_transcript(**options):
    raise ValueError(_NO_TRANSCRIPT)


def test_a_failed_terminal_closes_the_work_room_and_voids_the_pairing_code(tmp_path, monkeypatch):
    storage = SessionStorage(tmp_path / "station" / "session_results.jsonl")
    station = claude_station.ClaudeStation(tmp_path, storage)
    monkeypatch.setattr(claude_station, "run_interactive_claude", _terminal_without_transcript)
    try:
        station.run()
    except claude_station.StationFailed as failure:
        assert str(failure) == _NO_TRANSCRIPT
    else:
        raise AssertionError("the station reported success")
    assert storage.get(station.session_id).status == "done"
    # The code was printed to the terminal; nothing is left for it to pair with.
    assert station.attach("0xowner", station.pairing_code)["accepted"] is False


def test_share_mode_fails_with_the_same_clean_line_as_no_share(tmp_path, monkeypatch):
    """With share on, a SessionStart without a transcript path printed a Work
    Room link, a pairing code and then a full Rich traceback ending
    `RuntimeError: Claude Station terminal failed`; --no-share printed one line."""
    import re

    from typer.testing import CliRunner

    from connectonion.cli.main import app

    monkeypatch.setattr(claude_station, "run_interactive_claude", _terminal_without_transcript)
    monkeypatch.setattr(claude_station, "host", lambda **kwargs: None)
    result = CliRunner().invoke(app, ["claude", "--cwd", str(tmp_path)])
    output = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert result.exit_code == 1
    assert f"co claude: {_NO_TRANSCRIPT}" in output
    assert "Traceback" not in output and "RuntimeError" not in output
    assert not isinstance(result.exception, RuntimeError)
