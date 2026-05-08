"""Unit tests for connectonion/network/asgi.py"""
"""
LLM-Note: Tests for asgi

What it tests:
- Asgi functionality

Components under test:
- Module: asgi
"""


import asyncio
import json
import queue
import threading
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from connectonion.network.asgi import (
    handle_websocket,
    create_app,
    send_json,
    read_body,
)
from connectonion.network.host.ws_router.agent_io import forward_agent_msgs_to_client
from connectonion.network.io import WebSocketIO
from connectonion.network.host.session import ActiveSessionRegistry


class TestWebSocketIOInASGI:
    """Test WebSocketIO used in WebSocket handling."""

    def test_integration_with_event_log(self):
        """Test that WebSocketIO event log works with sending pattern."""
        conn = WebSocketIO()

        # Simulate agent sending events
        conn.send({"type": "thinking"})
        conn.send({"type": "tool_call", "name": "search"})

        # Should be able to read message log
        assert len(conn._msgs_from_agent) == 2
        assert conn._msgs_from_agent[0]["type"] == "thinking"
        assert conn._msgs_from_agent[1]["type"] == "tool_call"

    def test_bidirectional_communication(self):
        """Test send and receive for approval flow."""
        conn = WebSocketIO()

        result_holder = [None]

        def run_agent():
            result_holder[0] = conn.request_approval("delete", {"path": "/tmp/x"})

        thread = threading.Thread(target=run_agent)
        thread.start()

        # Wait for outgoing request
        with conn._agent_condition:
            while not conn._msgs_from_agent:
                conn._agent_condition.wait(timeout=1)
        request = conn._msgs_from_agent[0]
        assert request["type"] == "approval_needed"
        assert request["tool"] == "delete"

        # Simulate client response
        conn.send_to_agent({"approved": True})

        thread.join(timeout=1)
        assert result_holder[0] is True


