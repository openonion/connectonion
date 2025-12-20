#!/usr/bin/env python3
"""
Unit tests for connect.py - remote agent connection.

Tests cover:
- RemoteAgent initialization
- connect() factory function
- input() synchronous method (with event loop detection)
- input_async() asynchronous method
- _sign_payload() signing helper
- _send_task() WebSocket communication
- Session management for multi-turn conversations
- OUTPUT message handling
- ERROR message handling
- Timeout handling
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from connectonion.network.connect import RemoteAgent, connect


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
        agent = RemoteAgent("0x123abc", relay_url="wss://relay.example.com/ws/announce")
        assert agent.address == "0x123abc"

    def test_init_stores_relay_url(self):
        """Test that __init__ stores relay URL."""
        agent = RemoteAgent("0x123", relay_url="ws://localhost:8000/ws/announce")
        assert agent._relay_url == "ws://localhost:8000/ws/announce"

    def test_init_default_relay_url(self):
        """Test that __init__ uses default relay URL."""
        agent = RemoteAgent("0x123")
        assert agent._relay_url == "wss://oo.openonion.ai/ws/announce"

    def test_init_with_keys(self):
        """Test that __init__ stores signing keys."""
        keys = {"address": "0xmykey", "private_key": b"secret"}
        agent = RemoteAgent("0x123", keys=keys)
        assert agent._keys == keys

    def test_init_session_is_none(self):
        """Test that __init__ initializes session as None."""
        agent = RemoteAgent("0x123")
        assert agent._session is None

    def test_init_cached_endpoint_is_none(self):
        """Test that __init__ initializes cached endpoint as None."""
        agent = RemoteAgent("0x123")
        assert agent._cached_endpoint is None


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

    def test_repr_exactly_12_chars(self):
        """Test __repr__ with exactly 12-char address (no truncation)."""
        agent = RemoteAgent("0x1234567890")
        assert repr(agent) == "RemoteAgent(0x1234567890)"

    def test_repr_13_chars_gets_truncated(self):
        """Test __repr__ with 13-char address (gets truncated)."""
        agent = RemoteAgent("0x12345678901")
        assert repr(agent) == "RemoteAgent(0x1234567890...)"


class TestRemoteAgentInput:
    """Test input() synchronous method."""

    def test_input_calls_send_task(self):
        """Test that input() calls _send_task via asyncio.run."""
        agent = RemoteAgent("0x123")
        agent._send_task = AsyncMock(return_value="Test response")
        agent._discover_endpoints = AsyncMock(return_value=[])

        with patch('asyncio.run', return_value="Test response") as mock_run:
            with patch('asyncio.get_running_loop', side_effect=RuntimeError("no loop")):
                result = agent.input("Test prompt")

        assert result == "Test response"

    def test_input_with_custom_timeout(self):
        """Test input() passes custom timeout to _send_task."""
        agent = RemoteAgent("0x123")
        agent._send_task = AsyncMock(return_value="Response")
        agent._discover_endpoints = AsyncMock(return_value=[])

        with patch('asyncio.run', return_value="Response"):
            with patch('asyncio.get_running_loop', side_effect=RuntimeError("no loop")):
                result = agent.input("Prompt", timeout=60.0)

        assert result == "Response"

    def test_input_raises_in_async_context(self):
        """Test input() raises clear error when called from async context."""
        async def test():
            agent = RemoteAgent("0x123")
            with pytest.raises(RuntimeError) as exc_info:
                agent.input("Test")
            assert "input_async" in str(exc_info.value)
            assert "async context" in str(exc_info.value)

        asyncio.run(test())


class TestRemoteAgentInputAsync:
    """Test input_async() asynchronous method."""

    @pytest.mark.asyncio
    async def test_input_async_calls_send_task(self):
        """Test that input_async() calls _send_task directly."""
        agent = RemoteAgent("0x123")
        agent._send_task = AsyncMock(return_value="Async response")

        result = await agent.input_async("Test prompt")

        agent._send_task.assert_called_once_with("Test prompt", 30.0)
        assert result == "Async response"

    @pytest.mark.asyncio
    async def test_input_async_with_custom_timeout(self):
        """Test input_async() passes custom timeout."""
        agent = RemoteAgent("0x123")
        agent._send_task = AsyncMock(return_value="Response")

        result = await agent.input_async("Prompt", timeout=45.0)

        agent._send_task.assert_called_once_with("Prompt", 45.0)
        assert result == "Response"


class TestSignPayload:
    """Test _sign_payload() helper method."""

    def test_sign_payload_without_keys(self):
        """Test _sign_payload returns simple body when no keys."""
        agent = RemoteAgent("0x123")
        payload = {"prompt": "Hello", "to": "0x123", "timestamp": 12345}

        result = agent._sign_payload(payload)

        assert result == {"prompt": "Hello"}

    def test_sign_payload_with_keys(self):
        """Test _sign_payload returns signed body when keys provided."""
        keys = {
            "address": "0xmyaddress",
            "private_key": b'\x00' * 32,
            "public_key": b'\x00' * 32
        }
        agent = RemoteAgent("0x123", keys=keys)
        payload = {"prompt": "Hello", "to": "0x123", "timestamp": 12345}

        from connectonion import address as addr_module
        with patch.object(addr_module, 'sign', return_value=b'\xab\xcd'):
            result = agent._sign_payload(payload)

        assert "payload" in result
        assert result["payload"] == payload
        assert result["from"] == "0xmyaddress"
        assert result["signature"] == "abcd"


class TestSessionManagement:
    """Test session management for multi-turn conversations."""

    def test_reset_conversation_clears_session(self):
        """Test reset_conversation() clears session state."""
        agent = RemoteAgent("0x123")
        agent._session = {"session_id": "abc", "messages": []}

        agent.reset_conversation()

        assert agent._session is None

    def test_create_signed_body_includes_session(self):
        """Test _create_signed_body includes session when present."""
        agent = RemoteAgent("0x123")
        agent._session = {"session_id": "abc123"}

        body = agent._create_signed_body("Hello")

        assert "session" in body
        assert body["session"]["session_id"] == "abc123"

    def test_create_signed_body_no_session(self):
        """Test _create_signed_body works without session."""
        agent = RemoteAgent("0x123")

        body = agent._create_signed_body("Hello")

        assert "session" not in body


class TestSendTaskOutputHandling:
    """Test _send_task() OUTPUT message handling."""

    @pytest.mark.asyncio
    async def test_send_task_successful_output(self):
        """Test _send_task() handles OUTPUT message correctly."""
        agent = RemoteAgent("0x123")
        agent._discover_endpoints = AsyncMock(return_value=[])

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
        agent = RemoteAgent("0xagent123")
        agent._discover_endpoints = AsyncMock(return_value=[])

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

        assert sent_message["type"] == "INPUT"
        assert sent_message["input_id"] == "uuid-123"
        assert sent_message["to"] == "0xagent123"

    @pytest.mark.asyncio
    async def test_send_task_transforms_relay_url(self):
        """Test _send_task() transforms /ws/announce to /ws/input."""
        agent = RemoteAgent("0x123", relay_url="wss://relay.example.com/ws/announce")
        agent._discover_endpoints = AsyncMock(return_value=[])

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

        assert connected_url == "wss://relay.example.com/ws/input"


class TestSendTaskErrorHandling:
    """Test _send_task() error handling."""

    @pytest.mark.asyncio
    async def test_send_task_error_message(self):
        """Test _send_task() raises ConnectionError on ERROR message."""
        agent = RemoteAgent("0x123")
        agent._discover_endpoints = AsyncMock(return_value=[])

        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)
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
        agent = RemoteAgent("0x123")
        agent._discover_endpoints = AsyncMock(return_value=[])

        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)
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
    async def test_send_task_timeout(self):
        """Test _send_task() raises TimeoutError on timeout."""
        agent = RemoteAgent("0x123")
        agent._discover_endpoints = AsyncMock(return_value=[])

        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)
        mock_ws.recv = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch('websockets.connect', return_value=mock_ws):
            with patch('uuid.uuid4', return_value=Mock(__str__=lambda self: "test")):
                with pytest.raises(asyncio.TimeoutError):
                    await agent._send_task("Prompt", 0.1)


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
