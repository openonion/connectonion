"""ACP-native Host wire notifications and rolling-upgrade decoding."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from connectonion.core.acp_wire import (
    acp_notification_frame,
    legacy_tool_event_from_acp,
    map_message_event,
)
from connectonion.network.connect import RemoteAgent

FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "acp_tool_events.json").read_text()
)
MESSAGE_FIXTURE = json.loads(
    (
        Path(__file__).parents[1]
        / "fixtures"
        / "acp_agent_message_events.json"
    ).read_text()
)


def test_tool_events_match_the_shared_acp_fixture():
    actual = [
        acp_notification_frame(event, "session-1")
        for event in FIXTURE["legacy"]
    ]

    assert actual == FIXTURE["acp"]


def test_agent_messages_match_the_shared_acp_fixture():
    actual = [
        acp_notification_frame(event, "session-1")
        for event in MESSAGE_FIXTURE["legacy"]
    ]

    assert actual == MESSAGE_FIXTURE["acp"]


@pytest.mark.parametrize(
    "event",
    [
        {"type": "assistant", "id": "", "content": "answer"},
        {"type": "assistant", "id": "message-2", "content": ""},
        {"type": "assistant", "id": "message-2", "content": None},
    ],
)
def test_empty_or_malformed_agent_messages_are_rejected(event):
    with pytest.raises(ValueError):
        map_message_event(event)


def test_acp_tool_events_decode_to_the_legacy_python_ui_shape():
    decoded = [legacy_tool_event_from_acp(event) for event in FIXTURE["acp"]]

    assert decoded == [
        {
            "type": "tool_call",
            "tool_id": "call-1",
            "name": "search_docs",
            "args": {"query": "ACP"},
            "status": "in_progress",
        },
        {
            "type": "tool_call_update",
            "tool_id": "call-1",
            "status": "completed",
            "result": "2 matches",
            "timing_ms": 42,
        },
    ]


def test_python_remote_agent_renders_one_card_during_a_rolling_upgrade():
    agent = RemoteAgent("0xabc")
    for event in [*FIXTURE["legacy"], *FIXTURE["acp"]]:
        agent._handle_stream_event(event)

    assert agent.ui == [{
        "type": "tool_call",
        "id": None,
        "tool_id": "call-1",
        "name": "search_docs",
        "args": {"query": "ACP"},
        "status": "done",
        "result": "2 matches",
        "timing_ms": 42,
    }]


def test_python_decoder_accepts_partial_and_content_free_updates():
    partial = json.loads(json.dumps(FIXTURE["acp"][1]))
    partial["message"]["params"]["update"] = {
        "toolCallId": "call-1",
        "title": "searching",
        "status": "in_progress",
        "sessionUpdate": "tool_call_update",
    }
    completed = json.loads(json.dumps(partial))
    completed["message"]["params"]["update"] = {
        "toolCallId": "call-1",
        "status": "completed",
        "sessionUpdate": "tool_call_update",
    }

    assert legacy_tool_event_from_acp(partial) == {
        "type": "tool_call_update",
        "tool_id": "call-1",
        "name": "searching",
        "status": "in_progress",
    }
    assert legacy_tool_event_from_acp(completed) == {
        "type": "tool_call_update",
        "tool_id": "call-1",
        "status": "completed",
    }


def test_python_remote_agent_applies_partial_acp_updates():
    agent = RemoteAgent("0xabc")
    partial = json.loads(json.dumps(FIXTURE["acp"][1]))
    partial["message"]["params"]["update"] = {
        "toolCallId": "call-1",
        "title": "searching",
        "status": "in_progress",
        "sessionUpdate": "tool_call_update",
    }
    completed = json.loads(json.dumps(partial))
    completed["message"]["params"]["update"] = {
        "toolCallId": "call-1",
        "status": "completed",
        "sessionUpdate": "tool_call_update",
    }

    for event in (FIXTURE["acp"][0], partial, completed):
        agent._handle_stream_event(event)

    assert agent.ui[0]["name"] == "searching"
    assert agent.ui[0]["status"] == "done"
    assert "result" not in agent.ui[0]


def test_non_tool_events_stay_in_the_connectonion_namespace():
    event = {"type": "thinking", "content": "checking"}

    assert acp_notification_frame(event, "session-1") is None
    assert legacy_tool_event_from_acp(event) is None


def test_python_remote_agent_ignores_a_malformed_acp_carrier():
    agent = RemoteAgent("0xabc")
    malformed = json.loads(json.dumps(FIXTURE["acp"][0]))
    malformed["acpSchema"] = "schema-v9.0.0"

    agent._handle_stream_event(malformed)

    assert agent.ui == []


def test_python_remote_agent_fails_an_unknown_terminal_status_closed():
    agent = RemoteAgent("0xabc")
    unknown = json.loads(json.dumps(FIXTURE["acp"][1]))
    unknown["message"]["params"]["update"]["status"] = "future"

    agent._handle_stream_event(FIXTURE["acp"][0])
    agent._handle_stream_event(unknown)

    assert agent.ui[0]["status"] == "error"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda frame: frame.update(acpSchema="schema-v9.0.0"),
        lambda frame: frame["message"].update(jsonrpc="1.0"),
        lambda frame: frame["message"].update(method="session/prompt"),
        lambda frame: frame["message"]["params"]["update"].pop(
            "toolCallId"
        ),
    ],
)
def test_malformed_or_unknown_acp_tool_updates_fail_closed(mutation):
    frame = json.loads(json.dumps(FIXTURE["acp"][1]))
    mutation(frame)

    with pytest.raises(ValueError):
        legacy_tool_event_from_acp(frame)
