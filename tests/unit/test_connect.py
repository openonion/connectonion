#!/usr/bin/env python3
"""
Unit tests for connect.py - remote agent connection.

Tests cover:
- RemoteAgent initialization
- connect() factory function
- input() synchronous method
- input_async() asynchronous method
- _send_task() WebSocket communication
- OUTPUT message handling
- ERROR message handling
- Timeout handling
- Unexpected response handling
- __repr__() string representation
- Relay URL transformation

Critical paths from coverage analysis:
- RemoteAgent.__init__ (lines 19-21)
- input() calls asyncio.run (line 41)
- input_async() calls _send_task (line 60)
- _send_task() WebSocket flow (lines 62-96)
- connect() factory function (line 119)
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from connectonion.connect import RemoteAgent, connect


def create_mock_websocket(recv_data=None):
    """Helper to create properly configured AsyncMock websocket for context manager."""
    mock_ws = AsyncMock()
    if recv_data:
        mock_ws.recv.return_value = recv_data
    mock_ws.__aenter__.return_value = mock_ws
    mock_ws.__aexit__.return_value = AsyncMock()
    return mock_ws


class TestRemoteAgentInit:
    """Test RemoteAgent initialization."""

    def test_init_stores_address(self):
        """Test that __init__ stores agent address."""
        agent = RemoteAgent("0x123abc", "wss://relay.example.com/ws/announce")
        assert agent.address == "0x123abc"

    def test_init_stores_relay_url(self):
        """Test that __init__ stores relay URL."""
        agent = RemoteAgent("0x123", "ws://localhost:8000/ws/announce")
        assert agent._relay_url == "ws://localhost:8000/ws/announce"

    def test_init_with_long_address(self):
        """Test initialization with full-length address."""
        full_addr = "0x" + "a" * 64
        agent = RemoteAgent(full_addr, "wss://relay/ws/announce")
        assert agent.address == full_addr

    def test_init_with_empty_address(self):
        """Test initialization with empty address (valid construction)."""
        agent = RemoteAgent("", "wss://relay/ws/announce")
        assert agent.address == ""


class TestConnectFactory:
    """Test connect() factory function."""

    def test_connect_returns_remote_agent(self):
        """Test that connect() returns RemoteAgent instance."""
        agent = connect("0x123abc")
        assert isinstance(agent, RemoteAgent)

    def test_connect_with_default_relay(self):
        """Test connect() uses default relay URL."""
        agent = connect("0x123abc")
        assert agent._relay_url == "wss://oo.openonion.ai/ws/announce"

    def test_connect_with_custom_relay(self):
        """Test connect() accepts custom relay URL."""
        custom_url = "ws://localhost:8000/ws/announce"
        agent = connect("0x123abc", relay_url=custom_url)
        assert agent._relay_url == custom_url

    def test_connect_sets_address(self):
        """Test connect() properly sets agent address."""
        agent = connect("0xdeadbeef")
        assert agent.address == "0xdeadbeef"


class TestRemoteAgentRepr:
    """Test __repr__() string representation."""

    def test_repr_short_address(self):
        """Test __repr__ with short address (no truncation)."""
        agent = RemoteAgent("0x123", "wss://relay/ws/announce")
        assert repr(agent) == "RemoteAgent(0x123)"

    def test_repr_long_address_truncated(self):
        """Test __repr__ truncates long addresses."""
        long_addr = "0x" + "a" * 64
        agent = RemoteAgent(long_addr, "wss://relay/ws/announce")
        result = repr(agent)
        assert result.startswith("RemoteAgent(0x")
        assert result.endswith("...)")
        # Should show first 12 chars + "..."
        assert len(result) == len("RemoteAgent(") + 12 + len("...)")

    def test_repr_exactly_12_chars(self):
        """Test __repr__ with exactly 12-char address (no truncation)."""
        agent = RemoteAgent("0x1234567890", "wss://relay/ws/announce")
        assert repr(agent) == "RemoteAgent(0x1234567890)"

    def test_repr_13_chars_gets_truncated(self):
        """Test __repr__ with 13-char address (gets truncated)."""
        agent = RemoteAgent("0x12345678901", "wss://relay/ws/announce")
        assert repr(agent) == "RemoteAgent(0x1234567890...)"


class TestRemoteAgentInput:
    """Test input() synchronous method."""

    def test_input_calls_send_task(self):
        """Test that input() calls _send_task via asyncio.run."""
        agent = RemoteAgent("0x123", "wss://relay/ws/announce")

        # Mock _send_task
        agent._send_task = AsyncMock(return_value="Test response")

        # Mock asyncio.run to return the result directly
        with patch('asyncio.run', return_value="Test response"):
            result = agent.input("Test prompt")

        # Verify _send_task was called
        agent._send_task.assert_called_once_with("Test prompt", 30.0)
        assert result == "Test response"

    def test_input_with_custom_timeout(self):
        """Test input() passes custom timeout to _send_task."""
        agent = RemoteAgent("0x123", "wss://relay/ws/announce")
        agent._send_task = AsyncMock(return_value="Response")

        with patch('asyncio.run', return_value="Response"):
            result = agent.input("Prompt", timeout=60.0)

        agent._send_task.assert_called_once_with("Prompt", 60.0)
        assert result == "Response"

    def test_input_default_timeout(self):
        """Test input() uses default 30s timeout."""
        agent = RemoteAgent("0x123", "wss://relay/ws/announce")
        agent._send_task = AsyncMock(return_value="Response")

        with patch('asyncio.run', return_value="Response"):
            agent.input("Prompt")

        # Check default timeout=30.0 was passed
        agent._send_task.assert_called_once_with("Prompt", 30.0)


class TestRemoteAgentInputAsync:
    """Test input_async() asynchronous method."""

    @pytest.mark.asyncio
    async def test_input_async_calls_send_task(self):
        """Test that input_async() calls _send_task directly."""
        agent = RemoteAgent("0x123", "wss://relay/ws/announce")
        agent._send_task = AsyncMock(return_value="Async response")

        result = await agent.input_async("Test prompt")

        agent._send_task.assert_called_once_with("Test prompt", 30.0)
        assert result == "Async response"

    @pytest.mark.asyncio
    async def test_input_async_with_custom_timeout(self):
        """Test input_async() passes custom timeout."""
        agent = RemoteAgent("0x123", "wss://relay/ws/announce")
        agent._send_task = AsyncMock(return_value="Response")

        result = await agent.input_async("Prompt", timeout=45.0)

        agent._send_task.assert_called_once_with("Prompt", 45.0)
        assert result == "Response"

    @pytest.mark.asyncio
    async def test_input_async_default_timeout(self):
        """Test input_async() uses default 30s timeout."""
        agent = RemoteAgent("0x123", "wss://relay/ws/announce")
        agent._send_task = AsyncMock(return_value="Response")

        await agent.input_async("Prompt")

        agent._send_task.assert_called_once_with("Prompt", 30.0)


class TestSendTaskOutputHandling:
    """Test _send_task() OUTPUT message handling."""

    @pytest.mark.asyncio
    async def test_send_task_successful_output(self):
        """Test _send_task() handles OUTPUT message correctly."""
        agent = RemoteAgent("0x123", "wss://relay/ws/announce")

        # Mock WebSocket
        output_message = {
            "type": "OUTPUT",
            "input_id": "test-uuid",
            "result": "Task completed successfully"
        }
        mock_ws = create_mock_websocket(json.dumps(output_message))

        with patch('websockets.connect', return_value=mock_ws):
            with patch('uuid.uuid4', return_value=Mock(__str__=lambda self: "test-uuid")):
                result = await agent._send_task("Do something", 30.0)

        assert result == "Task completed successfully"

    @pytest.mark.asyncio
    async def test_send_task_sends_input_message(self):
        """Test _send_task() sends correct INPUT message format."""
        agent = RemoteAgent("0xagent123", "wss://relay/ws/announce")

        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock()
        mock_ws.recv.return_value = json.dumps({
            "type": "OUTPUT",
            "input_id": "uuid-123",
            "result": "Done"
        })

        sent_message = None

        async def capture_send(msg):
            nonlocal sent_message
            sent_message = json.loads(msg)

        mock_ws.send = capture_send

        with patch('websockets.connect', return_value=mock_ws):
            with patch('uuid.uuid4', return_value=Mock(__str__=lambda self: "uuid-123")):
                await agent._send_task("Test prompt", 30.0)

        # Verify INPUT message structure
        assert sent_message["type"] == "INPUT"
        assert sent_message["input_id"] == "uuid-123"
        assert sent_message["to"] == "0xagent123"
        assert sent_message["prompt"] == "Test prompt"

    @pytest.mark.asyncio
    async def test_send_task_transforms_relay_url(self):
        """Test _send_task() transforms /ws/announce to /ws/input."""
        agent = RemoteAgent("0x123", "wss://relay.example.com/ws/announce")

        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock()
        mock_ws.recv.return_value = json.dumps({
            "type": "OUTPUT",
            "input_id": "test",
            "result": "OK"
        })

        connected_url = None

        def capture_connect(url):
            nonlocal connected_url
            connected_url = url
            return mock_ws

        with patch('websockets.connect', side_effect=capture_connect):
            with patch('uuid.uuid4', return_value=Mock(__str__=lambda self: "test")):
                await agent._send_task("Prompt", 30.0)

        # Verify URL transformation
        assert connected_url == "wss://relay.example.com/ws/input"

    @pytest.mark.asyncio
    async def test_send_task_output_with_empty_result(self):
        """Test _send_task() handles OUTPUT with empty result."""
        agent = RemoteAgent("0x123", "wss://relay/ws/announce")

        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock()
        mock_ws.recv.return_value = json.dumps({
            "type": "OUTPUT",
            "input_id": "test",
            "result": ""
        })

        with patch('websockets.connect', return_value=mock_ws):
            with patch('uuid.uuid4', return_value=Mock(__str__=lambda self: "test")):
                result = await agent._send_task("Prompt", 30.0)

        assert result == ""

    @pytest.mark.asyncio
    async def test_send_task_output_missing_result_field(self):
        """Test _send_task() handles OUTPUT missing 'result' field."""
        agent = RemoteAgent("0x123", "wss://relay/ws/announce")

        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock()
        mock_ws.recv.return_value = json.dumps({
            "type": "OUTPUT",
            "input_id": "test"
            # No 'result' field
        })

        with patch('websockets.connect', return_value=mock_ws):
            with patch('uuid.uuid4', return_value=Mock(__str__=lambda self: "test")):
                result = await agent._send_task("Prompt", 30.0)

        # Should return empty string when result missing
        assert result == ""


class TestSendTaskErrorHandling:
    """Test _send_task() error handling."""

    @pytest.mark.asyncio
    async def test_send_task_error_message(self):
        """Test _send_task() raises ConnectionError on ERROR message."""
        agent = RemoteAgent("0x123", "wss://relay/ws/announce")

        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)  # Don't suppress exceptions
        mock_ws.recv.return_value = json.dumps({
            "type": "ERROR",
            "error": "Agent not found"
        })

        with patch('websockets.connect', return_value=mock_ws):
            with patch('uuid.uuid4', return_value=Mock(__str__=lambda self: "test")):
                with pytest.raises(ConnectionError) as exc_info:
                    await agent._send_task("Prompt", 30.0)

        assert "Agent error: Agent not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_task_unexpected_response_type(self):
        """Test _send_task() raises ConnectionError on unexpected message type."""
        agent = RemoteAgent("0x123", "wss://relay/ws/announce")

        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)  # Don't suppress exceptions
        mock_ws.recv.return_value = json.dumps({
            "type": "UNKNOWN",
            "data": "something"
        })

        with patch('websockets.connect', return_value=mock_ws):
            with patch('uuid.uuid4', return_value=Mock(__str__=lambda self: "test")):
                with pytest.raises(ConnectionError) as exc_info:
                    await agent._send_task("Prompt", 30.0)

        assert "Unexpected response" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_task_mismatched_input_id(self):
        """Test _send_task() raises error if OUTPUT input_id doesn't match."""
        agent = RemoteAgent("0x123", "wss://relay/ws/announce")

        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)  # Don't suppress exceptions
        mock_ws.recv.return_value = json.dumps({
            "type": "OUTPUT",
            "input_id": "wrong-uuid",
            "result": "Response"
        })

        with patch('websockets.connect', return_value=mock_ws):
            with patch('uuid.uuid4', return_value=Mock(__str__=lambda self: "correct-uuid")):
                with pytest.raises(ConnectionError) as exc_info:
                    await agent._send_task("Prompt", 30.0)

        assert "Unexpected response" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_task_timeout(self):
        """Test _send_task() raises TimeoutError on timeout."""
        agent = RemoteAgent("0x123", "wss://relay/ws/announce")

        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)  # Don't suppress exceptions
        # Simulate timeout by never returning
        mock_ws.recv = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch('websockets.connect', return_value=mock_ws):
            with patch('uuid.uuid4', return_value=Mock(__str__=lambda self: "test")):
                with pytest.raises(asyncio.TimeoutError):
                    await agent._send_task("Prompt", 0.1)


