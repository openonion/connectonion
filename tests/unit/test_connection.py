"""Unit tests for connectonion/network/connection.py"""

import queue
import threading
import pytest
from unittest.mock import Mock

from connectonion.network.connection import Connection, SyncWebSocketConnection
from connectonion.network.asgi import AsyncToSyncConnection


class TestConnectionBase:
    """Test Connection abstract base class."""

    def test_cannot_instantiate_abstract_class(self):
        """Connection is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            Connection()
        assert "abstract" in str(exc_info.value).lower()


class TestSyncWebSocketConnection:
    """Test SyncWebSocketConnection implementation."""

    def test_init_stores_callbacks(self):
        """__init__ stores send and receive callbacks."""
        mock_send = Mock()
        mock_receive = Mock()

        conn = SyncWebSocketConnection(mock_send, mock_receive)

        assert conn._send == mock_send
        assert conn._receive == mock_receive

    def test_send_calls_callback(self):
        """send() calls the send callback with event."""
        mock_send = Mock()
        mock_receive = Mock()
        conn = SyncWebSocketConnection(mock_send, mock_receive)

        event = {"type": "thinking"}
        conn.send(event)

        mock_send.assert_called_once_with(event)

    def test_receive_calls_callback(self):
        """receive() calls the receive callback and returns result."""
        mock_send = Mock()
        mock_receive = Mock(return_value={"approved": True})
        conn = SyncWebSocketConnection(mock_send, mock_receive)

        result = conn.receive()

        assert result == {"approved": True}
        mock_receive.assert_called_once()


class TestAsyncToSyncConnection:
    """Test AsyncToSyncConnection queue-based implementation."""

    def test_init_creates_empty_queues(self):
        """__init__ creates empty outgoing and incoming queues."""
        conn = AsyncToSyncConnection()

        assert conn._outgoing.empty()
        assert conn._incoming.empty()
        assert conn._closed is False

    def test_send_queues_event(self):
        """send() puts event on outgoing queue."""
        conn = AsyncToSyncConnection()

        event = {"type": "thinking"}
        conn.send(event)

        assert conn._outgoing.get_nowait() == event

    def test_send_skips_when_closed(self):
        """send() does nothing when connection is closed."""
        conn = AsyncToSyncConnection()
        conn.close()

        conn.send({"type": "thinking"})

        assert conn._outgoing.empty()

    def test_receive_returns_from_incoming_queue(self):
        """receive() returns item from incoming queue."""
        conn = AsyncToSyncConnection()
        conn._incoming.put({"approved": True})

        result = conn.receive()

        assert result == {"approved": True}

    def test_receive_blocks_until_data(self):
        """receive() blocks until data is available."""
        conn = AsyncToSyncConnection()
        result_holder = [None]

        def receive_thread():
            result_holder[0] = conn.receive()

        thread = threading.Thread(target=receive_thread)
        thread.start()

        # Give thread time to block
        thread.join(timeout=0.05)
        assert thread.is_alive()  # Still blocking

        # Now put data
        conn._incoming.put({"approved": True})
        thread.join(timeout=0.1)

        assert not thread.is_alive()
        assert result_holder[0] == {"approved": True}

    def test_close_unblocks_receive(self):
        """close() unblocks any waiting receive() call."""
        conn = AsyncToSyncConnection()
        result_holder = [None]

        def receive_thread():
            result_holder[0] = conn.receive()

        thread = threading.Thread(target=receive_thread)
        thread.start()

        # Give thread time to block
        thread.join(timeout=0.05)
        assert thread.is_alive()

        # Close should unblock
        conn.close()
        thread.join(timeout=0.1)

        assert not thread.is_alive()
        assert result_holder[0] == {"type": "connection_closed"}


class TestHighLevelAPI:
    """Test high-level API methods (log, request_approval)."""

    def test_log_sends_event_type_only(self):
        """log() with just event type sends minimal event."""
        mock_send = Mock()
        mock_receive = Mock()
        conn = SyncWebSocketConnection(mock_send, mock_receive)

        conn.log("thinking")

        mock_send.assert_called_once_with({"type": "thinking"})

    def test_log_with_kwargs(self):
        """log() includes additional kwargs in event."""
        mock_send = Mock()
        mock_receive = Mock()
        conn = SyncWebSocketConnection(mock_send, mock_receive)

        conn.log("tool_call", name="search", arguments={"q": "python"})

        mock_send.assert_called_once_with({
            "type": "tool_call",
            "name": "search",
            "arguments": {"q": "python"}
        })

    def test_request_approval_approved(self):
        """request_approval() returns True when client approves."""
        mock_send = Mock()
        mock_receive = Mock(return_value={"approved": True})
        conn = SyncWebSocketConnection(mock_send, mock_receive)

        result = conn.request_approval("delete_file", {"path": "/tmp/x"})

        assert result is True
        mock_send.assert_called_once()
        sent_event = mock_send.call_args[0][0]
        assert sent_event["type"] == "approval_needed"
        assert sent_event["tool"] == "delete_file"
        assert sent_event["arguments"] == {"path": "/tmp/x"}

    def test_request_approval_rejected(self):
        """request_approval() returns False when client rejects."""
        mock_send = Mock()
        mock_receive = Mock(return_value={"approved": False})
        conn = SyncWebSocketConnection(mock_send, mock_receive)

        result = conn.request_approval("delete_file", {"path": "/tmp/x"})

        assert result is False

    def test_request_approval_missing_key_defaults_false(self):
        """request_approval() returns False when 'approved' key missing."""
        mock_send = Mock()
        mock_receive = Mock(return_value={})  # No 'approved' key
        conn = SyncWebSocketConnection(mock_send, mock_receive)

        result = conn.request_approval("delete_file", {"path": "/tmp/x"})

        assert result is False

    def test_request_approval_with_async_connection(self):
        """request_approval() works with AsyncToSyncConnection."""
        conn = AsyncToSyncConnection()

        # Simulate client response in another thread
        def respond():
            # Wait for outgoing message
            conn._outgoing.get(timeout=1)
            # Send approval
            conn._incoming.put({"approved": True})

        thread = threading.Thread(target=respond)
        thread.start()

        result = conn.request_approval("send_email", {"to": "test@example.com"})

        thread.join(timeout=1)
        assert result is True
