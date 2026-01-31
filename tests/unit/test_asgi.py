"""Unit tests for connectonion/network/asgi.py"""

import asyncio
import json
import queue
import threading
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from connectonion.network.asgi import (
    handle_websocket,
    _pump_messages,
    create_app,
    send_json,
    read_body,
)
from connectonion.network.io import WebSocketIO


class TestWebSocketIOInASGI:
    """Test WebSocketIO used in WebSocket handling."""

    def test_integration_with_message_pump(self):
        """Test that WebSocketIO works with message pumping pattern."""
        conn = WebSocketIO()

        # Simulate agent sending events
        conn.send({"type": "thinking"})
        conn.send({"type": "tool_call", "name": "search"})

        # Should be able to drain queue
        events = []
        while not conn._outgoing.empty():
            events.append(conn._outgoing.get_nowait())

        assert len(events) == 2
        assert events[0]["type"] == "thinking"
        assert events[1]["type"] == "tool_call"

    def test_bidirectional_communication(self):
        """Test send and receive for approval flow."""
        conn = WebSocketIO()

        # Agent sends approval request
        def agent_thread():
            result = conn.request_approval("delete", {"path": "/tmp/x"})
            return result

        result_holder = [None]

        def run_agent():
            result_holder[0] = conn.request_approval("delete", {"path": "/tmp/x"})

        thread = threading.Thread(target=run_agent)
        thread.start()

        # Wait for outgoing request
        request = conn._outgoing.get(timeout=1)
        assert request["type"] == "approval_needed"
        assert request["tool"] == "delete"

        # Simulate client response
        conn._incoming.put({"approved": True})

        thread.join(timeout=1)
        assert result_holder[0] is True


@pytest.mark.asyncio
class TestPumpMessages:
    """Test _pump_messages async function."""

    async def test_sends_outgoing_messages_to_websocket(self):
        """Test that outgoing queue messages are sent to WebSocket."""
        conn = WebSocketIO()
        agent_done = threading.Event()
        sent_messages = []

        async def mock_receive():
            await asyncio.sleep(0.1)
            return {"type": "websocket.disconnect"}

        async def mock_send(msg):
            sent_messages.append(msg)

        # Put messages in queue
        conn.send({"type": "thinking"})
        conn.send({"type": "tool_call", "name": "search"})

        # Mark agent done quickly
        def mark_done():
            asyncio.get_event_loop().call_later(0.1, agent_done.set)

        threading.Thread(target=lambda: (asyncio.run(asyncio.sleep(0.05)), agent_done.set())).start()

        await asyncio.wait_for(
            _pump_messages(mock_receive, mock_send, conn, agent_done),
            timeout=2.0
        )

        # Check messages were sent
        ws_messages = [m for m in sent_messages if m.get("type") == "websocket.send"]
        assert len(ws_messages) >= 2

        # Parse the sent events
        events = [json.loads(m["text"]) for m in ws_messages]
        event_types = [e["type"] for e in events]
        assert "thinking" in event_types
        assert "tool_call" in event_types

    async def test_routes_incoming_to_connection(self):
        """Test that WebSocket messages are routed to connection incoming queue."""
        conn = WebSocketIO()
        agent_done = threading.Event()
        receive_count = [0]

        async def mock_receive():
            receive_count[0] += 1
            if receive_count[0] == 1:
                return {"type": "websocket.receive", "text": '{"approved": true}'}
            # Second call - set agent_done and return disconnect
            agent_done.set()
            return {"type": "websocket.disconnect"}

        async def mock_send(msg):
            pass

        await asyncio.wait_for(
            _pump_messages(mock_receive, mock_send, conn, agent_done),
            timeout=2.0
        )

        # Check message was routed to incoming queue
        msg = conn._incoming.get_nowait()
        assert msg["approved"] is True


    async def test_returns_true_when_client_disconnects(self):
        """Test that _pump_messages returns True when client disconnects.

        This allows the caller to skip sending OUTPUT to a closed connection.
        The result is still saved to SessionStorage by input_handler, so
        clients can fetch it via GET /sessions/{session_id} on reconnect.
        """
        conn = WebSocketIO()
        agent_done = threading.Event()

        async def mock_receive():
            # Simulate immediate disconnect
            return {"type": "websocket.disconnect"}

        async def mock_send(msg):
            pass

        # Start agent completion in background
        def complete_agent():
            import time
            time.sleep(0.05)
            agent_done.set()

        threading.Thread(target=complete_agent).start()

        # _pump_messages should return True (client disconnected)
        disconnected = await asyncio.wait_for(
            _pump_messages(mock_receive, mock_send, conn, agent_done),
            timeout=2.0
        )

        assert disconnected is True

    async def test_returns_false_when_agent_completes_normally(self):
        """Test that _pump_messages returns False when agent completes without disconnect."""
        conn = WebSocketIO()
        agent_done = threading.Event()

        async def mock_receive():
            # Keep waiting forever - client never disconnects
            # _pump_messages will cancel this task when agent completes
            await asyncio.sleep(10)
            return {"type": "websocket.disconnect"}

        async def mock_send(msg):
            pass

        # Complete agent quickly
        def complete_agent():
            import time
            time.sleep(0.05)
            agent_done.set()

        threading.Thread(target=complete_agent).start()

        disconnected = await asyncio.wait_for(
            _pump_messages(mock_receive, mock_send, conn, agent_done),
            timeout=2.0
        )

        # Agent completed before client disconnected
        assert disconnected is False


