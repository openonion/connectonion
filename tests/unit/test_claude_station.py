"""A paired browser may take and release the exact terminal Claude session."""

import threading
import time
from types import SimpleNamespace

from connectonion.cli.co_ai import claude_station
from connectonion.network.host.session.storage import SessionStorage, session_owner
from connectonion.network.host.session.ui import session_to_chat_items
from connectonion.network.host.http_router import session_handler, sessions_handler
from connectonion.useful_tools.claude_code import _approve_claude_permission


def test_terminal_browser_terminal_handover(tmp_path, monkeypatch):
    native_session = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    storage = SessionStorage(tmp_path / "station" / "session_results.jsonl")
    station = claude_station.ClaudeStation(tmp_path, storage)
    assert session_handler(storage, station.session_id) is None
    assert sessions_handler(storage)["sessions"] == []
    launched = []

    def terminal(**options):
        launched.append(options["session_id"])
        options["on_private_fact"]({
            "hook_event_name": "SessionStart", "session_id": native_session,
        })
        if len(launched) == 1:
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
    assert provider["controlOwner"] == "browser"
    assert provider["controlPhase"] == "remote_controlling"
    assert station.take_control("0xowner", taken["stateRevision"])["accepted"] is False
    released = station.release_control("0xowner", taken["stateRevision"])
    assert released["accepted"] is True
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert launched == ["", native_session]


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
