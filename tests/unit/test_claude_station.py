"""A paired browser may take and release the exact terminal Claude session."""

import threading
import time
from types import SimpleNamespace

from connectonion.cli.co_ai import claude_station
from connectonion.network.host.http_router import session_handler, sessions_handler
from connectonion.network.host.session.storage import SessionStorage, session_owner
from connectonion.network.host.session.ui import session_to_chat_items
from connectonion.useful_tools.claude_code import _approve_claude_permission


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

        def request_approval(self, tool, arguments, *, context):
            self.requests.append((tool, arguments, context))
            return True

    io = ApprovalIO()
    agent = SimpleNamespace(
        io=io,
        current_session={
            "requester": {"address": "0xowner", "level": "admin"},
            "_active_tool_call_id": "task-1",
        },
    )
    edit = {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "note.txt")}}
    assert _approve_claude_permission(edit, agent, tmp_path)
    assert io.requests[0][2]["providerApproval"]["files"] == ["note.txt"]
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
