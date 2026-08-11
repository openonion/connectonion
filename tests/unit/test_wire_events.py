"""Provider-neutral IO event vocabulary aligned with ACP tool lifecycles."""

import pytest

from connectonion.core.wire_events import normalize_wire_event


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("pending", "pending"),
        ("running", "in_progress"),
        ("in_progress", "in_progress"),
    ],
)
def test_tool_start_statuses_use_the_acp_vocabulary(source, expected):
    event = {"type": "tool_call", "tool_id": "call-1", "status": source}

    assert normalize_wire_event(event)["status"] == expected
    assert event["status"] == source


def test_tool_start_defaults_to_in_progress_without_mutating_the_trace():
    event = {"type": "tool_call", "tool_id": "call-1"}

    normalized = normalize_wire_event(event)

    assert normalized == {
        "type": "tool_call",
        "tool_id": "call-1",
        "status": "in_progress",
    }
    assert "status" not in event


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("success", "completed"),
        ("done", "completed"),
        ("completed", "completed"),
        ("error", "failed"),
        ("failed", "failed"),
        ("not_found", "failed"),
        ("interrupted", "failed"),
    ],
)
def test_tool_result_statuses_use_the_acp_vocabulary(source, expected):
    event = {"type": "tool_result", "tool_id": "call-1", "status": source}

    assert normalize_wire_event(event)["status"] == expected
    assert event["status"] == source


@pytest.mark.parametrize(
    "event",
    [
        {"type": "tool_call", "status": "completed"},
        {"type": "tool_result"},
        {"type": "tool_result", "status": "mystery"},
    ],
)
def test_invalid_tool_lifecycle_statuses_fail_closed(event):
    with pytest.raises(ValueError, match="tool event status"):
        normalize_wire_event(event)


def test_non_tool_events_are_detached_but_unchanged():
    event = {"type": "thinking", "content": "checking"}

    normalized = normalize_wire_event(event)

    assert normalized == event
    assert normalized is not event
