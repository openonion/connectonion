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
from connectonion.network.host.session.mode import ModeTransactionError
from connectonion.network.host.ws_router.agent_io import (
    _agent_thread_body,
    forward_agent_msgs_to_client,
)
from connectonion.network.host.ws_router import agent_io as agent_io_module
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

    FINAL_MESSAGE_ID = "6d1fcd7e-2e31-4ac4-9f39-7de8f73cd82e"

    async def test_sends_outgoing_messages_to_client(self):
        """Test that outgoing events are forwarded via send_msg."""
        io = WebSocketIO()
        sent_messages = []

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        io.send({"type": "thinking"})
        io.send({
            "type": "tool_call",
            "tool_id": "call-1",
            "name": "search",
            "args": {},
            "status": "in_progress",
        })

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
        assert "ACP_NOTIFICATION" in event_types
        assert "tool_call" in event_types
        acp_message = next(
            message for message in sent_messages
            if message.get("type") == "ACP_NOTIFICATION"
        )["message"]
        assert acp_message["method"] == "session/update"
        assert acp_message["params"]["sessionId"] == "test-session"

    async def test_public_thought_acp_mirror_precedes_legacy_event(self):
        io = WebSocketIO()
        sent_messages = []

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        thought = {
            "type": "thinking",
            "id": "thought-1",
            "kind": "reflect",
            "content": "checking the result",
        }
        io._send_persisted_trace(thought)
        io.mark_agent_done()

        await forward_agent_msgs_to_client(
            mock_send_msg, io, "session-1"
        )

        assert [message["type"] for message in sent_messages[:2]] == [
            "ACP_NOTIFICATION",
            "thinking",
        ]
        assert sent_messages[0]["message"]["params"] == {
            "sessionId": "session-1",
            "update": {
                "content": {"text": "checking the result", "type": "text"},
                "messageId": "thought-1",
                "_meta": {"connectonion": {"kind": "reflect"}},
                "sessionUpdate": "agent_thought_chunk",
            },
        }
        assert sent_messages[1]["type"] == "thinking"
        assert sent_messages[1]["id"] == thought["id"]
        assert sent_messages[1]["kind"] == thought["kind"]
        assert sent_messages[1]["content"] == thought["content"]
        assert sent_messages[1]["session_id"] == "session-1"
        assert isinstance(sent_messages[1]["ts"], float)

    async def test_direct_thinking_event_stays_legacy_only(self):
        """The public IO primitive does not classify direct events as thoughts."""
        io = WebSocketIO()
        sent_messages = []

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        thought = {
            "type": "thinking",
            "id": "direct-thought",
            "content": "not a persisted trace entry",
        }
        io.send(thought)
        io.mark_agent_done()

        await forward_agent_msgs_to_client(
            mock_send_msg, io, "session-1"
        )

        protocol_types = [
            message["type"] for message in sent_messages
            if message["type"] != "DASHBOARD_SNAPSHOT"
        ]
        assert protocol_types == [
            "thinking",
            "ERROR",
        ]
        assert sent_messages[0] == {**thought, "session_id": "session-1"}
        assert not any(
            message.get("type") == "ACP_NOTIFICATION"
            for message in sent_messages
        )

    async def test_bad_thought_mirror_still_drains_legacy_and_output(self):
        io = WebSocketIO()
        sent_messages = []
        result_holder = [{
            "result": "committed",
            "duration_ms": 5,
            "session": {},
        }]

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        io._send_persisted_trace({
            "type": "thinking",
            "id": "thought-1",
            "content": "already visible",
        })
        io.mark_agent_done()

        with patch.object(
            agent_io_module,
            "acp_notification_frame",
            side_effect=ValueError("bad thought mirror"),
        ):
            await forward_agent_msgs_to_client(
                mock_send_msg,
                io,
                "session-1",
                result_holder=result_holder,
            )

        protocol_types = [
            message["type"] for message in sent_messages
            if message["type"] != "DASHBOARD_SNAPSHOT"
        ]
        assert protocol_types == [
            "thinking",
            "OUTPUT",
        ]

    async def test_provider_diagnostics_are_not_acp_thoughts(self):
        io = WebSocketIO()
        sent_messages = []
        result_holder = [{
            "result": "committed",
            "duration_ms": 5,
            "session": {},
        }]

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        io.send({
            "type": "llm_result",
            "id": "provider-1",
            "content": "must not become public reasoning",
        })
        io.mark_agent_done()

        await forward_agent_msgs_to_client(
            mock_send_msg,
            io,
            "session-1",
            result_holder=result_holder,
        )

        protocol_types = [
            message["type"] for message in sent_messages
            if message["type"] != "DASHBOARD_SNAPSHOT"
        ]
        assert protocol_types == [
            "llm_result",
            "OUTPUT",
        ]

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

    async def test_persisted_final_answer_precedes_output_as_acp_message(self):
        io = WebSocketIO()
        sent_messages = []
        session = {
            "messages": [
                {"role": "system", "content": "help"},
                {"role": "user", "content": "question"},
                {
                    "role": "assistant",
                    "content": "answer",
                    "id": self.FINAL_MESSAGE_ID,
                },
            ]
        }
        result_holder = [{
            "result": "answer",
            "duration_ms": 50,
            "session": session,
        }]

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        io.mark_agent_done()
        await forward_agent_msgs_to_client(
            mock_send_msg, io, "s1", result_holder=result_holder
        )

        terminal_messages = [
            message for message in sent_messages
            if message.get("type") in {"ACP_NOTIFICATION", "OUTPUT"}
        ]
        assert [message["type"] for message in terminal_messages] == [
            "ACP_NOTIFICATION",
            "OUTPUT",
        ]
        params = terminal_messages[0]["message"]["params"]
        assert params == {
            "sessionId": "s1",
            "update": {
                "content": {"text": "answer", "type": "text"},
                "messageId": self.FINAL_MESSAGE_ID,
                "sessionUpdate": "agent_message_chunk",
            },
        }
        assert terminal_messages[1]["chat_items"][-1] == {
            "id": self.FINAL_MESSAGE_ID,
            "type": "agent",
            "content": "answer",
        }

    async def test_unpersisted_terminal_text_uses_legacy_output_only(self):
        io = WebSocketIO()
        sent_messages = []
        result_holder = [{
            "result": "Task incomplete: Maximum iterations reached.",
            "duration_ms": 50,
            "session": {"messages": []},
        }]

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        io.mark_agent_done()
        await forward_agent_msgs_to_client(
            mock_send_msg, io, "s1", result_holder=result_holder
        )

        assert [
            message["type"] for message in sent_messages
            if message.get("type") in {"ACP_NOTIFICATION", "OUTPUT"}
        ] == ["OUTPUT"]

    async def test_legacy_stored_answer_without_id_uses_output_only(self):
        io = WebSocketIO()
        sent_messages = []
        result_holder = [{
            "result": "answer",
            "duration_ms": 50,
            "session": {
                "messages": [{"role": "assistant", "content": "answer"}],
            },
        }]

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        io.mark_agent_done()
        await forward_agent_msgs_to_client(
            mock_send_msg, io, "s1", result_holder=result_holder
        )

        assert [
            message["type"] for message in sent_messages
            if message.get("type") in {"ACP_NOTIFICATION", "OUTPUT"}
        ] == ["OUTPUT"]

    async def test_terminal_text_does_not_reuse_an_older_matching_answer(self):
        io = WebSocketIO()
        sent_messages = []
        result_holder = [{
            "result": "same text",
            "duration_ms": 50,
            "session": {
                "messages": [
                    {"role": "assistant", "content": "same text"},
                    {"role": "user", "content": "new question"},
                    {"role": "assistant", "content": "different answer"},
                ]
            },
        }]

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        io.mark_agent_done()
        await forward_agent_msgs_to_client(
            mock_send_msg, io, "s1", result_holder=result_holder
        )

        assert [
            message["type"] for message in sent_messages
            if message.get("type") in {"ACP_NOTIFICATION", "OUTPUT"}
        ] == ["OUTPUT"]

    async def test_stored_completion_reuses_the_same_message_id(self):
        io = WebSocketIO()
        sent_messages = []
        stored = Mock(
            status="done",
            result="answer",
            duration_ms=50,
            session={
                "messages": [
                    {"role": "user", "content": "question"},
                    {
                        "role": "assistant",
                        "content": "answer",
                        "id": self.FINAL_MESSAGE_ID,
                    },
                ]
            },
        )
        storage = Mock()
        storage.get.return_value = stored

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        io.mark_agent_done()
        await forward_agent_msgs_to_client(
            mock_send_msg, io, "s1", storage=storage
        )

        assert (
            sent_messages[0]["message"]["params"]["update"]["messageId"]
            == self.FINAL_MESSAGE_ID
        )
        assert sent_messages[1]["chat_items"][-1]["id"] == self.FINAL_MESSAGE_ID

    async def test_bad_final_message_mirror_still_sends_output(self):
        io = WebSocketIO()
        sent_messages = []
        result_holder = [{
            "result": "answer",
            "duration_ms": 50,
            "session": {
                "messages": [
                    {"role": "user", "content": "question"},
                    {
                        "role": "assistant",
                        "content": "answer",
                        "id": self.FINAL_MESSAGE_ID,
                    },
                ]
            },
        }]

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        io.mark_agent_done()
        with patch.object(
            agent_io_module,
            "acp_notification_frame",
            side_effect=ValueError("bad mirror"),
        ):
            await forward_agent_msgs_to_client(
                mock_send_msg, io, "s1", result_holder=result_holder
            )

        assert [
            message["type"] for message in sent_messages
            if message.get("type") in {"ACP_NOTIFICATION", "OUTPUT"}
        ] == ["OUTPUT"]

    async def test_stray_live_assistant_event_cannot_duplicate_final_answer(self):
        io = WebSocketIO()
        sent_messages = []
        result_holder = [{
            "result": "answer",
            "duration_ms": 50,
            "session": {
                "messages": [{
                    "role": "assistant",
                    "content": "answer",
                    "id": self.FINAL_MESSAGE_ID,
                }],
            },
        }]

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        io.send({
            "type": "assistant",
            "id": "plugin-message",
            "content": "plugin text",
        })
        io.mark_agent_done()
        await forward_agent_msgs_to_client(
            mock_send_msg, io, "s1", result_holder=result_holder
        )

        assert [
            message["type"] for message in sent_messages
            if message.get("type") in {
                "assistant", "ACP_NOTIFICATION", "OUTPUT"
            }
        ] == [
            "assistant",
            "ACP_NOTIFICATION",
            "OUTPUT",
        ]
        acp_updates = [
            message["message"]["params"]["update"]
            for message in sent_messages
            if message["type"] == "ACP_NOTIFICATION"
        ]
        assert [update["messageId"] for update in acp_updates] == [
            self.FINAL_MESSAGE_ID
        ]

    async def test_bad_acp_mirror_falls_back_without_inviting_a_retry(self):
        io = WebSocketIO()
        sent_messages = []
        result_holder = [{
            "result": "committed",
            "duration_ms": 5,
            "session": {},
        }]

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        io.send({"type": "tool_result", "status": "success", "result": "ok"})
        io.mark_agent_done()

        await forward_agent_msgs_to_client(
            mock_send_msg, io, "s1", result_holder=result_holder
        )

        event_types = [message["type"] for message in sent_messages]
        assert event_types.count("tool_result") == 1
        assert event_types.count("OUTPUT") == 1
        assert "ACP_NOTIFICATION" not in event_types
        assert "ERROR" not in event_types

    async def test_sends_error_from_exception(self):
        """Unexpected Agent errors never disclose their raw details."""
        io = WebSocketIO()
        sent_messages = []
        result_holder = [OSError("private /srv/agent/.co/session_results.jsonl")]

        async def mock_send_msg(msg):
            sent_messages.append(msg)

        io.mark_agent_done()

        await asyncio.wait_for(
            forward_agent_msgs_to_client(mock_send_msg, io, "s1", result_holder=result_holder),
            timeout=2.0
        )

        error_msgs = [m for m in sent_messages if m.get("type") == "ERROR"]
        assert error_msgs == [{
            "type": "ERROR",
            "code": -32603,
            "message": "Unable to run agent",
        }]
        assert "private" not in str(sent_messages)

    async def test_agent_thread_keeps_private_error_for_output_boundary(
        self, caplog
    ):
        io = WebSocketIO()
        result_holder = [None]
        registry = Mock()
        private_detail = "private /srv/agent/.co/session_results.jsonl"

        _agent_thread_body(
            {"ws_input": Mock(side_effect=OSError(private_detail))},
            Mock(),
            "prompt",
            io,
            {"session_id": "s1"},
            None,
            None,
            registry,
            "s1",
            result_holder,
            "0xowner",
        )

        assert isinstance(result_holder[0], OSError)
        assert str(result_holder[0]) == private_detail
        assert private_detail in caplog.text
        registry.mark_session_connected.assert_called_once_with("s1")

    async def test_owned_prompt_policy_error_keeps_stable_public_details(self):
        io = WebSocketIO()
        sent_messages = []
        result_holder = [ModeTransactionError(
            -32000, "Session is busy", {"retryable": True}
        )]

        async def mock_send_msg(message):
            sent_messages.append(message)

        io.mark_agent_done()
        await forward_agent_msgs_to_client(
            mock_send_msg, io, "s1", result_holder=result_holder
        )

        assert next(
            message for message in sent_messages
            if message.get("type") == "ERROR"
        ) == {
            "type": "ERROR",
            "code": -32000,
            "message": "Session is busy",
            "retryable": True,
        }


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
            "ws_input": lambda storage, prompt, conn, session=None, images=None, files=None, requester_address=None: {"result": "result", "session_id": "123", "duration_ms": 100, "session": {}},
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

        def mock_ws_input(storage, prompt, connection, session=None, images=None, files=None,
                          requester_address=None):
            agent_called[0] = True
            connection_received[0] = connection
            return {"result": "Agent response", "session_id": "123", "duration_ms": 100, "session": {}, "status": "done"}

        handlers = {
            "auth": lambda *args, **kwargs: ("hello", "0xtest", True, None),
            "connect_auth": lambda *args, **kwargs: ("hello", "0xtest", True, None),
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
            "connect_auth": lambda *args, **kwargs: ("test", "0x", True, None),
            "ws_input": lambda storage, p, c, session=None, images=None, files=None, requester_address=None: {"result": "Expected result", "session_id": "abc-123", "duration_ms": 50, "session": {}, "status": "done"},
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
            "ws_input": lambda storage, p, c, session=None, images=None, files=None, requester_address=None: {"result": "result", "session_id": "123", "duration_ms": 100, "session": {}},
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
