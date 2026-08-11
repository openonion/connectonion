"""ACP permission requests on the authenticated Host carrier."""

from __future__ import annotations

import copy

import pytest

from connectonion.core.acp_wire import acp_permission_request_frame
from connectonion.network.host.ws_router.agent_io import (
    forward_agent_msgs_to_client,
)
from connectonion.network.io import WebSocketIO

SESSION_ID = "session-1"
REQUEST_ID = "approval-event-1"
TOOL_CALL_ID = "call-1"


def approval_event() -> dict:
    return {
        "type": "approval_needed",
        "id": REQUEST_ID,
        "tool_call_id": TOOL_CALL_ID,
        "tool": "Bash(npm test)",
        "arguments": {"command": "npm test"},
        "description": "Run the test suite",
    }


def selected_response(
    option_id: str,
    *,
    request_id: str = REQUEST_ID,
    session_id: str = SESSION_ID,
    feedback: str | None = None,
) -> dict:
    result: dict = {
        "outcome": {"outcome": "selected", "optionId": option_id}
    }
    if feedback is not None:
        result["_meta"] = {"connectonion": {"feedback": feedback}}
    return {
        "type": "ACP_RESPONSE",
        "acpSchema": "schema-v1.19.0",
        "sessionId": session_id,
        "message": {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        },
    }


def test_permission_request_uses_the_exact_pinned_acp_shape():
    assert acp_permission_request_frame(approval_event(), SESSION_ID) == {
        "type": "ACP_REQUEST",
        "acpSchema": "schema-v1.19.0",
        "message": {
            "jsonrpc": "2.0",
            "id": REQUEST_ID,
            "method": "session/request_permission",
            "params": {
                "sessionId": SESSION_ID,
                "toolCall": {
                    "toolCallId": TOOL_CALL_ID,
                    "title": "Bash(npm test)",
                    "status": "pending",
                    "rawInput": {"command": "npm test"},
                },
                "options": [
                    {
                        "optionId": "allow_once",
                        "name": "Allow this call",
                        "kind": "allow_once",
                    },
                    {
                        "optionId": "allow_session",
                        "name": "Allow for this session",
                        "kind": "allow_always",
                    },
                    {
                        "optionId": "reject_soft",
                        "name": "Reject this call and continue",
                        "kind": "reject_once",
                    },
                    {
                        "optionId": "reject_hard",
                        "name": "Reject and stop this turn",
                        "kind": "reject_once",
                    },
                    {
                        "optionId": "reject_explain",
                        "name": "Reject and explain first",
                        "kind": "reject_once",
                    },
                ],
            },
        },
    }


@pytest.mark.parametrize(
    "field",
    ["id", "tool_call_id", "tool", "arguments"],
)
def test_permission_request_rejects_missing_identity_or_input(field):
    event = approval_event()
    event.pop(field)

    with pytest.raises((TypeError, ValueError)):
        acp_permission_request_frame(event, SESSION_ID)


@pytest.mark.asyncio
async def test_host_sends_acp_request_before_the_legacy_fallback():
    io = WebSocketIO()
    sent: list[dict] = []
    event = approval_event()

    async def send(message):
        sent.append(copy.deepcopy(message))

    io.send(event)
    io.mark_agent_done()
    await forward_agent_msgs_to_client(send, io, SESSION_ID)

    assert [message["type"] for message in sent[:2]] == [
        "ACP_REQUEST",
        "approval_needed",
    ]
    assert sent[0]["message"]["id"] == sent[1]["id"] == REQUEST_ID


@pytest.mark.parametrize(
    ("option_id", "expected"),
    [
        ("allow_once", {"approved": True, "scope": "once"}),
        ("allow_session", {"approved": True, "scope": "session"}),
        (
            "reject_soft",
            {
                "approved": False,
                "scope": "once",
                "mode": "reject_soft",
                "feedback": "use the smaller command",
            },
        ),
        (
            "reject_hard",
            {"approved": False, "scope": "once", "mode": "reject_hard"},
        ),
        (
            "reject_explain",
            {
                "approved": False,
                "scope": "once",
                "mode": "reject_explain",
                "feedback": "why is this needed?",
            },
        ),
    ],
)
def test_only_advertised_acp_options_reach_the_agent_once(option_id, expected):
    io = WebSocketIO()
    frame = acp_permission_request_frame(approval_event(), SESSION_ID)
    io.register_permission_request(approval_event(), SESSION_ID, frame)
    feedback = expected.get("feedback")

    assert io.resolve_acp_permission(
        selected_response(option_id, feedback=feedback), SESSION_ID
    ) is True
    assert io.receive_all() == [expected]
    assert io.resolve_acp_permission(
        selected_response(option_id, feedback=feedback), SESSION_ID
    ) is False
    assert io.receive_all() == []


