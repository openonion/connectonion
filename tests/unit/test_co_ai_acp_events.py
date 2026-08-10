"""Exact ACP event mapping and per-turn streaming barriers."""

from __future__ import annotations

import asyncio
import threading
import time
from copy import deepcopy
from typing import Any, Callable
from uuid import UUID, uuid4

import pytest
from acp import RequestError, text_block
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    ToolCallProgress,
    ToolCallStart,
)

from connectonion import Agent
from connectonion.cli.co_ai import acp_server
from connectonion.cli.co_ai.acp_events import map_agent_event
from connectonion.cli.co_ai.acp_server import (
    ACP_EVENT_BUFFER_SIZE,
    ConnectOnionACPAgent,
)
from connectonion.core.llm import LLMResponse, ToolCall
from connectonion.core.usage import TokenUsage
from tests.utils.mock_helpers import MockLLM


def dumped(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def test_tool_start_maps_to_the_exact_acp_model():
    mapped = map_agent_event({
        "type": "tool_call",
        "tool_id": "call-1",
        "name": "search_docs",
        "args": {"query": "ACP"},
    })

    assert mapped.terminal is None
    assert len(mapped.updates) == 1
    assert isinstance(mapped.updates[0], ToolCallStart)
    assert dumped(mapped.updates[0]) == {
        "toolCallId": "call-1",
        "title": "search_docs",
        "status": "in_progress",
        "rawInput": {"query": "ACP"},
        "sessionUpdate": "tool_call",
    }


def test_successful_tool_result_keeps_text_and_structured_output():
    mapped = map_agent_event({
        "type": "tool_result",
        "tool_id": "call-1",
        "name": "search_docs",
        "status": "success",
        "result": "{'matches': [1, 2]}",
        "raw_output": {"matches": [1, 2]},
    })

    assert len(mapped.updates) == 1
    update = mapped.updates[0]
    assert isinstance(update, ToolCallProgress)
    assert dumped(update) == {
        "toolCallId": "call-1",
        "status": "completed",
        "content": [{
            "type": "content",
            "content": {"type": "text", "text": "{'matches': [1, 2]}"},
        }],
        "rawOutput": {"matches": [1, 2]},
        "sessionUpdate": "tool_call_update",
    }


@pytest.mark.parametrize("status", ["error", "not_found", "interrupted"])
def test_unsuccessful_tool_statuses_map_to_failed(status):
    mapped = map_agent_event({
        "type": "tool_result",
        "tool_id": "call-1",
        "status": status,
        "result": "failed",
    })

    assert mapped.updates[0].status == "failed"


def test_none_raw_output_uses_the_official_sdk_shape():
    mapped = map_agent_event({
        "type": "tool_result",
        "tool_id": "call-1",
        "status": "success",
        "result": "None",
        "raw_output": None,
    })

    payload = dumped(mapped.updates[0])
    assert payload["content"][0]["content"]["text"] == "None"
    assert "rawOutput" not in payload


def test_thought_and_assistant_messages_keep_their_message_ids():
    thought = map_agent_event({
        "type": "thinking",
        "id": "47c7e8e1-6755-48ea-a8d3-8f6cf618b60a",
        "content": "checking",
    }).updates[0]
    assistant = map_agent_event({
        "type": "assistant",
        "message_id": "2359f04e-8e17-49d9-a634-ec14d2ecf754",
        "content": "done",
    }).updates[0]

    assert isinstance(thought, AgentThoughtChunk)
    assert isinstance(assistant, AgentMessageChunk)
    assert thought.message_id == "47c7e8e1-6755-48ea-a8d3-8f6cf618b60a"
    assert assistant.message_id == "2359f04e-8e17-49d9-a634-ec14d2ecf754"
    assert thought.content.text == "checking"
    assert assistant.content.text == "done"


@pytest.mark.parametrize(
    ("reason", "stop_reason"),
    [
        ("natural", "end_turn"),
        ("max_iterations", "max_turn_requests"),
        ("interrupted", "cancelled"),
        ("stopped", "refusal"),
    ],
)
def test_terminal_reasons_map_without_parsing_display_text(reason, stop_reason):
    mapped = map_agent_event({
        "type": "turn_result",
        "turn": 1,
        "reason": reason,
        "usage": None,
    })

    assert mapped.updates == ()
    assert mapped.terminal.stop_reason == stop_reason
    assert mapped.terminal.usage is None


def test_terminal_usage_maps_measured_fields_without_inventing_thought_tokens():
    terminal = map_agent_event({
        "type": "turn_result",
        "turn": 1,
        "reason": "natural",
        "usage": {
            "input_tokens": 11,
            "output_tokens": 7,
            "cached_tokens": 3,
            "cache_write_tokens": 2,
            "total_tokens": 25,
            "cost": 0.5,
        },
    }).terminal

    assert dumped(terminal.usage) == {
        "totalTokens": 25,
        "inputTokens": 11,
        "outputTokens": 7,
        "cachedReadTokens": 3,
        "cachedWriteTokens": 2,
    }


@pytest.mark.parametrize(
    "event_type",
    ["user_input", "session_sync", "llm_call", "llm_result", "intent"],
)
def test_client_owned_or_non_protocol_events_are_not_echoed(event_type):
    mapped = map_agent_event({"type": event_type, "content": "private prompt"})

    assert mapped.updates == ()
    assert mapped.terminal is None


class _Client:
    def __init__(self) -> None:
        self.updates: list[tuple[str, Any]] = []

    async def session_update(
        self,
        session_id: str,
        update: Any,
        **_kwargs: Any,
    ) -> None:
        self.updates.append((session_id, update))


class _ScriptedAgent:
    def __init__(self, script: Callable[["_ScriptedAgent", str], str]) -> None:
        self.io: Any = None
        self.current_session: dict[str, Any] = {"trace": [], "turn": 0}
        self._script = script

    def emit(self, event: dict[str, Any]) -> None:
        if event.get("type") == "turn_result":
            self.current_session["trace"].append(event)
        self.io.send(event)

    def input(self, prompt: str) -> str:
        self.current_session["turn"] += 1
        return self._script(self, prompt)


def _server(agent: _ScriptedAgent) -> ConnectOnionACPAgent:
    return ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: agent,
    )


