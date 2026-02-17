"""Unit tests for connectonion/network/io/"""
"""
LLM-Note: Tests for io

What it tests:
- Io functionality

Components under test:
- Module: io
"""


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


class TestReceiveAll:
    """Test receive_all() non-blocking message retrieval."""

    def test_receive_all_returns_empty_list_when_empty(self):
        """receive_all() returns empty list when queue is empty."""
        io = WebSocketIO()

        result = io.receive_all()

        assert result == []

    def test_receive_all_returns_all_messages(self):
        """receive_all() returns all pending messages."""
        io = WebSocketIO()
        io._incoming.put({"type": "msg1"})
        io._incoming.put({"type": "msg2"})
        io._incoming.put({"type": "msg3"})

        result = io.receive_all()

        assert len(result) == 3
        assert result[0]["type"] == "msg1"
        assert result[1]["type"] == "msg2"
        assert result[2]["type"] == "msg3"
        assert io._incoming.empty()

    def test_receive_all_with_type_filter(self):
        """receive_all(msg_type) only returns messages of that type."""
        io = WebSocketIO()
        io._incoming.put({"type": "mode_change", "mode": "safe"})
        io._incoming.put({"type": "approval", "approved": True})
        io._incoming.put({"type": "mode_change", "mode": "ulw"})

        result = io.receive_all("mode_change")

        assert len(result) == 2
        assert result[0] == {"type": "mode_change", "mode": "safe"}
        assert result[1] == {"type": "mode_change", "mode": "ulw"}

    def test_receive_all_with_type_filter_keeps_others_in_queue(self):
        """receive_all(msg_type) keeps non-matching messages in queue."""
        io = WebSocketIO()
        io._incoming.put({"type": "mode_change", "mode": "safe"})
        io._incoming.put({"type": "approval", "approved": True})
        io._incoming.put({"type": "mode_change", "mode": "ulw"})

        io.receive_all("mode_change")

        # The approval message should still be in queue
        assert not io._incoming.empty()
        remaining = io._incoming.get_nowait()
        assert remaining == {"type": "approval", "approved": True}
        assert io._incoming.empty()

    def test_receive_all_with_no_matching_type(self):
        """receive_all(msg_type) returns empty list when no matches."""
        io = WebSocketIO()
        io._incoming.put({"type": "approval", "approved": True})
        io._incoming.put({"type": "other", "data": 123})

        result = io.receive_all("mode_change")

        assert result == []
        # All messages should still be in queue
        assert io._incoming.qsize() == 2

    def test_receive_all_is_non_blocking(self):
        """receive_all() returns immediately without blocking."""
        io = WebSocketIO()

        # Should return immediately even with empty queue
        import time
        start = time.time()
        result = io.receive_all()
        elapsed = time.time() - start

        assert result == []
        assert elapsed < 0.1  # Should be nearly instant


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