def test_wrong_request_or_session_cannot_cross_into_the_mailbox():
    io = WebSocketIO()
    event = approval_event()
    frame = acp_permission_request_frame(event, SESSION_ID)
    io.register_permission_request(event, SESSION_ID, frame)

    assert io.resolve_acp_permission(
        selected_response("allow_once", request_id="stale"), SESSION_ID
    ) is False
    assert io.resolve_acp_permission(
        selected_response("allow_once", session_id="other"), SESSION_ID
    ) is False
    assert io.receive_all() == []

    assert io.resolve_acp_permission(
        selected_response("allow_once"), SESSION_ID
    ) is True
    assert io.receive_all() == [{"approved": True, "scope": "once"}]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda frame: frame["message"]["result"]["outcome"].update(
            optionId="manufactured_allow"
        ),
        lambda frame: frame["message"].update(jsonrpc="1.0"),
        lambda frame: frame["message"].pop("result"),
    ],
)
def test_a_matching_but_invalid_response_consumes_the_request_fail_closed(mutate):
    io = WebSocketIO()
    event = approval_event()
    frame = acp_permission_request_frame(event, SESSION_ID)
    io.register_permission_request(event, SESSION_ID, frame)
    response = selected_response("allow_once")
    mutate(response)

    assert io.resolve_acp_permission(response, SESSION_ID) is True
    assert io.receive_all() == [
        {"approved": False, "scope": "once", "mode": "reject_hard"}
    ]


def test_cancelled_response_is_a_hard_rejection():
    io = WebSocketIO()
    event = approval_event()
    frame = acp_permission_request_frame(event, SESSION_ID)
    io.register_permission_request(event, SESSION_ID, frame)
    response = selected_response("allow_once")
    response["message"]["result"] = {"outcome": {"outcome": "cancelled"}}

    assert io.resolve_acp_permission(response, SESSION_ID) is True
    assert io.receive_all() == [
        {"approved": False, "scope": "once", "mode": "reject_hard"}
    ]


def test_legacy_response_is_bound_to_the_current_request_and_consumed_once():
    io = WebSocketIO()
    event = approval_event()
    frame = acp_permission_request_frame(event, SESSION_ID)
    io.register_permission_request(event, SESSION_ID, frame)
    response = {"type": "APPROVAL_RESPONSE", "approved": True, "scope": "once"}

    assert io.resolve_legacy_permission(response) is True
    assert io.resolve_legacy_permission(response) is False
    assert io.receive_all() == [{"approved": True, "scope": "once"}]


@pytest.mark.parametrize(
    "response",
    [
        {"type": "APPROVAL_RESPONSE", "approved": "yes", "scope": "once"},
        {"type": "APPROVAL_RESPONSE", "approved": True, "scope": "forever"},
        {
            "type": "APPROVAL_RESPONSE",
            "approved": False,
            "scope": "once",
            "mode": "manufactured_mode",
        },
    ],
)
def test_malformed_legacy_answers_also_fail_closed(response):
    io = WebSocketIO()
    event = approval_event()
    frame = acp_permission_request_frame(event, SESSION_ID)
    io.register_permission_request(event, SESSION_ID, frame)

    assert io.resolve_legacy_permission(response) is True
    assert io.receive_all() == [
        {"approved": False, "scope": "once", "mode": "reject_hard"}
    ]


def test_reconnect_re_registers_the_same_request_but_not_a_second_one():
    io = WebSocketIO()
    event = approval_event()
    frame = acp_permission_request_frame(event, SESSION_ID)

    assert io.register_permission_request(event, SESSION_ID, frame) is True
    assert io.register_permission_request(event, SESSION_ID, frame) is True

    other = {**event, "id": "other"}
    other_frame = acp_permission_request_frame(other, SESSION_ID)
    assert io.register_permission_request(other, SESSION_ID, other_frame) is False


async def _run_bound_response(monkeypatch, response):
    from connectonion.network.host.ws_router import session as ws_session

    io = WebSocketIO()
    event = approval_event()
    frame = acp_permission_request_frame(event, SESSION_ID)
    io.register_permission_request(event, SESSION_ID, frame)
    sent = []
    frames = [{"type": "CONNECT"}, response]

    async def fake_connect(
        data, send_msg, conn, route_handlers, storage, registry, trust,
        blacklist, whitelist,
    ):
        conn.update(
            authenticated=True,
            agent_address="operator",
            session_id=SESSION_ID,
        )
        return io, None

    async def recv_msg():
        return frames.pop(0) if frames else None

    async def send_msg(message):
        sent.append(message)

    monkeypatch.setattr(ws_session, "handle_connect", fake_connect)
    await ws_session.run_ws_session(
        send_msg,
        recv_msg,
        route_handlers={},
        storage=None,
        registry=None,
        trust=None,
        enable_ping=False,
    )
    return io.receive_all(), sent


@pytest.mark.asyncio
async def test_session_dispatch_routes_a_bound_acp_response(monkeypatch):
    mailbox, sent = await _run_bound_response(
        monkeypatch, selected_response("allow_once")
    )

    assert mailbox == [{"approved": True, "scope": "once"}]
    assert sent == []


@pytest.mark.asyncio
async def test_session_dispatch_answers_a_stale_acp_response(monkeypatch):
    mailbox, sent = await _run_bound_response(
        monkeypatch,
        selected_response("allow_once", request_id="stale"),
    )

    assert mailbox == []
    assert sent == [{
        "type": "ERROR",
        "message": "unknown or stale ACP permission response",
    }]