class TestSendTaskWebSocketContext:
    """Test _send_task() WebSocket context management."""

    @pytest.mark.asyncio
    async def test_send_task_uses_async_context_manager(self):
        """Test _send_task() uses async with for WebSocket."""
        agent = RemoteAgent("0x123", "wss://relay/ws/announce")

        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock()
        mock_ws.recv.return_value = json.dumps({
            "type": "OUTPUT",
            "input_id": "test",
            "result": "OK"
        })

        # Track context manager calls
        mock_connect = MagicMock()
        mock_connect.return_value = mock_ws

        with patch('websockets.connect', mock_connect):
            with patch('uuid.uuid4', return_value=Mock(__str__=lambda self: "test")):
                await agent._send_task("Prompt", 30.0)

        # Verify connect was called
        mock_connect.assert_called_once()


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_workflow_sync_input(self):
        """Test full workflow: connect() -> input() -> OUTPUT."""
        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock()
        mock_ws.recv.return_value = json.dumps({
            "type": "OUTPUT",
            "input_id": "test-id",
            "result": "Translation: Hola"
        })

        with patch('websockets.connect', return_value=mock_ws):
            with patch('uuid.uuid4', return_value=Mock(__str__=lambda self: "test-id")):
                agent = connect("0xtranslator")
                result = agent.input("Translate 'hello' to Spanish")

        assert result == "Translation: Hola"

    @pytest.mark.asyncio
    async def test_full_workflow_async_input(self):
        """Test full workflow: connect() -> input_async() -> OUTPUT."""
        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock()
        mock_ws.recv.return_value = json.dumps({
            "type": "OUTPUT",
            "input_id": "async-test",
            "result": "Calculation: 42"
        })

        with patch('websockets.connect', return_value=mock_ws):
            with patch('uuid.uuid4', return_value=Mock(__str__=lambda self: "async-test")):
                agent = connect("0xcalculator")
                result = await agent.input_async("Calculate 6 * 7")

        assert result == "Calculation: 42"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