@pytest.mark.asyncio
async def test_multi_tool_stream_is_ordered_and_prompt_response_is_terminal(tmp_path):
    def script(agent: _ScriptedAgent, prompt: str) -> str:
        agent.emit({"type": "user_input", "content": prompt})
        agent.emit({
            "type": "tool_call",
            "tool_id": "a",
            "name": "lookup",
            "args": {"q": "one"},
        })
        agent.emit({
            "type": "tool_call",
            "tool_id": "b",
            "name": "write",
            "args": {"path": "x"},
        })
        agent.emit({
            "type": "tool_result",
            "tool_id": "a",
            "status": "success",
            "result": "{'value': 1}",
            "raw_output": {"value": 1},
        })
        agent.emit({
            "type": "tool_result",
            "tool_id": "b",
            "status": "error",
            "result": "Error: denied",
        })
        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "natural",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 4,
                "cached_tokens": 2,
                "cache_write_tokens": 0,
                "total_tokens": 18,
                "cost": 0.1,
            },
        })
        return "finished"

    client = _Client()
    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(client)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])

    response = await acp_agent.prompt(session.session_id, [text_block("do it")])

    updates = [update for _, update in client.updates]
    assert [type(update) for update in updates] == [
        ToolCallStart,
        ToolCallStart,
        ToolCallProgress,
        ToolCallProgress,
        AgentMessageChunk,
    ]
    assert [update.tool_call_id for update in updates[:4]] == ["a", "b", "a", "b"]
    assert updates[2].raw_output == {"value": 1}
    assert updates[3].status == "failed"
    assert updates[-1].content.text == "finished"
    UUID(updates[-1].message_id)
    assert all(
        getattr(update, "content", None) != "do it"
        for update in updates
    )
    assert response.stop_reason == "end_turn"
    assert response.usage.total_tokens == 18


