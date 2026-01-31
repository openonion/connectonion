"""Unit tests for connectonion/network/io/"""

import threading
import pytest

from connectonion.network.io import IO, WebSocketIO


class TestIOBase:
    """Test IO abstract base class."""

    def test_cannot_instantiate_abstract_class(self):
        """IO is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            IO()
        assert "abstract" in str(exc_info.value).lower()


class TestWebSocketIO:
    """Test WebSocketIO queue-based implementation."""

    def test_init_creates_empty_queues(self):
        """__init__ creates empty outgoing and incoming queues."""
        io = WebSocketIO()

        assert io._outgoing.empty()
        assert io._incoming.empty()
        assert io._closed is False

    def test_send_queues_event(self):
        """send() puts event on outgoing queue with auto-generated id and ts."""
        io = WebSocketIO()

        event = {"type": "thinking"}
        io.send(event)

        queued = io._outgoing.get_nowait()
        assert queued["type"] == "thinking"
        assert "id" in queued  # UUID auto-generated
        assert "ts" in queued  # timestamp auto-generated

    def test_send_preserves_existing_id(self):
        """send() preserves existing id if provided."""
        io = WebSocketIO()

        event = {"type": "tool_call", "id": "custom-id-123"}
        io.send(event)

        queued = io._outgoing.get_nowait()
        assert queued["id"] == "custom-id-123"  # preserved, not overwritten

    def test_send_skips_when_closed(self):
        """send() does nothing when IO is closed."""
        io = WebSocketIO()
        io.close()

        io.send({"type": "thinking"})

        assert io._outgoing.empty()

    def test_receive_returns_from_incoming_queue(self):
        """receive() returns item from incoming queue."""
        io = WebSocketIO()
        io._incoming.put({"approved": True})

        result = io.receive()

        assert result == {"approved": True}

    def test_receive_blocks_until_data(self):
        """receive() blocks until data is available."""
        io = WebSocketIO()
        result_holder = [None]

        def receive_thread():
            result_holder[0] = io.receive()

        thread = threading.Thread(target=receive_thread)
        thread.start()

        # Give thread time to block
        thread.join(timeout=0.05)
        assert thread.is_alive()  # Still blocking

        # Now put data
        io._incoming.put({"approved": True})
        thread.join(timeout=0.1)

        assert not thread.is_alive()
        assert result_holder[0] == {"approved": True}

    def test_close_unblocks_receive(self):
        """close() unblocks any waiting receive() call."""
        io = WebSocketIO()
        result_holder = [None]

        def receive_thread():
            result_holder[0] = io.receive()

        thread = threading.Thread(target=receive_thread)
        thread.start()

        # Give thread time to block
        thread.join(timeout=0.05)
        assert thread.is_alive()

        # Close should unblock
        io.close()
        thread.join(timeout=0.1)

        assert not thread.is_alive()
        assert result_holder[0] == {"type": "io_closed"}


class TestHighLevelAPI:
    """Test high-level API methods (log, request_approval)."""

    def test_log_sends_event_type_only(self):
        """log() with just event type sends minimal event with auto-generated id and ts."""
        io = WebSocketIO()

        io.log("thinking")

        event = io._outgoing.get_nowait()
        assert event["type"] == "thinking"
        assert "id" in event  # UUID auto-generated
        assert "ts" in event  # timestamp auto-generated

    def test_log_with_kwargs(self):
        """log() includes additional kwargs in event with auto-generated id and ts."""
        io = WebSocketIO()

        io.log("tool_call", name="search", arguments={"q": "python"})

        event = io._outgoing.get_nowait()
        assert event["type"] == "tool_call"
        assert event["name"] == "search"
        assert event["arguments"] == {"q": "python"}
        assert "id" in event  # UUID auto-generated
        assert "ts" in event  # timestamp auto-generated

    def test_request_approval_approved(self):
        """request_approval() returns True when client approves."""
        io = WebSocketIO()

        # Simulate client response in another thread
        def respond():
            # Wait for outgoing message
            io._outgoing.get(timeout=1)
            # Send approval
            io._incoming.put({"approved": True})

        thread = threading.Thread(target=respond)
        thread.start()

        result = io.request_approval("delete_file", {"path": "/tmp/x"})

        thread.join(timeout=1)
        assert result is True

    def test_request_approval_rejected(self):
        """request_approval() returns False when client rejects."""
        io = WebSocketIO()

        # Simulate client response in another thread
        def respond():
            io._outgoing.get(timeout=1)
            io._incoming.put({"approved": False})

        thread = threading.Thread(target=respond)
        thread.start()

        result = io.request_approval("delete_file", {"path": "/tmp/x"})

        thread.join(timeout=1)
        assert result is False

    def test_request_approval_missing_key_defaults_false(self):
        """request_approval() returns False when 'approved' key missing."""
        io = WebSocketIO()

        # Simulate client response in another thread
        def respond():
            io._outgoing.get(timeout=1)
            io._incoming.put({})  # No 'approved' key

        thread = threading.Thread(target=respond)
        thread.start()

        result = io.request_approval("delete_file", {"path": "/tmp/x"})

        thread.join(timeout=1)
        assert result is False
