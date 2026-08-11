"""ACP session/cancel over the authenticated Host carrier."""

from copy import deepcopy
from unittest.mock import AsyncMock, Mock

import pytest

from connectonion.core.acp_wire import (
    ACP_SCHEMA_VERSION,
    legacy_interrupt_from_acp_cancel,
)
from connectonion.network.io import WebSocketIO

SESSION_ID = "session-cancel"


def cancel_frame(session_id=SESSION_ID):
    return {
        "type": "ACP_NOTIFICATION",
        "acpSchema": ACP_SCHEMA_VERSION,
        "message": {
            "jsonrpc": "2.0",
            "method": "session/cancel",
            "params": {"sessionId": session_id},
        },
    }


def test_exact_cancel_maps_to_the_existing_interrupt_lifecycle():
    assert legacy_interrupt_from_acp_cancel(
        cancel_frame(), expected_session_id=SESSION_ID
    ) == {"type": "INTERRUPT"}


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda frame: frame.update(acpSchema="schema-v9"), "schema"),
        (lambda frame: frame["message"].update(jsonrpc="1.0"), "jsonrpc"),
        (lambda frame: frame["message"].update(method="session/update"), "method"),
        (lambda frame: frame["message"].update(id="request-not-notification"), "notification"),
        (lambda frame: frame["message"]["params"].update(sessionId="other"), "another session"),
        (lambda frame: frame["message"]["params"].update(sessionId=7), "string"),
    ],
)
def test_malformed_or_cross_session_cancel_fails_closed(mutate, message):
    frame = deepcopy(cancel_frame())
    mutate(frame)

    with pytest.raises(ValueError, match=message):
        legacy_interrupt_from_acp_cancel(
            frame, expected_session_id=SESSION_ID
        )


def test_one_io_generation_accepts_one_interrupt_but_the_next_is_fresh():
    first = WebSocketIO()
    assert first.request_interrupt() is True
    assert first.request_interrupt() is False
    assert first.receive_all() == [{"type": "INTERRUPT"}]
    assert first.request_interrupt() is False
    assert first.receive_all() == []

    second = WebSocketIO()
    assert second.request_interrupt() is True
    assert second.receive_all() == [{"type": "INTERRUPT"}]


async def run_cancel(monkeypatch, *frames, active=True):
    from connectonion.network.host.ws_router import session as ws_session

    io = WebSocketIO()
    queue = [{"type": "CONNECT"}, *frames]
    sent = []

    async def fake_connect(data, send_msg, conn, *args):
        conn.update(
            authenticated=True,
            agent_address="operator",
            session_id=SESSION_ID,
        )
        return (io, None) if active else None

    async def recv_msg():
        return queue.pop(0) if queue else None

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
async def test_dispatch_delivers_repeated_acp_cancel_once(monkeypatch):
    mailbox, sent = await run_cancel(
        monkeypatch, cancel_frame(), cancel_frame()
    )

    assert mailbox == [{"type": "INTERRUPT"}]
    assert sent == []


@pytest.mark.asyncio
async def test_dispatch_keeps_legacy_interrupt_but_makes_it_one_shot(monkeypatch):
    mailbox, sent = await run_cancel(
        monkeypatch, {"type": "INTERRUPT"}, {"type": "INTERRUPT"}
    )

    assert mailbox == [{"type": "INTERRUPT"}]
    assert sent == []


@pytest.mark.asyncio
async def test_dispatch_rejects_cross_session_cancel_without_interrupt(monkeypatch):
    mailbox, sent = await run_cancel(monkeypatch, cancel_frame("other"))

    assert mailbox == []
    assert sent[0]["type"] == "ERROR"
    assert "another session" in sent[0]["message"]


@pytest.mark.asyncio
async def test_dispatch_rejects_cancel_without_an_active_turn(monkeypatch):
    mailbox, sent = await run_cancel(
        monkeypatch, cancel_frame(), active=False
    )

    assert mailbox == []
    assert sent == [{
        "type": "ERROR",
        "message": "ACP cancel requires an active turn",
    }]


@pytest.mark.asyncio
async def test_connected_advertises_the_cancel_adapter(tmp_path, monkeypatch):
    from connectonion.network.host.ws_router.connect import establish_connection

    monkeypatch.chdir(tmp_path)
    sent = []
    storage = Mock()
    storage.get.return_value = None
    registry = Mock()
    registry.get.return_value = None

    await establish_connection(
        {},
        "0xoperator",
        AsyncMock(side_effect=lambda message: sent.append(message)),
        {},
        storage,
        registry,
    )

    connected = next(message for message in sent if message["type"] == "CONNECTED")
    assert connected["carrier_capabilities"] == {
        "acp": {
            "schema": "schema-v1.19.0",
            "client_notifications": ["session/cancel"],
        }
    }