@pytest.mark.asyncio
async def test_real_agent_streams_structured_tool_events_through_acp(tmp_path):
    def lookup(query: str) -> dict[str, Any]:
        """Return deterministic structured results."""
        return {"query": query, "hits": [1, 2]}

    agent = Agent(
        name="acp-integration",
        tools=[lookup],
        llm=MockLLM(responses=[
            LLMResponse(
                content="",
                tool_calls=[ToolCall(
                    name="lookup",
                    arguments={"query": "ACP"},
                    id="call-real",
                )],
                raw_response={},
                usage=TokenUsage(
                    input_tokens=3,
                    output_tokens=2,
                    total_tokens=5,
                ),
            ),
            LLMResponse(
                content="Found two matches.",
                tool_calls=[],
                raw_response={},
                usage=TokenUsage(
                    input_tokens=4,
                    output_tokens=3,
                    total_tokens=7,
                ),
            ),
        ]),
        max_iterations=2,
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )
    client = _Client()
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: agent,
    )
    acp_agent.on_connect(client)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])

    response = await acp_agent.prompt(
        session.session_id,
        [text_block("Find ACP")],
    )

    updates = [update for _, update in client.updates]
    assert [type(update) for update in updates] == [
        ToolCallStart,
        ToolCallProgress,
        AgentMessageChunk,
    ]
    assert updates[0].tool_call_id == "call-real"
    assert updates[0].raw_input == {"query": "ACP"}
    assert updates[1].tool_call_id == "call-real"
    assert updates[1].raw_output == {"query": "ACP", "hits": [1, 2]}
    assert updates[2].content.text == "Found two matches."
    assert response.stop_reason == "end_turn"
    assert response.usage.total_tokens == 12


@pytest.mark.asyncio
async def test_prompt_waits_until_the_last_session_update_is_drained(tmp_path):
    class BlockingClient(_Client):
        def __init__(self) -> None:
            super().__init__()
            self.assistant_started = asyncio.Event()
            self.release = asyncio.Event()

        async def session_update(self, session_id, update, **kwargs):
            await super().session_update(session_id, update, **kwargs)
            if isinstance(update, AgentMessageChunk):
                self.assistant_started.set()
                await self.release.wait()

    def script(agent: _ScriptedAgent, _prompt: str) -> str:
        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "natural",
            "usage": None,
        })
        return "done"

    client = BlockingClient()
    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(client)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    prompt_task = asyncio.create_task(
        acp_agent.prompt(session.session_id, [text_block("wait")])
    )

    await asyncio.wait_for(client.assistant_started.wait(), timeout=1)
    assert not prompt_task.done()
    client.release.set()

    response = await asyncio.wait_for(prompt_task, timeout=1)
    assert response.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_parallel_event_detachment_preserves_entry_order(monkeypatch, tmp_path):
    first_copy_started = threading.Event()
    second_copy_started = threading.Event()
    release_first_copy = threading.Event()

    def controlled_copy(event: dict[str, Any]) -> dict[str, Any]:
        if event.get("content") == "first":
            first_copy_started.set()
            assert release_first_copy.wait(timeout=1)
        elif event.get("content") == "second":
            second_copy_started.set()
        return deepcopy(event)

    monkeypatch.setattr(acp_server.copy, "deepcopy", controlled_copy)

    def script(agent: _ScriptedAgent, _prompt: str) -> str:
        first = threading.Thread(target=lambda: agent.emit({
            "type": "thinking",
            "id": str(uuid4()),
            "content": "first",
        }))
        second = threading.Thread(target=lambda: agent.emit({
            "type": "thinking",
            "id": str(uuid4()),
            "content": "second",
        }))
        first.start()
        assert first_copy_started.wait(timeout=1)
        second.start()
        second_copy_started.wait(timeout=0.05)
        release_first_copy.set()
        first.join(timeout=1)
        second.join(timeout=1)
        assert not first.is_alive()
        assert not second.is_alive()
        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "natural",
            "usage": None,
        })
        return "done"

    client = _Client()
    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(client)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])

    await acp_agent.prompt(session.session_id, [text_block("work")])

    assert [
        update.content.text
        for _, update in client.updates
        if isinstance(update, AgentThoughtChunk)
    ] == ["first", "second"]


