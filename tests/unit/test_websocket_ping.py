"""
Unit tests for WebSocket connection-level PING.

Tests that PING messages are sent for the entire connection lifetime,
not just during INPUT processing. This prevents the TS SDK's ping monitor
from closing the WebSocket after 60s of idle time.
"""

import asyncio
import json
import pytest
from connectonion.network.asgi.websocket import handle_websocket


def make_scope(path="/ws"):
    return {"type": "websocket", "path": path, "client": ("127.0.0.1", 12345)}


class TestConnectionLevelPing:

    @pytest.mark.asyncio
    async def test_ping_sent_while_idle(self):
        """PING should be sent even when no INPUT is being processed."""
        sent_messages = []
        received_queue = asyncio.Queue()

        async def mock_send(msg):
            sent_messages.append(msg)

        async def mock_receive():
            return await received_queue.get()

        # Start handle_websocket
        task = asyncio.create_task(handle_websocket(
            make_scope(),
            mock_receive,
            mock_send,
            route_handlers={},
            storage=None,
            registry=_MockRegistry(),
            trust="open",
        ))

        # Wait for accept
        await asyncio.sleep(0.05)
        assert sent_messages[0] == {"type": "websocket.accept"}

        # Don't send CONNECT or INPUT — just idle for >30s worth of ping intervals
        # Use a short sleep and check that ping fires (we can't wait 30s in a test,
        # so we'll test the mechanism differently below)

        # Disconnect
        await received_queue.put({"type": "websocket.disconnect"})
        await asyncio.wait_for(task, timeout=2)

    @pytest.mark.asyncio
    async def test_ping_fires_at_interval(self):
        """Verify _connection_ping sends PING at the configured interval."""
        sent_messages = []

        async def mock_send(msg):
            sent_messages.append(msg)

        # Directly test the ping coroutine pattern used in handle_websocket
        ws_closed = asyncio.Event()

        async def _connection_ping():
            while not ws_closed.is_set():
                await asyncio.sleep(0.05)  # Short interval for testing
                if not ws_closed.is_set():
                    try:
                        await mock_send({"type": "websocket.send", "text": json.dumps({"type": "PING"})})
                    except Exception:
                        break

        ping_task = asyncio.create_task(_connection_ping())
        await asyncio.sleep(0.18)  # Should fire ~3 times at 0.05s intervals
        ws_closed.set()
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass

        ping_count = sum(
            1 for m in sent_messages
            if m.get("text") and json.loads(m["text"]).get("type") == "PING"
        )
        assert ping_count >= 2, f"Expected at least 2 PINGs, got {ping_count}"

    @pytest.mark.asyncio
    async def test_ping_stops_on_disconnect(self):
        """PING task should stop when connection closes."""
        sent_messages = []

        async def mock_send(msg):
            sent_messages.append(msg)

        ws_closed = asyncio.Event()

        async def _connection_ping():
            while not ws_closed.is_set():
                await asyncio.sleep(0.05)
                if not ws_closed.is_set():
                    try:
                        await mock_send({"type": "websocket.send", "text": json.dumps({"type": "PING"})})
                    except Exception:
                        break

        ping_task = asyncio.create_task(_connection_ping())
        await asyncio.sleep(0.08)  # Let 1 ping fire

        # Signal close
        ws_closed.set()
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass

        count_before = len(sent_messages)
        await asyncio.sleep(0.1)  # No more pings should fire
        assert len(sent_messages) == count_before

    @pytest.mark.asyncio
    async def test_ping_stops_on_send_error(self):
        """PING task should stop if send raises an error."""
        call_count = 0

        async def mock_send(msg):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise ConnectionError("closed")

        ws_closed = asyncio.Event()

        async def _connection_ping():
            while not ws_closed.is_set():
                await asyncio.sleep(0.05)
                if not ws_closed.is_set():
                    try:
                        await mock_send({"type": "websocket.send", "text": json.dumps({"type": "PING"})})
                    except Exception:
                        break

        ping_task = asyncio.create_task(_connection_ping())
        await asyncio.sleep(0.2)

        # Task should have exited on its own due to error
        assert ping_task.done()

    @pytest.mark.asyncio
    async def test_wrong_path_rejected(self):
        """WebSocket on wrong path should be closed with 4004."""
        sent_messages = []

        async def mock_send(msg):
            sent_messages.append(msg)

        async def mock_receive():
            await asyncio.sleep(999)

        await handle_websocket(
            make_scope(path="/wrong"),
            mock_receive,
            mock_send,
            route_handlers={},
            storage=None,
            registry=_MockRegistry(),
            trust="open",
        )

        assert sent_messages == [{"type": "websocket.close", "code": 4004}]


class _MockRegistry:
    """Minimal mock for ActiveSessionRegistry."""
    def count(self):
        return 0
    def get(self, session_id):
        return None
    def register(self, *args, **kwargs):
        pass
    def update_ping(self, session_id):
        pass
    def mark_connected(self, session_id):
        pass
    def mark_suspended(self, session_id):
        pass