@pytest.mark.asyncio
class TestHandleWebSocket:
    """Test handle_websocket function."""

    async def test_accepts_websocket_connection(self):
        """Test that WebSocket connection is accepted."""
        scope = {"path": "/ws", "type": "websocket"}
        sent_messages = []
        storage = Mock()

        async def receive():
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent_messages.append(msg)

        handlers = {
            "auth": lambda *args, **kwargs: ("prompt", "identity", True, None),
            "ws_input": lambda storage, prompt, conn, session=None: {"result": "result", "session_id": "123", "duration_ms": 100, "session": {}},
        }

        await handle_websocket(scope, receive, send, route_handlers=handlers, storage=storage, trust="open")

        assert {"type": "websocket.accept"} in sent_messages

    async def test_rejects_non_ws_path(self):
        """Test that non-/ws paths are rejected."""
        scope = {"path": "/other", "type": "websocket"}
        sent_messages = []
        storage = Mock()

        async def receive():
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent_messages.append(msg)

        handlers = {}

        await handle_websocket(scope, receive, send, route_handlers=handlers, storage=storage, trust="open")

        close_msg = [m for m in sent_messages if m.get("type") == "websocket.close"]
        assert len(close_msg) == 1
        assert close_msg[0]["code"] == 4004

    async def test_handles_input_message(self):
        """Test that INPUT message triggers agent execution."""
        scope = {"path": "/ws", "type": "websocket"}
        sent_messages = []
        message_count = [0]
        storage = Mock()

        async def receive():
            message_count[0] += 1
            if message_count[0] == 1:
                return {
                    "type": "websocket.receive",
                    "text": json.dumps({
                        "type": "INPUT",
                        "payload": {"prompt": "hello", "timestamp": 1234567890},
                        "from": "0xtest",
                        "signature": "0xsig"
                    })
                }
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent_messages.append(msg)

        agent_called = [False]
        connection_received = [None]

        def mock_ws_input(storage, prompt, connection, session=None):
            agent_called[0] = True
            connection_received[0] = connection
            return {"result": "Agent response", "session_id": "123", "duration_ms": 100, "session": {}}

        handlers = {
            "auth": lambda *args, **kwargs: ("hello", "0xtest", True, None),
            "ws_input": mock_ws_input,
        }

        await handle_websocket(scope, receive, send, route_handlers=handlers, storage=storage, trust="open")

        assert agent_called[0] is True
        assert connection_received[0] is not None
        assert isinstance(connection_received[0], WebSocketIO)

    async def test_sends_output_after_agent_completes(self):
        """Test that OUTPUT message is sent after agent completes."""
        scope = {"path": "/ws", "type": "websocket"}
        sent_messages = []
        message_count = [0]
        storage = Mock()

        async def receive():
            message_count[0] += 1
            if message_count[0] == 1:
                return {
                    "type": "websocket.receive",
                    "text": json.dumps({"type": "INPUT", "payload": {"prompt": "test", "timestamp": 123}, "from": "0x", "signature": "0x"})
                }
            # Give time for agent to complete
            await asyncio.sleep(0.1)
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent_messages.append(msg)

        handlers = {
            "auth": lambda *args, **kwargs: ("test", "0x", True, None),
            "ws_input": lambda storage, p, c, session=None: {"result": "Expected result", "session_id": "abc-123", "duration_ms": 50, "session": {}},
        }

        await handle_websocket(scope, receive, send, route_handlers=handlers, storage=storage, trust="open")

        # Find OUTPUT message
        output_msgs = [
            m for m in sent_messages
            if m.get("type") == "websocket.send" and "OUTPUT" in m.get("text", "")
        ]
        assert len(output_msgs) >= 1

        output_data = json.loads(output_msgs[-1]["text"])
        assert output_data["type"] == "OUTPUT"
        assert output_data["result"] == "Expected result"
        assert output_data["session_id"] == "abc-123"
        assert output_data["duration_ms"] == 50

    async def test_auth_error_sends_error_message(self):
        """Test that auth errors are sent back to client."""
        scope = {"path": "/ws", "type": "websocket"}
        sent_messages = []
        message_count = [0]
        storage = Mock()

        async def receive():
            message_count[0] += 1
            if message_count[0] == 1:
                return {
                    "type": "websocket.receive",
                    "text": json.dumps({"type": "INPUT", "payload": {"prompt": "test"}, "from": "0x", "signature": "0x"})
                }
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent_messages.append(msg)

        handlers = {
            "auth": lambda *args, **kwargs: (None, "0x", False, "unauthorized: invalid signature"),
            "ws_input": lambda storage, p, c, session=None: {"result": "result", "session_id": "123", "duration_ms": 100, "session": {}},
        }

        await handle_websocket(scope, receive, send, route_handlers=handlers, storage=storage, trust="open")

        # Find ERROR message
        error_msgs = [
            m for m in sent_messages
            if m.get("type") == "websocket.send" and "ERROR" in m.get("text", "")
        ]
        assert len(error_msgs) >= 1

        error_data = json.loads(error_msgs[0]["text"])
        assert error_data["type"] == "ERROR"
        assert "unauthorized" in error_data["message"]