@pytest.mark.asyncio
async def test_terminal_barrier_waits_for_an_event_already_being_detached(
    monkeypatch,
    tmp_path,
):
    copy_started = threading.Event()
    release_copy = threading.Event()
    send_finished = threading.Event()

    def controlled_copy(event: dict[str, Any]) -> dict[str, Any]:
        if event.get("content") == "before terminal":
            copy_started.set()
            assert release_copy.wait(timeout=1)
        return deepcopy(event)

    monkeypatch.setattr(acp_server.copy, "deepcopy", controlled_copy)

    def script(agent: _ScriptedAgent, _prompt: str) -> str:
        def send_thought() -> None:
            agent.emit({
                "type": "thinking",
                "id": str(uuid4()),
                "content": "before terminal",
            })
            send_finished.set()

        threading.Thread(target=send_thought, daemon=True).start()
        assert copy_started.wait(timeout=1)
        threading.Timer(0.05, release_copy.set).start()
        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "natural",
            "usage": None,
        })
        return "done"

    client = _Client()
    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(client)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])

    response = await acp_agent.prompt(session.session_id, [text_block("work")])
    assert await asyncio.to_thread(send_finished.wait, 1)

    assert response.stop_reason == "end_turn"
    assert [
        update.content.text
        for _, update in client.updates
        if isinstance(update, AgentThoughtChunk)
    ] == ["before terminal"]


@pytest.mark.asyncio
async def test_slow_client_applies_bounded_backpressure_to_agent_events(tmp_path):
    event_limit = ACP_EVENT_BUFFER_SIZE
    completed_sends: list[int] = []
    capacity_reached = threading.Event()

    class BlockingClient(_Client):
        def __init__(self) -> None:
            super().__init__()
            self.first_update_started = asyncio.Event()
            self.release = asyncio.Event()

        async def session_update(self, session_id, update, **kwargs):
            if not self.first_update_started.is_set():
                self.first_update_started.set()
                await self.release.wait()
            await super().session_update(session_id, update, **kwargs)

    def script(agent: _ScriptedAgent, _prompt: str) -> str:
        for index in range(event_limit + 3):
            agent.emit({
                "type": "thinking",
                "id": str(uuid4()),
                "content": f"event {index}",
            })
            completed_sends.append(index)
            if len(completed_sends) == event_limit + 1:
                capacity_reached.set()
        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "natural",
            "usage": None,
        })
        return "done"

    client = BlockingClient()
    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(client)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    prompt_task = asyncio.create_task(
        acp_agent.prompt(session.session_id, [text_block("work")])
    )

    await asyncio.wait_for(client.first_update_started.wait(), timeout=1)
    assert await asyncio.to_thread(capacity_reached.wait, 1)
    await asyncio.sleep(0.05)
    assert len(completed_sends) == event_limit + 1
    assert not prompt_task.done()

    client.release.set()
    response = await asyncio.wait_for(prompt_task, timeout=2)
    assert response.stop_reason == "end_turn"
    assert len(completed_sends) == event_limit + 3


