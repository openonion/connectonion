"""RemoteAgent's typed Remote Browser request/response contract."""

import asyncio
import json

import pytest

from connectonion import address
from connectonion.network.connect import RemoteAgent


class FakeConnection:
    def __init__(self):
        self.sent = []
        self.replies = []

    async def send(self, raw):
        frame = json.loads(raw)
        self.sent.append(frame)
        if frame["type"] == "CONNECT":
            self.replies.append({"type": "CONNECTED", "session_id": "oip-1"})
        elif frame["type"] == "REMOTE_BROWSER":
            request = frame["payload"]
            self.replies.append(
                {
                    "type": "REMOTE_BROWSER_RESULT",
                    "schema_version": "1",
                    "ok": True,
                    "command": "remote-browser.start",
                    "request_id": request["request_id"],
                    "result": {"session_id": "rb_" + "1" * 32},
                }
            )

    async def recv(self):
        return json.dumps(self.replies.pop(0))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class WaitingConnection(FakeConnection):
    def __init__(self):
        super().__init__()
        self.waiting = asyncio.Event()

    async def send(self, raw):
        frame = json.loads(raw)
        self.sent.append(frame)
        if frame["type"] == "CONNECT":
            self.replies.append({"type": "CONNECTED", "session_id": "oip-1"})

    async def recv(self):
        if self.replies:
            return json.dumps(self.replies.pop(0))
        await self.waiting.wait()


@pytest.mark.asyncio
async def test_client_signs_and_correlates_typed_remote_browser_request(monkeypatch):
    remote = RemoteAgent("0x" + "12" * 20, keys=address.generate())
    connection = FakeConnection()

    async def no_resolve():
        return None

    async def open_connection(websockets):
        return connection, True

    monkeypatch.setattr(remote, "_try_resolve_endpoint", no_resolve)
    monkeypatch.setattr(remote, "_open_best_connection", open_connection)

    result = await remote.remote_browser_async(
        "start", timeout=1, headless=True, proxy="direct"
    )

    request = connection.sent[1]
    assert request["type"] == request["payload"]["type"] == "REMOTE_BROWSER"
    assert request["payload"]["command"] == "start"
    assert request["payload"]["args"] == {"headless": True, "proxy": "direct"}
    assert request["signature"]
    assert result["ok"] is True
    assert result["request_id"] == request["payload"]["request_id"]


@pytest.mark.asyncio
async def test_connection_failure_returns_stable_error_envelope(monkeypatch):
    remote = RemoteAgent("0x" + "12" * 20, keys=address.generate())

    async def no_resolve():
        return None

    async def fail_connection(websockets):
        raise ConnectionRefusedError("host is offline")

    monkeypatch.setattr(remote, "_try_resolve_endpoint", no_resolve)
    monkeypatch.setattr(remote, "_open_best_connection", fail_connection)

    result = await remote.remote_browser_async("sessions", timeout=1)

    assert result["ok"] is False
    assert result["code"] == "CONNECTION_FAILED"
    assert result["retryable"] is True
    assert result["warnings"] == []


@pytest.mark.asyncio
async def test_response_timeout_returns_stable_error_envelope(monkeypatch):
    remote = RemoteAgent("0x" + "12" * 20, keys=address.generate())
    connection = WaitingConnection()

    async def no_resolve():
        return None

    async def open_connection(websockets):
        return connection, True

    monkeypatch.setattr(remote, "_try_resolve_endpoint", no_resolve)
    monkeypatch.setattr(remote, "_open_best_connection", open_connection)

    result = await remote.remote_browser_async("sessions", timeout=0.01)

    assert result["ok"] is False
    assert result["code"] == "TIMEOUT"
    assert result["retryable"] is True


@pytest.mark.asyncio
async def test_python_cancellation_propagates_without_becoming_a_retry(monkeypatch):
    remote = RemoteAgent("0x" + "12" * 20, keys=address.generate())
    connection = WaitingConnection()

    async def no_resolve():
        return None

    async def open_connection(websockets):
        return connection, True

    monkeypatch.setattr(remote, "_try_resolve_endpoint", no_resolve)
    monkeypatch.setattr(remote, "_open_best_connection", open_connection)
    task = asyncio.create_task(remote.remote_browser_async("sessions", timeout=60))
    while len(connection.sent) < 2:
        await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
