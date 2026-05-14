"""Unit tests for connectonion/network/host/ws_router/ping.py"""

import asyncio
import pytest

from connectonion.network.host.ws_router.ping import ping_loop


@pytest.mark.asyncio
async def test_ping_loop_sends_ping_after_sleep(monkeypatch):
    """First iteration: sleep 30s, then send PING."""
    sent = []
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        # Stop after first PING sent by raising CancelledError on second sleep
        if len(sleeps) >= 2:
            raise asyncio.CancelledError

    async def fake_send(msg):
        sent.append(msg)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await ping_loop(fake_send)

    assert sleeps[0] == 30
    assert sent == [{"type": "PING"}]


@pytest.mark.asyncio
async def test_ping_loop_continues_sending_after_each_interval(monkeypatch):
    """After three sleeps, three PINGs should have been sent."""
    sent = []
    sleeps = 0

    async def fake_sleep(seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps > 3:
            raise asyncio.CancelledError

    async def fake_send(msg):
        sent.append(msg)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await ping_loop(fake_send)

    assert len(sent) == 3
    assert all(m == {"type": "PING"} for m in sent)


@pytest.mark.asyncio
async def test_ping_loop_propagates_send_failure(monkeypatch):
    """If send_msg raises, the loop should not silently swallow — failure propagates."""

    async def fake_sleep(seconds):
        pass

    async def failing_send(msg):
        raise ConnectionError("ws closed")

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(ConnectionError, match="ws closed"):
        await ping_loop(failing_send)
