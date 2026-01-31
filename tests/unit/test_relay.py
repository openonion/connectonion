#!/usr/bin/env python3
"""
Unit tests for relay.py - WebSocket relay client functionality.

Tests cover:
- WebSocket connection establishment
- ANNOUNCE message sending
- INPUT message receiving (with/without timeout)
- OUTPUT message sending
- Serve loop with heartbeat mechanism
- Error handling (ConnectionClosed, TimeoutError, malformed JSON)

All tests use mocked WebSocket connections to avoid network dependencies.
"""

import pytest
import json
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from connectonion.network import relay
import websockets


class TestRelayConnection:
    """Test relay connection establishment."""

    @pytest.mark.asyncio
    async def test_connect_default_url(self):
        """Test connecting to default relay URL."""
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value = mock_ws

            result = await relay.connect()

            # Should connect to production relay
            mock_connect.assert_called_once_with("wss://oo.openonion.ai/ws/announce")
            assert result == mock_ws

    @pytest.mark.asyncio
    async def test_connect_custom_url(self):
        """Test connecting to custom relay URL."""
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_connect.return_value = mock_ws
            custom_url = "ws://localhost:8000"

            result = await relay.connect(custom_url)

            # Base URL should have /ws/announce appended
            mock_connect.assert_called_once_with("ws://localhost:8000/ws/announce")
            assert result == mock_ws

    @pytest.mark.asyncio
    async def test_connect_handles_connection_error(self):
        """Test connection error handling."""
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = websockets.exceptions.WebSocketException("Connection failed")

            with pytest.raises(websockets.exceptions.WebSocketException):
                await relay.connect()


class TestAnnounceMessage:
    """Test ANNOUNCE message sending."""

    @pytest.mark.asyncio
    async def test_send_announce_success(self):
        """Test successfully sending ANNOUNCE message."""
        mock_ws = AsyncMock()
        announce_msg = {
            "type": "ANNOUNCE",
            "address": "0x1234567890abcdef",
            "short_address": "co1234",
            "description": "Test agent",
            "capabilities": ["math", "search"],
            "timestamp": 1234567890,
            "signature": "0xsignature..."
        }

        await relay.send_announce(mock_ws, announce_msg)

        # Verify message was sent as JSON
        mock_ws.send.assert_called_once()
        sent_data = mock_ws.send.call_args[0][0]
        assert json.loads(sent_data) == announce_msg

    @pytest.mark.asyncio
    async def test_send_announce_serializes_correctly(self):
        """Test that ANNOUNCE message is properly JSON serialized."""
        mock_ws = AsyncMock()
        announce_msg = {
            "type": "ANNOUNCE",
            "address": "0xtest",
            "timestamp": 12345
        }

        await relay.send_announce(mock_ws, announce_msg)

        sent_data = mock_ws.send.call_args[0][0]
        # Should be valid JSON string
        parsed = json.loads(sent_data)
        assert parsed["type"] == "ANNOUNCE"
        assert parsed["address"] == "0xtest"
        assert parsed["timestamp"] == 12345


class TestWaitForTask:
    """Test INPUT message receiving with timeout handling."""

    @pytest.mark.asyncio
    async def test_wait_for_task_receives_input(self):
        """Test receiving INPUT message successfully."""
        mock_ws = AsyncMock()
        input_msg = {
            "type": "INPUT",
            "input_id": "abc123",
            "prompt": "Calculate 2+2",
            "from_address": "0xsender"
        }
        mock_ws.recv.return_value = json.dumps(input_msg)

        result = await relay.wait_for_task(mock_ws)

        assert result == input_msg
        assert result["type"] == "INPUT"
        assert result["prompt"] == "Calculate 2+2"

    @pytest.mark.asyncio
    async def test_wait_for_task_with_timeout_success(self):
        """Test receiving INPUT message within timeout."""
        mock_ws = AsyncMock()
        input_msg = {"type": "INPUT", "input_id": "123", "prompt": "test"}
        mock_ws.recv.return_value = json.dumps(input_msg)

        result = await relay.wait_for_task(mock_ws, timeout=5.0)

        assert result == input_msg
        mock_ws.recv.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_task_timeout_expires(self):
        """Test timeout raises asyncio.TimeoutError."""
        mock_ws = AsyncMock()
        # Simulate slow response
        async def slow_recv():
            await asyncio.sleep(10)
            return json.dumps({"type": "INPUT"})

        mock_ws.recv = slow_recv

        with pytest.raises(asyncio.TimeoutError):
            await relay.wait_for_task(mock_ws, timeout=0.1)

    @pytest.mark.asyncio
    async def test_wait_for_task_no_timeout(self):
        """Test waiting indefinitely when no timeout specified."""
        mock_ws = AsyncMock()
        input_msg = {"type": "INPUT", "input_id": "xyz", "prompt": "wait forever"}
        mock_ws.recv.return_value = json.dumps(input_msg)

        result = await relay.wait_for_task(mock_ws, timeout=None)

        assert result == input_msg
        # recv should be called without timeout wrapper
        mock_ws.recv.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_task_handles_malformed_json(self):
        """Test error handling for malformed JSON."""
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = "not valid json{"

        with pytest.raises(json.JSONDecodeError):
            await relay.wait_for_task(mock_ws)

    @pytest.mark.asyncio
    async def test_wait_for_task_handles_connection_closed(self):
        """Test error handling when connection closes."""
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = websockets.exceptions.ConnectionClosed(None, None)

        with pytest.raises(websockets.exceptions.ConnectionClosed):
            await relay.wait_for_task(mock_ws)


