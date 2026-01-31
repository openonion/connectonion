#!/usr/bin/env python3
"""
Unit tests for connect.py - remote agent connection with streaming.

Tests cover:
- RemoteAgent initialization
- connect() factory function
- Response dataclass
- input() and input_async() methods
- UI event transformation (tool_call + tool_result merge)
- Status management
- Session state sync
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from connectonion.network.connect import RemoteAgent, connect, Response


class TestResponse:
    """Test Response dataclass."""

    def test_response_attributes(self):
        """Test Response has text and done attributes."""
        response = Response(text="Hello", done=True)
        assert response.text == "Hello"
        assert response.done is True

    def test_response_done_false(self):
        """Test Response with done=False (agent asked question)."""
        response = Response(text="Which date?", done=False)
        assert response.text == "Which date?"
        assert response.done is False


class TestRemoteAgentInit:
    """Test RemoteAgent initialization."""

    def test_init_stores_address(self):
        """Test that __init__ stores agent address."""
        agent = RemoteAgent("0x123abc", relay_url="wss://relay.example.com")
        assert agent.address == "0x123abc"

    def test_init_stores_relay_url(self):
        """Test that __init__ stores relay URL."""
        agent = RemoteAgent("0x123", relay_url="ws://localhost:8000")
        assert agent._relay_url == "ws://localhost:8000"

    def test_init_default_relay_url(self):
        """Test that __init__ uses default relay URL."""
        agent = RemoteAgent("0x123")
        assert agent._relay_url == "wss://oo.openonion.ai"

    def test_init_with_keys(self):
        """Test that __init__ stores signing keys."""
        keys = {"address": "0xmykey", "private_key": b"secret"}
        agent = RemoteAgent("0x123", keys=keys)
        assert agent._keys == keys

    def test_init_status_is_idle(self):
        """Test that __init__ initializes status as idle."""
        agent = RemoteAgent("0x123")
        assert agent.status == "idle"

    def test_init_current_session_is_none(self):
        """Test that __init__ initializes current_session as None."""
        agent = RemoteAgent("0x123")
        assert agent.current_session is None

    def test_init_ui_is_empty(self):
        """Test that __init__ initializes ui as empty list."""
        agent = RemoteAgent("0x123")
        assert agent.ui == []


class TestRemoteAgentProperties:
    """Test RemoteAgent properties."""

    def test_status_property(self):
        """Test status property returns current status."""
        agent = RemoteAgent("0x123")
        assert agent.status == "idle"
        agent._status = "working"
        assert agent.status == "working"

    def test_current_session_property(self):
        """Test current_session property returns session data."""
        agent = RemoteAgent("0x123")
        assert agent.current_session is None
        agent._current_session = {"messages": []}
        assert agent.current_session == {"messages": []}

    def test_ui_property(self):
        """Test ui property returns UI events list."""
        agent = RemoteAgent("0x123")
        agent._ui_events = [{"type": "user", "content": "Hello"}]
        assert agent.ui == [{"type": "user", "content": "Hello"}]


class TestConnectFactory:
    """Test connect() factory function."""

    def test_connect_returns_remote_agent(self):
        """Test that connect() returns RemoteAgent instance."""
        agent = connect("0x123abc")
        assert isinstance(agent, RemoteAgent)

    def test_connect_with_default_relay(self):
        """Test connect() uses default relay URL."""
        agent = connect("0x123abc")
        assert agent._relay_url == "wss://oo.openonion.ai"

    def test_connect_with_custom_relay(self):
        """Test connect() accepts custom relay URL."""
        custom_url = "ws://localhost:8000"
        agent = connect("0x123abc", relay_url=custom_url)
        assert agent._relay_url == custom_url

    def test_connect_sets_address(self):
        """Test connect() properly sets agent address."""
        agent = connect("0xdeadbeef")
        assert agent.address == "0xdeadbeef"

    def test_connect_with_keys(self):
        """Test connect() accepts signing keys."""
        keys = {"address": "0xmykey"}
        agent = connect("0x123", keys=keys)
        assert agent._keys == keys


class TestRemoteAgentRepr:
    """Test __repr__() string representation."""

    def test_repr_short_address(self):
        """Test __repr__ with short address (no truncation)."""
        agent = RemoteAgent("0x123")
        assert repr(agent) == "RemoteAgent(0x123)"

    def test_repr_long_address_truncated(self):
        """Test __repr__ truncates long addresses."""
        long_addr = "0x" + "a" * 64
        agent = RemoteAgent(long_addr)
        result = repr(agent)
        assert result.startswith("RemoteAgent(0x")
        assert result.endswith("...)")


class TestRemoteAgentReset:
    """Test reset() method."""

    def test_reset_clears_session(self):
        """Test reset() clears current_session."""
        agent = RemoteAgent("0x123")
        agent._current_session = {"messages": []}
        agent.reset()
        assert agent._current_session is None

    def test_reset_clears_ui_events(self):
        """Test reset() clears ui events."""
        agent = RemoteAgent("0x123")
        agent._ui_events = [{"type": "user"}]
        agent.reset()
        assert agent._ui_events == []

    def test_reset_sets_status_idle(self):
        """Test reset() sets status to idle."""
        agent = RemoteAgent("0x123")
        agent._status = "working"
        agent.reset()
        assert agent._status == "idle"


class TestRemoteAgentInput:
    """Test input() synchronous method."""

    def test_input_raises_in_async_context(self):
        """Test input() raises clear error when called from async context."""
        async def test():
            agent = RemoteAgent("0x123")
            with pytest.raises(RuntimeError) as exc_info:
                agent.input("Test")
            assert "input_async" in str(exc_info.value)
            assert "async context" in str(exc_info.value)

        asyncio.run(test())


class TestUIEventTransformation:
    """Test UI event transformation logic."""

    def test_handle_tool_call_adds_running_status(self):
        """Test tool_call event adds UI item with running status."""
        agent = RemoteAgent("0x123")
        event = {"type": "tool_call", "id": "tc1", "name": "search", "args": {"q": "test"}}

        agent._handle_stream_event(event)

        assert len(agent.ui) == 1
        assert agent.ui[0]["type"] == "tool_call"
        assert agent.ui[0]["id"] == "tc1"
        assert agent.ui[0]["status"] == "running"

    def test_handle_tool_result_updates_existing_tool_call(self):
        """Test tool_result event updates existing tool_call item."""
        agent = RemoteAgent("0x123")
        # First add tool_call
        agent._handle_stream_event({"type": "tool_call", "id": "tc1", "name": "search"})
        # Then add tool_result with same id
        agent._handle_stream_event({"type": "tool_result", "id": "tc1", "result": "Found 3 results", "status": "success"})

        assert len(agent.ui) == 1  # Still one item, not two
        assert agent.ui[0]["status"] == "done"
        assert agent.ui[0]["result"] == "Found 3 results"

    def test_handle_tool_result_error_status(self):
        """Test tool_result with error status."""
        agent = RemoteAgent("0x123")
        agent._handle_stream_event({"type": "tool_call", "id": "tc1", "name": "search"})
        agent._handle_stream_event({"type": "tool_result", "id": "tc1", "result": "Error", "status": "error"})

        assert agent.ui[0]["status"] == "error"

    def test_handle_thinking_event(self):
        """Test thinking event adds thinking indicator."""
        agent = RemoteAgent("0x123")
        agent._handle_stream_event({"type": "thinking"})

        assert len(agent.ui) == 1
        assert agent.ui[0]["type"] == "thinking"

    def test_handle_assistant_event(self):
        """Test assistant event adds agent message."""
        agent = RemoteAgent("0x123")
        agent._handle_stream_event({"type": "assistant", "content": "Hello!"})

        assert len(agent.ui) == 1
        assert agent.ui[0]["type"] == "agent"
        assert agent.ui[0]["content"] == "Hello!"

    def test_handle_user_input_skipped(self):
        """Test user_input event is skipped (already added by input())."""
        agent = RemoteAgent("0x123")
        agent._handle_stream_event({"type": "user_input", "content": "Hello"})

        assert len(agent.ui) == 0  # Skipped

    def test_add_ui_event_auto_generates_id(self):
        """Test _add_ui_event auto-generates id if not present."""
        agent = RemoteAgent("0x123")
        agent._add_ui_event({"type": "user", "content": "Hello"})

        assert "id" in agent.ui[0]
        assert agent.ui[0]["id"] == "1"

    def test_add_ui_event_preserves_existing_id(self):
        """Test _add_ui_event preserves id if already present."""
        agent = RemoteAgent("0x123")
        agent._add_ui_event({"type": "tool_call", "id": "custom-id"})

        assert agent.ui[0]["id"] == "custom-id"


def create_mock_ws(messages: list):
    """Create a mock WebSocket with recv() method for testing."""
    class MockWebSocket:
        def __init__(self):
            self.messages = messages
            self.index = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def send(self, msg):
            pass

        async def recv(self):
            if self.index < len(self.messages):
                msg = self.messages[self.index]
                self.index += 1
                return msg
            raise Exception("No more messages")

    return MockWebSocket()


class TestStreamInput:
    """Test _stream_input() WebSocket streaming."""

    @pytest.mark.asyncio
    async def test_stream_input_adds_user_event(self):
        """Test _stream_input adds user event to UI."""
        agent = RemoteAgent("0x123")

        mock_ws = create_mock_ws([json.dumps({"type": "OUTPUT", "result": "Done", "session": {}})])

        with patch('websockets.connect', return_value=mock_ws):
            await agent._stream_input("Hello", 30.0)

        # Check user event was added
        assert any(e["type"] == "user" and e["content"] == "Hello" for e in agent.ui)

    @pytest.mark.asyncio
    async def test_stream_input_returns_response(self):
        """Test _stream_input returns Response object."""
        agent = RemoteAgent("0x123")

        mock_ws = create_mock_ws([json.dumps({"type": "OUTPUT", "result": "Task done", "session": {}})])

        with patch('websockets.connect', return_value=mock_ws):
            response = await agent._stream_input("Do something", 30.0)

        assert isinstance(response, Response)
        assert response.text == "Task done"
        assert response.done is True

    @pytest.mark.asyncio
    async def test_stream_input_ask_user_returns_done_false(self):
        """Test _stream_input returns done=False on ask_user event."""
        agent = RemoteAgent("0x123")

        mock_ws = create_mock_ws([json.dumps({"type": "ask_user", "text": "Which date?"})])

        with patch('websockets.connect', return_value=mock_ws):
            response = await agent._stream_input("Book flight", 30.0)

        assert response.done is False
        assert response.text == "Which date?"
        assert agent.status == "waiting"

    @pytest.mark.asyncio
    async def test_stream_input_handles_error(self):
        """Test _stream_input raises on ERROR message."""
        agent = RemoteAgent("0x123")

        mock_ws = create_mock_ws([json.dumps({"type": "ERROR", "message": "Agent not found"})])

        with patch('websockets.connect', return_value=mock_ws):
            with pytest.raises(ConnectionError) as exc_info:
                await agent._stream_input("Test", 30.0)

        assert "Agent error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_stream_input_processes_tool_events(self):
        """Test _stream_input processes tool_call and tool_result events."""
        agent = RemoteAgent("0x123")

        mock_ws = create_mock_ws([
            json.dumps({"type": "tool_call", "id": "t1", "name": "search", "args": {}}),
            json.dumps({"type": "tool_result", "id": "t1", "result": "Found", "status": "success"}),
            json.dumps({"type": "OUTPUT", "result": "Done", "session": {}})
        ])

        with patch('websockets.connect', return_value=mock_ws):
            await agent._stream_input("Search", 30.0)

        # tool_call and tool_result should be merged into one UI item
        tool_events = [e for e in agent.ui if e["type"] == "tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0]["status"] == "done"
        assert tool_events[0]["result"] == "Found"

    @pytest.mark.asyncio
    async def test_stream_input_sets_status_working(self):
        """Test _stream_input sets status to working during execution."""
        agent = RemoteAgent("0x123")

        # We'll check status after recv is called
        class StatusCheckingMockWS:
            def __init__(self, agent_ref):
                self.agent = agent_ref
                self.status_during_recv = None
                self.called = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def send(self, msg):
                pass

            async def recv(self):
                if not self.called:
                    self.called = True
                    self.status_during_recv = self.agent.status
                    return json.dumps({"type": "OUTPUT", "result": "Done", "session": {}})
                raise Exception("No more messages")

        mock_ws = StatusCheckingMockWS(agent)

        with patch('websockets.connect', return_value=mock_ws):
            await agent._stream_input("Test", 30.0)

        assert mock_ws.status_during_recv == "working"
        assert agent.status == "idle"  # Back to idle after completion


class TestIntegration:
    """Integration tests combining multiple components."""

    @pytest.mark.asyncio
    async def test_full_workflow_async(self):
        """Test full workflow: connect() -> input_async() -> Response."""
        mock_ws = create_mock_ws([
            json.dumps({"type": "thinking"}),
            json.dumps({"type": "tool_call", "id": "t1", "name": "translate", "args": {"text": "hello"}}),
            json.dumps({"type": "tool_result", "id": "t1", "result": "hola", "status": "success"}),
            json.dumps({"type": "OUTPUT", "result": "Translation: hola", "session": {"messages": []}})
        ])

        with patch('websockets.connect', return_value=mock_ws):
            agent = connect("0xtranslator")
            response = await agent.input_async("Translate 'hello' to Spanish")

        assert response.text == "Translation: hola"
        assert response.done is True
        assert agent.status == "idle"

        # Check UI has correct events
        assert any(e["type"] == "user" for e in agent.ui)
        assert any(e["type"] == "thinking" for e in agent.ui)
        assert any(e["type"] == "tool_call" and e["status"] == "done" for e in agent.ui)
        assert any(e["type"] == "agent" for e in agent.ui)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