@pytest.mark.asyncio
async def test_cancelling_slow_client_wakes_backpressured_producer(tmp_path):
    capacity_reached = threading.Event()

    class BlockingOnceClient(_Client):
        def __init__(self) -> None:
            super().__init__()
            self.first_update_started = asyncio.Event()
            self.release = asyncio.Event()
            self.blocked = False

        async def session_update(self, session_id, update, **kwargs):
            if not self.blocked:
                self.blocked = True
                self.first_update_started.set()
                await self.release.wait()
            await super().session_update(session_id, update, **kwargs)

    def script(agent: _ScriptedAgent, prompt: str) -> str:
        if prompt == "first":
            for index in range(ACP_EVENT_BUFFER_SIZE + 2):
                agent.emit({
                    "type": "thinking",
                    "id": str(uuid4()),
                    "content": f"event {index}",
                })
                if index == ACP_EVENT_BUFFER_SIZE:
                    capacity_reached.set()
        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "natural",
            "usage": None,
        })
        return f"{prompt} answer"

    client = BlockingOnceClient()
    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(client)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    first = asyncio.create_task(
        acp_agent.prompt(session.session_id, [text_block("first")])
    )
    await asyncio.wait_for(client.first_update_started.wait(), timeout=1)
    assert await asyncio.to_thread(capacity_reached.wait, 1)

    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(first, timeout=1)

    second = await asyncio.wait_for(
        acp_agent.prompt(session.session_id, [text_block("second")]),
        timeout=1,
    )

    assert second.stop_reason == "end_turn"
    assert [
        update.content.text
        for _, update in client.updates
        if isinstance(update, AgentMessageChunk)
    ] == ["second answer"]


@pytest.mark.asyncio
async def test_protocol_cancel_wakes_backpressured_producer(tmp_path):
    capacity_reached = threading.Event()
    worker_finished = threading.Event()

    class BlockingClient(_Client):
        def __init__(self) -> None:
            super().__init__()
            self.first_update_started = asyncio.Event()
            self.release = asyncio.Event()

        async def session_update(self, session_id, update, **kwargs):
            if not self.first_update_started.is_set():
                self.first_update_started.set()
                await self.release.wait()
            await super().session_update(session_id, update, **kwargs)

    def script(agent: _ScriptedAgent, _prompt: str) -> str:
        for index in range(ACP_EVENT_BUFFER_SIZE + 2):
            agent.emit({
                "type": "thinking",
                "id": str(uuid4()),
                "content": f"event {index}",
            })
            if index == ACP_EVENT_BUFFER_SIZE:
                capacity_reached.set()
        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "interrupted",
            "usage": None,
        })
        worker_finished.set()
        return "cancelled"

    client = BlockingClient()
    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(client)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    prompt_task = asyncio.create_task(
        acp_agent.prompt(session.session_id, [text_block("work")])
    )

    await asyncio.wait_for(client.first_update_started.wait(), timeout=1)
    assert await asyncio.to_thread(capacity_reached.wait, 1)
    try:
        await acp_agent.cancel(session.session_id)
        assert await asyncio.to_thread(worker_finished.wait, 0.1)
    finally:
        client.release.set()

    response = await asyncio.wait_for(prompt_task, timeout=2)
    assert response.stop_reason == "cancelled"


@pytest.mark.asyncio
async def test_cancel_after_natural_terminal_keeps_final_assistant(tmp_path):
    terminal_sent = threading.Event()
    allow_return = threading.Event()

    def script(agent: _ScriptedAgent, _prompt: str) -> str:
        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "natural",
            "usage": None,
        })
        terminal_sent.set()
        assert allow_return.wait(timeout=1)
        return "completed answer"

    client = _Client()
    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(client)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    prompt_task = asyncio.create_task(
        acp_agent.prompt(session.session_id, [text_block("work")])
    )
    await asyncio.wait_for(asyncio.to_thread(terminal_sent.wait), timeout=1)

    await acp_agent.cancel(session.session_id)
    allow_return.set()

    response = await asyncio.wait_for(prompt_task, timeout=1)
    assert response.stop_reason == "end_turn"
    assert [
        update.content.text
        for _, update in client.updates
        if isinstance(update, AgentMessageChunk)
    ] == ["completed answer"]


