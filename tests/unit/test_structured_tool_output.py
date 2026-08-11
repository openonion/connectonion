"""Structured tool output is bounded, detached, and wire-only."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from connectonion import Agent
from connectonion.core.llm import LLMResponse, ToolCall
from connectonion.core.tool_executor import (
    STRUCTURED_OUTPUT_MAX_BYTES,
    STRUCTURED_OUTPUT_MAX_DEPTH,
    _structured_tool_output,
)
from tests.utils.mock_helpers import MockLLM


def response(
    content: str = "done",
    *,
    tool_calls: list[ToolCall] | None = None,
) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=tool_calls or [],
        raw_response={},
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        42,
        -3.5,
        "hello",
        [1, "two", None, {"ok": True}],
        {"items": [1, 2], "meta": {"ready": True}},
    ],
)
def test_json_native_values_are_detached(value):
    accepted, detached = _structured_tool_output(value)

    assert accepted is True
    assert detached == value
    if isinstance(value, (dict, list)):
        assert detached is not value


@pytest.mark.parametrize(
    "value",
    [
        b"secret",
        bytearray(b"secret"),
        Path("report.txt"),
        (1, 2),
        {1: "non-string key"},
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_non_json_or_non_interoperable_values_fall_back(value):
    assert _structured_tool_output(value) == (False, None)


def test_custom_objects_are_not_introspected():
    class ModelLike:
        @property
        def model_dump(self):
            raise AssertionError("custom attributes must not be inspected")

    assert _structured_tool_output(ModelLike()) == (False, None)


def test_pydantic_models_are_not_implicitly_serialized():
    class Payload(BaseModel):
        value: int

    assert _structured_tool_output(Payload(value=1)) == (False, None)


def test_cycles_fall_back_without_recursing_forever():
    value = []
    value.append(value)

    assert _structured_tool_output(value) == (False, None)


def test_shared_non_cyclic_values_are_copied_normally():
    shared = [1, 2]
    value = [shared, shared]

    accepted, detached = _structured_tool_output(value)

    assert accepted is True
    assert detached == [[1, 2], [1, 2]]
    assert detached[0] is not shared
    assert detached[1] is not shared


def test_container_depth_has_an_exact_boundary():
    at_limit = "leaf"
    for _ in range(STRUCTURED_OUTPUT_MAX_DEPTH):
        at_limit = [at_limit]

    accepted, _detached = _structured_tool_output(at_limit)
    assert accepted is True
    assert _structured_tool_output([at_limit]) == (False, None)


def test_compact_utf8_size_has_an_exact_boundary():
    # A compact JSON string adds exactly two quote bytes for plain ASCII.
    at_limit = "x" * (STRUCTURED_OUTPUT_MAX_BYTES - 2)
    over_limit = at_limit + "x"

    assert _structured_tool_output(at_limit)[0] is True
    assert _structured_tool_output(over_limit) == (False, None)


def test_detached_output_does_not_follow_later_mutation():
    original = {"items": [{"value": 1}]}

    accepted, detached = _structured_tool_output(original)
    original["items"][0]["value"] = 99
    original["items"].append({"value": 2})

    assert accepted is True
    assert detached == {"items": [{"value": 1}]}


class CaptureIO:
    def __init__(self):
        self.events: list[dict] = []
        self.snapshots: list[dict] = []

    def send(self, event: dict) -> None:
        self.events.append(event)
        self.snapshots.append(deepcopy(event))

    def receive_all(self, message_type: str | None = None) -> list[dict]:
        return []


def test_agent_streams_structured_result_without_persisting_it(tmp_path):
    returned = {"items": [{"id": 1}], "count": 1}

    def lookup() -> dict:
        """Return structured search results."""
        return returned

    llm = MockLLM(responses=[
        response(tool_calls=[ToolCall(name="lookup", arguments={}, id="call-1")]),
        response("complete"),
    ])
    agent = Agent(
        name="structured-wire",
        tools=[lookup],
        llm=llm,
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )
    io = CaptureIO()
    agent.io = io

    assert agent.input("look it up") == "complete"

    wire_result = next(event for event in io.events if event.get("type") == "tool_result")
    tool_call_index = next(
        index for index, event in enumerate(io.events) if event.get("type") == "tool_call"
    )
    tool_result_index = io.events.index(wire_result)
    trace_result = next(
        event
        for event in agent.current_session["trace"]
        if event.get("type") == "tool_result"
    )
    assert wire_result["raw_output"] == returned
    assert tool_call_index < tool_result_index
    assert wire_result["id"] == trace_result["id"]
    assert wire_result["ts"] == trace_result["ts"]
    assert wire_result is not trace_result
    assert "raw_output" not in trace_result
    assert all(
        "raw_output" not in event
        for event in agent.current_session["trace"]
    )
    assert llm.calls[1]["messages"][-1] == {
        "role": "tool",
        "content": str(returned),
        "tool_call_id": "call-1",
    }

    returned["items"][0]["id"] = 99
    assert wire_result["raw_output"] == {"items": [{"id": 1}], "count": 1}


def test_fallback_result_keeps_existing_wire_and_persisted_shape(tmp_path):
    def read_bytes() -> bytes:
        """Return bytes that must use the string compatibility path."""
        return b"data"

    agent = Agent(
        name="fallback-wire",
        tools=[read_bytes],
        llm=MockLLM(responses=[
            response(tool_calls=[ToolCall(name="read_bytes", arguments={}, id="call-1")]),
            response("complete"),
        ]),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )
    io = CaptureIO()
    agent.io = io

    assert agent.input("read") == "complete"

    wire_result = next(event for event in io.events if event.get("type") == "tool_result")
    assert wire_result["result"] == "b'data'"
    assert "raw_output" not in wire_result


def test_session_sync_never_contains_structured_wire_output(tmp_path):
    def lookup() -> dict:
        """Return a nested object."""
        return {"private": {"value": "wire-only"}}

    agent = Agent(
        name="canonical-sync",
        tools=[lookup],
        llm=MockLLM(responses=[
            response(tool_calls=[ToolCall(name="lookup", arguments={}, id="call-1")]),
            response("complete"),
        ]),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )
    io = CaptureIO()
    agent.io = io

    agent.input("look up")

    syncs = [event for event in io.snapshots if event.get("type") == "session_sync"]
    assert syncs
    assert all(
        "raw_output" not in trace_entry
        for sync in syncs
        for trace_entry in sync["session"]["trace"]
    )


def test_projection_failure_cannot_change_successful_tool_semantics(tmp_path):
    def lookup() -> dict:
        """Return a result even if optional projection fails."""
        return {"value": 1}

    llm = MockLLM(responses=[
        response(tool_calls=[ToolCall(name="lookup", arguments={}, id="call-1")]),
        response("complete"),
    ])
    agent = Agent(
        name="projection-fallback",
        tools=[lookup],
        llm=llm,
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )
    io = CaptureIO()
    agent.io = io

    with patch(
        "connectonion.core.tool_executor._structured_tool_output",
        side_effect=RuntimeError("dictionary changed size during iteration"),
    ):
        assert agent.input("look up") == "complete"

    wire_result = next(event for event in io.events if event.get("type") == "tool_result")
    trace_result = next(
        event for event in agent.current_session["trace"]
        if event.get("type") == "tool_result"
    )
    assert wire_result["result"] == "{'value': 1}"
    assert "raw_output" not in wire_result
    assert trace_result["status"] == "success"
    assert "error" not in trace_result
    assert llm.calls[1]["messages"][-1]["content"] == "{'value': 1}"


def test_aba_mutation_omits_raw_and_keeps_existing_string(tmp_path):
    returned = {"value": 1}

    def lookup() -> dict:
        """Return a value that changes while the wire snapshot is built."""
        return returned

    def snapshot_then_restore(value):
        value["value"] = 2
        detached = dict(value)
        value["value"] = 1
        return True, detached

    llm = MockLLM(responses=[
        response(tool_calls=[ToolCall(name="lookup", arguments={}, id="call-1")]),
        response("complete"),
    ])
    agent = Agent(
        name="stable-snapshot",
        tools=[lookup],
        llm=llm,
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )
    io = CaptureIO()
    agent.io = io

    with patch(
        "connectonion.core.tool_executor._structured_tool_output",
        side_effect=snapshot_then_restore,
    ):
        assert agent.input("look up") == "complete"

    wire_result = next(event for event in io.events if event.get("type") == "tool_result")
    trace_result = next(
        event for event in agent.current_session["trace"]
        if event.get("type") == "tool_result"
    )
    assert returned == {"value": 1}
    assert "raw_output" not in wire_result
    assert wire_result["result"] == "{'value': 1}"
    assert trace_result["result"] == "{'value': 1}"
    assert llm.calls[1]["messages"][-1]["content"] == "{'value': 1}"


@pytest.mark.parametrize("failure_point", ["tool_result", "session_sync"])
def test_transport_failure_does_not_reclassify_or_duplicate_success(
    tmp_path,
    failure_point,
):
    class FailingIO(CaptureIO):
        def __init__(self):
            super().__init__()
            self.saw_tool_result = False
            self.failed = False

        def send(self, event: dict) -> None:
            event_type = event.get("type")
            should_fail = (
                failure_point == "tool_result" and event_type == "tool_result"
            ) or (
                failure_point == "session_sync"
                and self.saw_tool_result
                and event_type == "session_sync"
            )
            if should_fail and not self.failed:
                self.failed = True
                raise OSError(f"{failure_point} transport failed")
            if event_type == "tool_result":
                self.saw_tool_result = True
            super().send(event)

    def write_once() -> dict:
        """Represent a tool with side effects that must not be retried."""
        return {"written": True}

    llm = MockLLM(responses=[
        response(tool_calls=[ToolCall(name="write_once", arguments={}, id="call-1")]),
        response("must not be reached"),
    ])
    agent = Agent(
        name=f"transport-{failure_point}",
        tools=[write_once],
        llm=llm,
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )
    agent.io = FailingIO()

    with pytest.raises(OSError, match=f"{failure_point} transport failed"):
        agent.input("write")

    tool_results = [
        event for event in agent.current_session["trace"]
        if event.get("type") == "tool_result"
    ]
    assert len(tool_results) == 1
    assert tool_results[0]["status"] == "success"
    assert tool_results[0]["result"] == "{'written': True}"
    assert "raw_output" not in tool_results[0]
    assert "error" not in tool_results[0]
    assert llm.call_count == 1


def test_logger_failure_does_not_reclassify_or_duplicate_success(tmp_path):
    def write_once() -> dict:
        """Represent a tool with side effects that must not be retried."""
        return {"written": True}

    llm = MockLLM(responses=[
        response(tool_calls=[ToolCall(name="write_once", arguments={}, id="call-1")]),
        response("must not be reached"),
    ])
    agent = Agent(
        name="logger-failure",
        tools=[write_once],
        llm=llm,
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )

    with patch.object(
        agent.logger,
        "log_tool_result",
        side_effect=OSError("logger failed"),
    ):
        with pytest.raises(OSError, match="logger failed"):
            agent.input("write")

    tool_results = [
        event for event in agent.current_session["trace"]
        if event.get("type") == "tool_result"
    ]
    assert len(tool_results) == 1
    assert tool_results[0]["status"] == "success"
    assert tool_results[0]["result"] == "{'written': True}"
    assert "error" not in tool_results[0]
    assert llm.call_count == 1


def test_wire_extras_cannot_override_canonical_event_fields(tmp_path):
    agent = Agent(
        name="canonical-wire-fields",
        llm=MockLLM(),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )
    agent.current_session = {"trace": []}
    io = CaptureIO()
    agent.io = io
    canonical = {
        "type": "tool_result",
        "id": "canonical-id",
        "ts": 123.0,
        "tool_id": "call-1",
        "status": "success",
        "result": "ok",
    }

    agent._record_trace(
        canonical,
        wire_extras={
            "type": "forged",
            "id": "forged-id",
            "ts": 999.0,
            "tool_id": "forged-call",
            "status": "error",
            "raw_output": {"ok": True},
        },
    )

    wire_result = io.events[0]
    assert wire_result == {
        **canonical,
        "status": "completed",
        "raw_output": {"ok": True},
    }
    assert agent.current_session["trace"] == [canonical]
    assert canonical["status"] == "success"