@pytest.mark.asyncio
class TestForwardAgentEvents:
    """Test forward_agent_msgs_to_client async function."""

    async def test_sends_outgoing_messages_to_client(self):
        """Test that outgoing events are forwarded via send_msg."""
        io = WebSocketIO()
        sent_messages = []

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        io.send({"type": "thinking"})
        io.send({"type": "tool_call", "name": "search"})

        def agent_done():
            import time
            time.sleep(0.05)
            io.mark_agent_done()

        threading.Thread(target=agent_done).start()

        await asyncio.wait_for(
            forward_agent_msgs_to_client(mock_send_msg, io, "test-session"),
            timeout=2.0
        )

        event_types = [m["type"] for m in sent_messages if m.get("type") not in ("ERROR",)]
        assert "thinking" in event_types
        assert "tool_call" in event_types

    async def test_sends_output_from_result_holder(self):
        """Test that OUTPUT is sent when agent completes with result."""
        io = WebSocketIO()
        sent_messages = []
        result_holder = [{"result": "answer", "session_id": "s1", "duration_ms": 50, "session": {}}]

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        io.mark_agent_done()

        await asyncio.wait_for(
            forward_agent_msgs_to_client(mock_send_msg, io, "s1", result_holder=result_holder),
            timeout=2.0
        )

        output_msgs = [m for m in sent_messages if m.get("type") == "OUTPUT"]
        assert len(output_msgs) == 1
        assert output_msgs[0]["result"] == "answer"

    async def test_sends_error_from_exception(self):
        """Test that ERROR is sent when agent raises."""
        io = WebSocketIO()
        sent_messages = []
        result_holder = [RuntimeError("boom")]

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        io.mark_agent_done()

        await asyncio.wait_for(
            forward_agent_msgs_to_client(mock_send_msg, io, "s1", result_holder=result_holder),
            timeout=2.0
        )

        error_msgs = [m for m in sent_messages if m.get("type") == "ERROR"]
        assert len(error_msgs) == 1
        assert "boom" in error_msgs[0]["message"]


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

        registry = ActiveSessionRegistry()
        await handle_websocket(scope, receive, send, route_handlers=handlers, storage=storage, registry=registry, trust="open")

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
        registry = ActiveSessionRegistry()

        await handle_websocket(scope, receive, send, route_handlers=handlers, storage=storage, registry=registry, trust="open")

        close_msg = [m for m in sent_messages if m.get("type") == "websocket.close"]
        assert len(close_msg) == 1
        assert close_msg[0]["code"] == 4004

    async def test_handles_input_message(self):
        """Test that CONNECT + INPUT triggers agent execution."""
        scope = {"path": "/ws", "type": "websocket"}
        sent_messages = []
        message_count = [0]
        storage = Mock()
        storage.get.return_value = None

        async def receive():
            message_count[0] += 1
            if message_count[0] == 1:
                return {
                    "type": "websocket.receive",
                    "text": json.dumps({
                        "type": "CONNECT",
                        "payload": {"timestamp": 1234567890},
                        "from": "0xtest",
                        "signature": "0xsig"
                    })
                }
            if message_count[0] == 2:
                return {
                    "type": "websocket.receive",
                    "text": json.dumps({
                        "type": "INPUT",
                        "prompt": "hello"
                    })
                }
            # Give time for agent thread to complete
            await asyncio.sleep(0.1)
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent_messages.append(msg)

        agent_called = [False]
        connection_received = [None]

        def mock_ws_input(storage, prompt, connection, session=None, images=None, files=None):
            agent_called[0] = True
            connection_received[0] = connection
            return {"result": "Agent response", "session_id": "123", "duration_ms": 100, "session": {}, "status": "done"}

        handlers = {
            "auth": lambda *args, **kwargs: ("hello", "0xtest", True, None),
            "ws_input": mock_ws_input,
            "trust_agent": Mock(config={}),
        }

        registry = ActiveSessionRegistry()
        await handle_websocket(scope, receive, send, route_handlers=handlers, storage=storage, registry=registry, trust="open")

        assert agent_called[0] is True
        assert connection_received[0] is not None
        assert isinstance(connection_received[0], WebSocketIO)

    async def test_sends_output_after_agent_completes(self):
        """Test that OUTPUT message is sent after agent completes."""
        scope = {"path": "/ws", "type": "websocket"}
        sent_messages = []
        message_count = [0]
        storage = Mock()
        storage.get.return_value = None

        async def receive():
            message_count[0] += 1
            if message_count[0] == 1:
                return {
                    "type": "websocket.receive",
                    "text": json.dumps({"type": "CONNECT", "session_id": "abc-123", "payload": {"timestamp": 123}, "from": "0x", "signature": "0x"})
                }
            if message_count[0] == 2:
                return {
                    "type": "websocket.receive",
                    "text": json.dumps({"type": "INPUT", "prompt": "test"})
                }
            # Give time for agent to complete
            await asyncio.sleep(0.1)
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent_messages.append(msg)

        handlers = {
            "auth": lambda *args, **kwargs: ("test", "0x", True, None),
            "ws_input": lambda storage, p, c, session=None, images=None, files=None: {"result": "Expected result", "session_id": "abc-123", "duration_ms": 50, "session": {}, "status": "done"},
            "trust_agent": Mock(config={}),
        }

        registry = ActiveSessionRegistry()
        await handle_websocket(scope, receive, send, route_handlers=handlers, storage=storage, registry=registry, trust="open")

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
        """Test that auth errors are sent back to client on INIT."""
        scope = {"path": "/ws", "type": "websocket"}
        sent_messages = []
        message_count = [0]
        storage = Mock()

        async def receive():
            message_count[0] += 1
            if message_count[0] == 1:
                return {
                    "type": "websocket.receive",
                    "text": json.dumps({"type": "CONNECT", "payload": {"timestamp": 123}, "from": "0x", "signature": "0x"})
                }
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent_messages.append(msg)

        handlers = {
            "auth": lambda *args, **kwargs: (None, "0x", False, "unauthorized: invalid signature"),
            "ws_input": lambda storage, p, c, session=None: {"result": "result", "session_id": "123", "duration_ms": 100, "session": {}},
        }
        registry = ActiveSessionRegistry()

        await handle_websocket(scope, receive, send, route_handlers=handlers, storage=storage, registry=registry, trust="open")

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
        registry = ActiveSessionRegistry()

        app = create_app(route_handlers=handlers, storage=storage, registry=registry)

        assert callable(app)

    async def test_app_handles_http_scope(self):
        """Test that app routes HTTP requests correctly."""
        handlers = {
            "health": lambda start_time: {"status": "healthy", "uptime": 0},
            "auth": lambda *args, **kwargs: ("prompt", "id", True, None),
        }
        storage = Mock()
        registry = ActiveSessionRegistry()

        app = create_app(route_handlers=handlers, storage=storage, registry=registry)

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
