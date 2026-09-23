"""Opt-in Haiku acceptance for the Host-owned co claude OIP path."""

import json
import shutil
from types import SimpleNamespace

import pytest

from connectonion.plugins.coding_agents import ClaudeCodePlugin

pytestmark = [pytest.mark.real_api, pytest.mark.provider_cli]


class RecordedIO:
    def __init__(self):
        self.events = []

    def log(self, kind, **fields):
        self.events.append({"type": kind, **fields})


@pytest.mark.skipif(not shutil.which("claude"), reason="Claude CLI not installed")
def test_host_claude_session_and_followup_emit_oip(tmp_path):
    io = RecordedIO()
    agent = SimpleNamespace(
        current_session={
            "_active_tool_call_id": "haiku-first",
            "mode": "read-only",
            "requester": {"address": "0xacceptance", "level": "admin"},
        },
        io=io,
    )
    plugin = ClaudeCodePlugin(workspace=tmp_path, use_host_permissions=True)
    first = json.loads(plugin.claude_code(
        "Reply with exactly CO_CLAUDE_OIP_FIRST_OK and do not use tools.",
        cwd=str(tmp_path), model="haiku", timeout=120, agent=agent,
    ))
    assert first["status"] == "completed", first["error"]
    assert "CO_CLAUDE_OIP_FIRST_OK" in first["result"]

    agent.current_session["_active_tool_call_id"] = "haiku-followup"
    second = json.loads(plugin.claude_code(
        "Reply with exactly CO_CLAUDE_OIP_RESUME_OK and do not use tools.",
        cwd=str(tmp_path), session_id=first["session_id"], model="haiku",
        timeout=120, agent=agent,
    ))
    assert second["status"] == "completed", second["error"]
    assert second["session_id"] == first["session_id"]
    assert "CO_CLAUDE_OIP_RESUME_OK" in second["result"]
    assert sum(event["type"] == "provider_invocation" for event in io.events) == 4
    assert any(
        event["type"] == "provider_message"
        and event.get("role") == "assistant"
        and "CO_CLAUDE_OIP_RESUME_OK" in event.get("text", "")
        for event in io.events
    )
    assert "transcript_path" not in json.dumps(io.events)