@pytest.mark.asyncio
class TestCreateApp:
    """Test create_app function."""

    async def test_creates_callable_app(self):
        """Test that create_app returns a callable ASGI app."""
        handlers = {
            "input": lambda *args: {"result": "ok"},
            "session": lambda *args: None,
            "sessions": lambda *args: {"sessions": []},
            "health": lambda *args: {"status": "healthy"},
            "info": lambda *args: {"name": "test"},
            "auth": lambda *args, **kwargs: ("prompt", "id", True, None),
            "ws_input": lambda p: "result",
            "ws_input": lambda p, c: "result",
            "admin_logs": lambda: {"content": ""},
            "admin_sessions": lambda: {"sessions": []},
        }
        storage = Mock()

        app = create_app(route_handlers=handlers, storage=storage)

        assert callable(app)

    async def test_app_handles_http_scope(self):
        """Test that app routes HTTP requests correctly."""
        handlers = {
            "health": lambda start_time: {"status": "healthy", "uptime": 0},
            "auth": lambda *args, **kwargs: ("prompt", "id", True, None),
        }
        storage = Mock()

        app = create_app(route_handlers=handlers, storage=storage)

        scope = {"type": "http", "method": "GET", "path": "/health", "headers": []}
        sent = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(msg):
            sent.append(msg)

        await app(scope, receive, send)

        # Should have response start and body
        assert any(m.get("type") == "http.response.start" for m in sent)
        assert any(m.get("type") == "http.response.body" for m in sent)
