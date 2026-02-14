"""Unit tests for IO image support"""

from connectonion.network.io import WebSocketIO


def test_send_image_helper():
    """Test that send_image() sends agent_image event with base64 data."""
    io = WebSocketIO()

    # Test sending an image
    image_data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    io.send_image(image_data)

    # Verify event was queued
    event = io._outgoing.get_nowait()
    assert event["type"] == "agent_image"
    assert event["image"] == image_data
    assert "id" in event  # Auto-generated ID
    assert "ts" in event  # Auto-generated timestamp


def test_send_image_multiple():
    """Test sending multiple images."""
    io = WebSocketIO()

    # Send multiple images
    image1 = "data:image/png;base64,first"
    image2 = "data:image/jpeg;base64,second"

    io.send_image(image1)
    io.send_image(image2)

    # Verify both events were queued
    event1 = io._outgoing.get_nowait()
    event2 = io._outgoing.get_nowait()

    assert event1["type"] == "agent_image"
    assert event1["image"] == image1

    assert event2["type"] == "agent_image"
    assert event2["image"] == image2