class TestSendResponse:
    """Test OUTPUT message sending."""

    @pytest.mark.asyncio
    async def test_send_response_success(self):
        """Test sending successful OUTPUT message."""
        mock_ws = AsyncMock()

        await relay.send_response(mock_ws, "input123", "Result: 42", success=True)

        mock_ws.send.assert_called_once()
        sent_data = mock_ws.send.call_args[0][0]
        output_msg = json.loads(sent_data)

        assert output_msg["type"] == "OUTPUT"
        assert output_msg["input_id"] == "input123"
        assert output_msg["result"] == "Result: 42"
        assert output_msg["success"] is True

    @pytest.mark.asyncio
    async def test_send_response_failure(self):
        """Test sending failed OUTPUT message."""
        mock_ws = AsyncMock()

        await relay.send_response(mock_ws, "input456", "Error: failed", success=False)

        sent_data = mock_ws.send.call_args[0][0]
        output_msg = json.loads(sent_data)

        assert output_msg["success"] is False
        assert output_msg["result"] == "Error: failed"

    @pytest.mark.asyncio
    async def test_send_response_default_success(self):
        """Test that success defaults to True."""
        mock_ws = AsyncMock()

        await relay.send_response(mock_ws, "id789", "Done")

        sent_data = mock_ws.send.call_args[0][0]
        output_msg = json.loads(sent_data)

        assert output_msg["success"] is True