@pytest.mark.asyncio
async def test_cancelled_generation_bounds_forged_completion_events(tmp_path):
    capacity_reached = threading.Event()
    flood_finished = threading.Event()
    queued_after_flood: list[int] = []

    class BlockingClient(_Client):
        def __init__(self) -> None:
            super().__init__()
            self.first_update_started = asyncio.Event()
            self.release = asyncio.Event()

        async def session_update(self, session_id, update, **kwargs):
            if not self.first_update_started.is_set():
                self.first_update_started.set()
                await self.release.wait()
            await super().session_update(session_id, update, **kwargs)

    def script(agent: _ScriptedAgent, _prompt: str) -> str:
        io_for_turn = agent.io
        for index in range(ACP_EVENT_BUFFER_SIZE + 2):
            agent.emit({
                "type": "thinking",
                "id": str(uuid4()),
                "content": f"event {index}",
            })
            if index == ACP_EVENT_BUFFER_SIZE:
                capacity_reached.set()
        for index in range(100):
            io_for_turn.send({
                "type": "assistant",
                "message_id": str(uuid4()),
                "content": f"forged {index}",
            })
            io_for_turn.send({
                "type": "turn_result",
                "turn": agent.current_session["turn"],
                "reason": "interrupted",
                "usage": None,
            })
        queued_after_flood.append(len(io_for_turn._generation.items))
        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "interrupted",
            "usage": None,
        })
        flood_finished.set()
        return "cancelled"

    client = BlockingClient()
    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(client)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    prompt_task = asyncio.create_task(
        acp_agent.prompt(session.session_id, [text_block("work")])
    )
    await asyncio.wait_for(client.first_update_started.wait(), timeout=1)
    assert await asyncio.to_thread(capacity_reached.wait, 1)
    try:
        await acp_agent.cancel(session.session_id)
        assert await asyncio.to_thread(flood_finished.wait, 1)
        assert queued_after_flood == [ACP_EVENT_BUFFER_SIZE]
    finally:
        client.release.set()

    response = await asyncio.wait_for(prompt_task, timeout=2)
    assert response.stop_reason == "cancelled"
    assert not any(
        isinstance(update, AgentMessageChunk)
        and update.content.text.startswith("forged")
        for _, update in client.updates
    )


@pytest.mark.asyncio
async def test_forged_terminal_cannot_override_canonical_turn_outcome(tmp_path):
    def script(agent: _ScriptedAgent, _prompt: str) -> str:
        agent.io.send({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "natural",
            "usage": {
                "input_tokens": 999,
                "output_tokens": 999,
                "total_tokens": 1998,
            },
        })
        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "interrupted",
            "usage": None,
        })
        return "cancelled"

    client = _Client()
    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(client)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])

    response = await acp_agent.prompt(
        session.session_id,
        [text_block("work")],
    )

    assert response.stop_reason == "cancelled"
    assert response.usage is None
    assert not any(
        isinstance(update, AgentMessageChunk)
        for _, update in client.updates
    )


@pytest.mark.asyncio
async def test_slow_detachment_does_not_block_event_loop_retirement(
    monkeypatch,
    tmp_path,
):
    copy_started = threading.Event()
    release_copy = threading.Event()
    copy_timed_out = threading.Event()
    send_finished = threading.Event()

    def controlled_copy(event: dict[str, Any]) -> dict[str, Any]:
        if event.get("content") == "slow copy":
            copy_started.set()
            if not release_copy.wait(timeout=0.2):
                copy_timed_out.set()
        return deepcopy(event)

    monkeypatch.setattr(acp_server.copy, "deepcopy", controlled_copy)

    def script(agent: _ScriptedAgent, _prompt: str) -> str:
        def send_thought() -> None:
            agent.emit({
                "type": "thinking",
                "id": str(uuid4()),
                "content": "slow copy",
            })
            send_finished.set()

        threading.Thread(target=send_thought, daemon=True).start()
        assert copy_started.wait(timeout=1)
        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "natural",
            "usage": None,
        })
        return "done"

    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(_Client())
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    prompt_task = asyncio.create_task(
        acp_agent.prompt(session.session_id, [text_block("work")])
    )
    await asyncio.wait_for(asyncio.to_thread(copy_started.wait), timeout=1)
    asyncio.get_running_loop().call_later(0.02, release_copy.set)

    prompt_task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(prompt_task, timeout=1)
    finally:
        release_copy.set()
    assert await asyncio.to_thread(send_finished.wait, 1)
    assert not copy_timed_out.is_set()


