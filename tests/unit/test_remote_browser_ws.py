"""OIP transport and authorization tests for Remote Browser."""

import asyncio

import pytest

from connectonion.network.host.server import _make_remote_browser
from connectonion.network.host.ws_router.remote_browser import run_remote_browser


class FakeTrust:
    def __init__(self, level="contact", admin=False):
        self.level = level
        self.admin = admin

    def is_admin(self, address):
        return self.admin

    def get_level(self, address):
        return self.level


class RecordingService:
    def __init__(self):
        self.calls = []

    def handle(self, request, *, owner, transport):
        self.calls.append((request, owner, transport))
        if transport != "direct":
            return {
                "schema_version": "1",
                "ok": False,
                "command": "remote-browser.status",
                "request_id": request["request_id"],
                "code": "SECURE_CHANNEL_UNAVAILABLE",
                "message": "secure channel unavailable",
            }
        return {
            "schema_version": "1",
            "ok": True,
            "command": "remote-browser.status",
            "request_id": request["request_id"],
            "result": {},
        }


def test_contact_direct_request_uses_authenticated_owner():
    service = RecordingService()
    handler = _make_remote_browser(service, FakeTrust())
    request = {"request_id": "req-1", "command": "status"}

    result = handler(request, "0xauthenticated", "direct")

    assert result["ok"] is True
    assert service.calls == [(request, "0xauthenticated", "direct")]


def test_stranger_is_rejected_before_browser_service():
    service = RecordingService()
    handler = _make_remote_browser(service, FakeTrust(level="stranger"))

    result = handler({"request_id": "req-2"}, "0xstranger", "direct")

    assert result["code"] == "FORBIDDEN"
    assert service.calls == []


def test_relay_reaches_service_as_relay_and_fails_closed():
    service = RecordingService()
    handler = _make_remote_browser(service, FakeTrust())
    request = {"request_id": "req-3", "command": "status"}

    result = handler(request, "0xowner", "relay")

    assert result["code"] == "SECURE_CHANNEL_UNAVAILABLE"
    assert service.calls == [(request, "0xowner", "relay")]


@pytest.mark.asyncio
async def test_router_returns_stable_result_frame():
    sent = []

    async def send(message):
        sent.append(message)

    service = RecordingService()
    handler = _make_remote_browser(service, FakeTrust())
    await run_remote_browser(
        {"type": "REMOTE_BROWSER", "request_id": "req-4", "command": "status"},
        send,
        {"remote_browser": handler},
        requester_address="0xowner",
        transport="direct",
    )

    assert sent[0]["type"] == "REMOTE_BROWSER_RESULT"
    assert sent[0]["request_id"] == "req-4"
    assert sent[0]["ok"] is True


@pytest.mark.asyncio
async def test_session_dispatch_uses_connection_identity(monkeypatch):
    from connectonion.network.host.ws_router import session

    result_sent = asyncio.Event()
    sent = []
    frames = [
        {"type": "CONNECT", "from": "0xowner"},
        {"type": "REMOTE_BROWSER", "request_id": "req-5", "command": "sessions"},
    ]

    async def fake_connect(data, send, conn, *args):
        conn.update(
            authenticated=True,
            agent_address="0xowner",
            signed_commands=False,
            session_id="oip-session",
        )

    async def recv():
        if frames:
            return frames.pop(0)
        await result_sent.wait()
        return None

    async def send(message):
        sent.append(message)
        if message.get("type") == "REMOTE_BROWSER_RESULT":
            result_sent.set()

    service = RecordingService()
    monkeypatch.setattr(session, "handle_connect", fake_connect)
    await session.run_ws_session(
        send,
        recv,
        route_handlers={
            "remote_browser": _make_remote_browser(service, FakeTrust()),
        },
        storage=None,
        registry=None,
        trust=None,
        enable_ping=False,
        transport="direct",
    )

    assert sent[-1]["type"] == "REMOTE_BROWSER_RESULT"
    assert service.calls[0][1:] == ("0xowner", "direct")


@pytest.mark.asyncio
async def test_session_executes_signed_payload_not_tampered_top_level(monkeypatch):
    from connectonion import address
    from connectonion.network.connect import RemoteAgent
    from connectonion.network.host.ws_router import session

    keys = address.generate()
    host = "0x" + "12" * 20
    signed = RemoteAgent(host, keys=keys)._build_command_message(
        {
            "type": "REMOTE_BROWSER",
            "request_id": "req-signed",
            "command": "sessions",
            "args": {},
        }
    )
    signed["command"] = "stop"
    frames = [{"type": "CONNECT", "from": keys["address"]}, signed]
    result_sent = asyncio.Event()
    sent = []

    async def fake_connect(data, send, conn, *args):
        conn.update(
            authenticated=True,
            agent_address=keys["address"],
            signed_commands=True,
            recipient_address=host,
            session_id="oip-session",
        )

    async def recv():
        if frames:
            return frames.pop(0)
        await result_sent.wait()
        return None

    async def send(message):
        sent.append(message)
        if message.get("type") == "REMOTE_BROWSER_RESULT":
            result_sent.set()

    service = RecordingService()
    monkeypatch.setattr(session, "handle_connect", fake_connect)
    await session.run_ws_session(
        send,
        recv,
        route_handlers={
            "remote_browser": _make_remote_browser(service, FakeTrust()),
        },
        storage=None,
        registry=None,
        trust=None,
        enable_ping=False,
        transport="direct",
    )

    assert sent[-1]["type"] == "REMOTE_BROWSER_RESULT"
    assert service.calls[0][0]["command"] == "sessions"
