"""
PROTOTYPE test — validates the ACP client against the fake codex-acp agent.

Not part of the shipped suite (pytest testpaths=tests). Run explicitly:
    python -m pytest prototypes/codex_acp/test_acp_prototype.py -q
"""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(__file__))
from acp_client import ACPClient


def _client():
    agent = [sys.executable, os.path.join(os.path.dirname(__file__), "fake_codex_acp.py")]
    events = []
    perms = []

    def on_permission(tool_call, options):
        perms.append(tool_call.get("title"))
        return options[0]["optionId"]

    client = ACPClient(command=agent, cwd=".",
                       on_event=events.append, on_permission=on_permission)
    return client, events, perms


def test_full_flow_streams_events_and_handles_permission():
    client, events, perms = _client()
    client.start()

    info = client.initialize()
    assert info["agentInfo"]["name"] == "fake-codex-acp"

    session_id = client.new_session()
    assert session_id == "acp-thread-abc123"

    stop = client.prompt(session_id, "fix the failing tests")
    assert stop == "end_turn"

    kinds = [e["acp_update"] for e in events]
    assert kinds == [
        "agent_message_chunk", "tool_call", "tool_call_update", "agent_message_chunk",
    ]
    # the permission round-trip fired
    assert perms == ["Run `pytest -q`"]
    # tool call resolved to completed after approval
    completed = [e for e in events if e["acp_update"] == "tool_call_update"]
    assert completed[0]["status"] == "completed"
    # final assistant text delivered
    assert events[-1]["text"] == "All tests pass now."

    resumed = client.load_session(session_id)
    assert resumed == session_id
    client.close()


def test_rejecting_permission_marks_tool_failed():
    client, events, _ = _client()
    client.on_permission = lambda tc, opts: "reject"
    client.start()
    client.initialize()
    sid = client.new_session()
    client.prompt(sid, "do it")

    update = [e for e in events if e["acp_update"] == "tool_call_update"][0]
    assert update["status"] == "failed"
    assert events[-1]["text"] == "Skipped: not permitted."
    client.close()


if __name__ == "__main__":
    test_full_flow_streams_events_and_handles_permission()
    test_rejecting_permission_marks_tool_failed()
    print("ACP prototype: all checks passed")