@pytest.mark.asyncio
async def test_different_sessions_keep_their_event_streams_isolated(tmp_path):
    def make_agent(answer: str) -> _ScriptedAgent:
        def script(agent: _ScriptedAgent, _prompt: str) -> str:
            agent.emit({
                "type": "tool_call",
                "tool_id": "shared-id",
                "name": answer,
                "args": {},
            })
            agent.emit({
                "type": "tool_result",
                "tool_id": "shared-id",
                "status": "success",
                "result": answer,
            })
            agent.emit({
                "type": "turn_result",
                "turn": agent.current_session["turn"],
                "reason": "natural",
                "usage": None,
            })
            return answer

        return _ScriptedAgent(script)

    agents = iter([make_agent("alpha"), make_agent("beta")])
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: next(agents),
    )
    client = _Client()
    acp_agent.on_connect(client)
    first = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    second = await acp_agent.new_session(str(tmp_path), mcp_servers=[])

    first_response, second_response = await asyncio.gather(
        acp_agent.prompt(first.session_id, [text_block("one")]),
        acp_agent.prompt(second.session_id, [text_block("two")]),
    )

    assert first_response.stop_reason == "end_turn"
    assert second_response.stop_reason == "end_turn"
    by_session = {
        session_id: [update for current_id, update in client.updates
                     if current_id == session_id]
        for session_id in (first.session_id, second.session_id)
    }
    assert [update.title for update in by_session[first.session_id]
            if isinstance(update, ToolCallStart)] == ["alpha"]
    assert [update.title for update in by_session[second.session_id]
            if isinstance(update, ToolCallStart)] == ["beta"]
    assert [update.content.text for update in by_session[first.session_id]
            if isinstance(update, AgentMessageChunk)] == ["alpha"]
    assert [update.content.text for update in by_session[second.session_id]
            if isinstance(update, AgentMessageChunk)] == ["beta"]


@pytest.mark.asyncio
async def test_same_session_rejects_an_overlapping_prompt(tmp_path):
    started = threading.Event()

    def script(agent: _ScriptedAgent, _prompt: str) -> str:
        started.set()
        io_for_turn = agent.io
        while not io_for_turn.receive_all("INTERRUPT"):
            time.sleep(0.01)
        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "interrupted",
            "usage": None,
        })
        return "cancelled"

    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(_Client())
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    active = asyncio.create_task(
        acp_agent.prompt(session.session_id, [text_block("first")])
    )
    await asyncio.wait_for(asyncio.to_thread(started.wait), timeout=1)

    with pytest.raises(RequestError, match="Session is busy"):
        await acp_agent.prompt(session.session_id, [text_block("second")])

    await acp_agent.cancel(session.session_id)
    assert (await asyncio.wait_for(active, timeout=1)).stop_reason == "cancelled"


@pytest.mark.asyncio
async def test_cancelling_prompt_task_retires_worker_and_allows_next_turn(tmp_path):
    first_started = threading.Event()

    def script(agent: _ScriptedAgent, prompt: str) -> str:
        if prompt == "first":
            io_for_turn = agent.io
            first_started.set()
            while not io_for_turn.receive_all("INTERRUPT"):
                time.sleep(0.01)
            agent.emit({
                "type": "turn_result",
                "turn": agent.current_session["turn"],
                "reason": "interrupted",
                "usage": None,
            })
            return "cancelled"

        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "natural",
            "usage": None,
        })
        return "second answer"

    client = _Client()
    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(client)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    first = asyncio.create_task(
        acp_agent.prompt(session.session_id, [text_block("first")])
    )
    await asyncio.wait_for(asyncio.to_thread(first_started.wait), timeout=1)

    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    try:
        second = await asyncio.wait_for(
            acp_agent.prompt(session.session_id, [text_block("second")]),
            timeout=1,
        )
    finally:
        await acp_agent.cancel(session.session_id)

    assert second.stop_reason == "end_turn"
    assert [
        update.content.text
        for _, update in client.updates
        if isinstance(update, AgentMessageChunk)
    ] == ["second answer"]