class TestServeLoop:
    """Test main serving loop with heartbeat and task handling."""

    @pytest.mark.asyncio
    async def test_serve_loop_sends_initial_announce(self):
        """Test that serve_loop sends initial ANNOUNCE on startup."""
        mock_ws = AsyncMock()
        announce_msg = {
            "type": "ANNOUNCE",
            "address": "0xtest",
            "timestamp": 12345
        }

        # Make wait_for_task raise ConnectionClosed immediately to exit loop
        mock_ws.recv.side_effect = websockets.exceptions.ConnectionClosed(None, None)

        async def dummy_handler(prompt):
            return "response"

        with patch('builtins.print'):  # Suppress print output
            await relay.serve_loop(mock_ws, announce_msg, dummy_handler)

        # Should have sent initial ANNOUNCE
        assert mock_ws.send.call_count >= 1
        first_call = mock_ws.send.call_args_list[0][0][0]
        sent_msg = json.loads(first_call)
        assert sent_msg["type"] == "ANNOUNCE"

    @pytest.mark.asyncio
    async def test_serve_loop_processes_input_message(self):
        """Test that INPUT messages are processed by task_handler."""
        mock_ws = AsyncMock()
        announce_msg = {"type": "ANNOUNCE", "address": "0xtest", "timestamp": 1}

        input_msg = {
            "type": "INPUT",
            "input_id": "task123",
            "prompt": "Calculate 5+5",
            "from_address": "0xsender"
        }

        # First recv: INPUT message, second recv: ConnectionClosed to exit
        mock_ws.recv.side_effect = [
            json.dumps(input_msg),
            websockets.exceptions.ConnectionClosed(None, None)
        ]

        handler_called = False
        handler_prompt = None

        async def test_handler(prompt):
            nonlocal handler_called, handler_prompt
            handler_called = True
            handler_prompt = prompt
            return "10"

        with patch('builtins.print'):
            await relay.serve_loop(mock_ws, announce_msg, test_handler)

        # Verify handler was called with prompt
        assert handler_called
        assert handler_prompt == "Calculate 5+5"

        # Verify OUTPUT was sent
        sent_calls = [call[0][0] for call in mock_ws.send.call_args_list]
        output_sent = False
        for call_data in sent_calls:
            msg = json.loads(call_data)
            if msg.get("type") == "OUTPUT":
                assert msg["input_id"] == "task123"
                assert msg["result"] == "10"
                output_sent = True

        assert output_sent, "OUTPUT message should have been sent"

    @pytest.mark.asyncio
    async def test_serve_loop_handles_error_message(self):
        """Test that ERROR messages from relay are handled gracefully."""
        mock_ws = AsyncMock()
        announce_msg = {"type": "ANNOUNCE", "address": "0xtest", "timestamp": 1}

        error_msg = {
            "type": "ERROR",
            "error": "Invalid signature"
        }

        mock_ws.recv.side_effect = [
            json.dumps(error_msg),
            websockets.exceptions.ConnectionClosed(None, None)
        ]

        async def dummy_handler(prompt):
            return "response"

        # Should print error but not crash
        with patch('builtins.print') as mock_print:
            await relay.serve_loop(mock_ws, announce_msg, dummy_handler)

            # Check that error was printed
            print_calls = [str(call) for call in mock_print.call_args_list]
            error_printed = any("Error from relay" in str(call) for call in print_calls)
            assert error_printed

    @pytest.mark.asyncio
    async def test_serve_loop_heartbeat_on_timeout(self):
        """Test that heartbeat ANNOUNCE is sent after timeout."""
        mock_ws = AsyncMock()
        announce_msg = {
            "type": "ANNOUNCE",
            "address": "0xtest",
            "timestamp": 12345
        }

        # First recv: timeout (for heartbeat), second recv: ConnectionClosed to exit
        async def recv_with_timeout_then_close():
            # First call raises TimeoutError
            if not hasattr(recv_with_timeout_then_close, 'called'):
                recv_with_timeout_then_close.called = True
                raise asyncio.TimeoutError()
            # Second call closes connection
            raise websockets.exceptions.ConnectionClosed(None, None)

        mock_ws.recv.side_effect = recv_with_timeout_then_close

        async def dummy_handler(prompt):
            return "response"

        with patch('builtins.print') as mock_print:
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.time.return_value = 99999
                await relay.serve_loop(mock_ws, announce_msg, dummy_handler, heartbeat_interval=1)

        # Should have sent at least 2 ANNOUNCEs (initial + heartbeat)
        announce_count = sum(
            1 for call in mock_ws.send.call_args_list
            if json.loads(call[0][0]).get("type") == "ANNOUNCE"
        )
        assert announce_count >= 2, "Should send initial ANNOUNCE + heartbeat ANNOUNCE"

    @pytest.mark.asyncio
    async def test_serve_loop_exits_on_connection_closed(self):
        """Test that serve_loop exits gracefully when connection closes."""
        mock_ws = AsyncMock()
        announce_msg = {"type": "ANNOUNCE", "address": "0xtest", "timestamp": 1}

        mock_ws.recv.side_effect = websockets.exceptions.ConnectionClosed(None, None)

        async def dummy_handler(prompt):
            return "response"

        with patch('builtins.print') as mock_print:
            await relay.serve_loop(mock_ws, announce_msg, dummy_handler)

            # Should print connection closed message
            print_calls = [str(call) for call in mock_print.call_args_list]
            closed_printed = any("Connection to relay closed" in str(call) for call in print_calls)
            assert closed_printed

    @pytest.mark.asyncio
    async def test_serve_loop_custom_heartbeat_interval(self):
        """Test that serve_loop accepts custom heartbeat interval without errors."""
        mock_ws = AsyncMock()
        announce_msg = {"type": "ANNOUNCE", "address": "0xtest", "timestamp": 1}

        # Simulate timeout after custom interval
        call_count = 0

        async def recv_with_custom_interval():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: timeout (triggers heartbeat)
                raise asyncio.TimeoutError()
            else:
                # Second call: close connection
                raise websockets.exceptions.ConnectionClosed(None, None)

        mock_ws.recv.side_effect = recv_with_custom_interval

        async def dummy_handler(prompt):
            return "response"

        with patch('builtins.print'):
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.time.return_value = 99999
                # Should complete without error with custom interval
                await relay.serve_loop(mock_ws, announce_msg, dummy_handler, heartbeat_interval=120)

        # Verify serve_loop ran and sent heartbeat
        assert call_count >= 2, "Should have handled timeout and then connection close"


class TestRelayIntegration:
    """Integration tests combining multiple relay functions."""

    @pytest.mark.asyncio
    async def test_full_message_flow(self):
        """Test complete flow: connect → announce → receive INPUT → send OUTPUT."""
        mock_ws = AsyncMock()

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws):
            # Connect
            ws = await relay.connect("ws://test")
            assert ws == mock_ws

            # Send ANNOUNCE
            announce_msg = {"type": "ANNOUNCE", "address": "0xtest"}
            await relay.send_announce(ws, announce_msg)

            # Receive INPUT
            input_msg = {"type": "INPUT", "input_id": "123", "prompt": "test"}
            mock_ws.recv.return_value = json.dumps(input_msg)
            task = await relay.wait_for_task(ws)
            assert task["input_id"] == "123"

            # Send OUTPUT
            await relay.send_response(ws, "123", "result")

            # Verify all messages were sent
            assert mock_ws.send.call_count == 2  # ANNOUNCE + OUTPUT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
