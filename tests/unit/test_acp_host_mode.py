"""Authoritative ACP Host mode notifications and compatibility readers."""

from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from connectonion.core.acp_wire import (
    acp_notification_frame,
    legacy_stream_event_from_acp,
)
from connectonion.network.connect import RemoteAgent
from connectonion.network.host.ws_router.agent_io import (
    forward_agent_msgs_to_client,
)
from connectonion.network.io import WebSocketIO

SESSION_ID = "session-mode-881"


def mode_frame(mode: str, session_id: str = SESSION_ID) -> dict:
    return {
        "type": "ACP_NOTIFICATION",
        "acpSchema": "schema-v1.19.0",
        "message": {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": session_id,
                "update": {
                    "currentModeId": mode,
                    "sessionUpdate": "current_mode_update",
                },
            },
        },
    }


@pytest.mark.parametrize("mode", [":read-only", ":workspace", ":danger-full-access"])
def test_host_serializes_exact_acp_mode_updates(mode):
    event = {"type": "mode_changed", "mode": mode}
    original = deepcopy(event)

    assert acp_notification_frame(event, SESSION_ID) == mode_frame(mode)
    assert event == original


@pytest.mark.parametrize("mode", ["plan", "future", "", None, 1])
def test_host_rejects_non_authoritative_output_modes(mode):
    with pytest.raises(ValueError, match="Unsupported permission profile"):
        acp_notification_frame(
            {"type": "mode_changed", "mode": mode}, SESSION_ID
        )


def test_python_decoder_binds_mode_to_the_active_session():
    assert legacy_stream_event_from_acp(
        mode_frame(":workspace"), expected_session_id=SESSION_ID
    ) == {"type": "mode_changed", "mode": ":workspace"}

    with pytest.raises(ValueError, match="another session"):
        legacy_stream_event_from_acp(
            mode_frame(":danger-full-access", "other-session"),
            expected_session_id=SESSION_ID,
        )


def test_python_remote_agent_deduplicates_acp_and_legacy_mode_output():
    agent = RemoteAgent("0xabc")
    agent._current_session = {
        "session_id": SESSION_ID,
        "mode": ":read-only",
        "turn": 4,
    }

    agent._handle_stream_event(mode_frame(":danger-full-access"))
    agent._handle_stream_event({
        "type": "mode_changed",
        "mode": ":danger-full-access",
        "session_id": SESSION_ID,
    })

    assert agent.current_session == {
        "session_id": SESSION_ID,
        "mode": ":danger-full-access",
        "turn": 4,
    }
    assert agent.ui == []


@pytest.mark.parametrize(
    "event",
    [
        mode_frame(":danger-full-access", "other-session"),
        {"type": "mode_changed", "mode": "future"},
        {
            "type": "mode_changed",
            "mode": ":danger-full-access",
            "session_id": "other-session",
        },
    ],
)
def test_python_remote_agent_ignores_unowned_or_unknown_modes(event):
    agent = RemoteAgent("0xabc")
    agent._current_session = {"session_id": SESSION_ID, "mode": ":read-only"}

    agent._handle_stream_event(event)

    assert agent.current_session["mode"] == ":read-only"


@pytest.mark.asyncio
async def test_host_dual_writes_mode_in_order():
    io = WebSocketIO()
    sent = []

    async def send(message):
        sent.append(message)

    io.send({"type": "mode_changed", "mode": ":workspace"})
    io.mark_agent_done()

    await asyncio.wait_for(
        forward_agent_msgs_to_client(
            send,
            io,
            SESSION_ID,
            result_holder=[{
                "result": "done",
                "duration_ms": 1,
                "session": {},
            }],
        ),
        timeout=2,
    )

    assert [message["type"] for message in sent[:2]] == [
        "ACP_NOTIFICATION",
        "mode_changed",
    ]
    assert sent[0] == mode_frame(":workspace")
    assert sent[1]["type"] == "mode_changed"
    assert sent[1]["mode"] == ":workspace"
    assert sent[1]["session_id"] == SESSION_ID


@pytest.mark.asyncio
async def test_bad_mode_mirror_preserves_legacy_and_output():
    io = WebSocketIO()
    sent = []

    async def send(message):
        sent.append(message)

    io.send({"type": "mode_changed", "mode": "plan"})
    io.mark_agent_done()

    await forward_agent_msgs_to_client(
        send,
        io,
        SESSION_ID,
        result_holder=[{
            "result": "done",
            "duration_ms": 1,
            "session": {},
        }],
    )

    assert [message["type"] for message in sent[:2]] == [
        "mode_changed",
        "OUTPUT",
    ]
    assert sent[0]["mode"] == "plan"