@pytest.mark.asyncio
async def test_max_iterations_returns_the_protocol_stop_reason(tmp_path):
    def script(agent: _ScriptedAgent, _prompt: str) -> str:
        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "max_iterations",
            "usage": None,
        })
        return "Task incomplete: iteration limit reached."

    client = _Client()
    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(client)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])

    response = await acp_agent.prompt(session.session_id, [text_block("work")])

    assert response.stop_reason == "max_turn_requests"
    assert response.usage is None
    assert [update.content.text for _, update in client.updates
            if isinstance(update, AgentMessageChunk)] == [
        "Task incomplete: iteration limit reached."
    ]


@pytest.mark.asyncio
async def test_cancelled_generation_drops_late_events_from_the_next_turn(tmp_path):
    first_started = threading.Event()
    release_late = threading.Event()
    late_sent = threading.Event()

    def script(agent: _ScriptedAgent, prompt: str) -> str:
        if prompt == "first":
            first_started.set()
            old_io = agent.io
            while not old_io.receive_all("INTERRUPT"):
                time.sleep(0.01)
            agent.emit({
                "type": "turn_result",
                "turn": agent.current_session["turn"],
                "reason": "interrupted",
                "usage": None,
            })

            def send_late() -> None:
                release_late.wait()
                old_io.send({
                    "type": "thinking",
                    "id": "84c3953e-0c09-4e5f-86a2-d5f22722daed",
                    "content": "late from first",
                })
                late_sent.set()

            threading.Thread(target=send_late, daemon=True).start()
            return "cancelled display text"

        release_late.set()
        assert late_sent.wait(timeout=1)
        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "natural",
            "usage": None,
        })
        return "second answer"

    client = _Client()
    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(client)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    first = asyncio.create_task(
        acp_agent.prompt(session.session_id, [text_block("first")])
    )
    await asyncio.wait_for(asyncio.to_thread(first_started.wait), timeout=1)
    await acp_agent.cancel(session.session_id)
    assert (await asyncio.wait_for(first, timeout=1)).stop_reason == "cancelled"

    second = await acp_agent.prompt(session.session_id, [text_block("second")])

    assert second.stop_reason == "end_turn"
    assert not any(
        isinstance(update, AgentThoughtChunk)
        and update.content.text == "late from first"
        for _, update in client.updates
    )
    assert [
        update.content.text
        for _, update in client.updates
        if isinstance(update, AgentMessageChunk)
    ] == ["second answer"]


@pytest.mark.asyncio
async def test_session_update_failure_interrupts_and_retires_the_generation(tmp_path):
    class FailingClient(_Client):
        def __init__(self) -> None:
            super().__init__()
            self.fail = True

        async def session_update(self, session_id, update, **kwargs):
            if self.fail:
                self.fail = False
                raise RuntimeError("private client transport detail")
            await super().session_update(session_id, update, **kwargs)

    def script(agent: _ScriptedAgent, prompt: str) -> str:
        if prompt == "first":
            io_for_turn = agent.io
            agent.emit({
                "type": "tool_call",
                "tool_id": "a",
                "name": "wait",
                "args": {},
            })
            while not io_for_turn.receive_all("INTERRUPT"):
                time.sleep(0.01)
            agent.emit({
                "type": "turn_result",
                "turn": agent.current_session["turn"],
                "reason": "interrupted",
                "usage": None,
            })
            return "cancelled"

        agent.emit({
            "type": "turn_result",
            "turn": agent.current_session["turn"],
            "reason": "natural",
            "usage": None,
        })
        return "recovered"

    client = FailingClient()
    acp_agent = _server(_ScriptedAgent(script))
    acp_agent.on_connect(client)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])

    with pytest.raises(RequestError) as exc_info:
        await asyncio.wait_for(
            acp_agent.prompt(session.session_id, [text_block("first")]),
            timeout=1,
        )
    assert "private client transport detail" not in str(exc_info.value)

    response = await asyncio.wait_for(
        acp_agent.prompt(session.session_id, [text_block("second")]),
        timeout=1,
    )
    assert response.stop_reason == "end_turn"
    assert [
        update.content.text
        for _, update in client.updates
        if isinstance(update, AgentMessageChunk)
    ] == ["recovered"]
