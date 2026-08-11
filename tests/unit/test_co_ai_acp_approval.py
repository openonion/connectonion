"""ACP permission requests reuse ConnectOnion's fail-closed approval policy."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

import pytest
from acp import RequestError, text_block
from acp.schema import PermissionOption, RequestPermissionResponse, ToolCallUpdate

from connectonion import Agent
from connectonion.cli.co_ai import acp_server
from connectonion.cli.co_ai.acp_server import ConnectOnionACPAgent, _ACPEventBridge
from connectonion.cli.co_ai.one_shot_sessions import load_snapshot, session_lock
from connectonion.core.llm import LLMResponse, ToolCall
from connectonion.useful_plugins import tool_approval
from tests.utils.mock_helpers import MockLLM


def _selected(option_id: str) -> dict[str, Any]:
    return {"outcome": {"outcome": "selected", "optionId": option_id}}


def _cancelled() -> dict[str, Any]:
    return {"outcome": {"outcome": "cancelled"}}


class _ApprovalClient:
    def __init__(self, *responses: Any) -> None:
        self.responses = deque(responses)
        self.requests: list[tuple[str, ToolCallUpdate, list[PermissionOption]]] = []
        self.updates: list[tuple[str, Any]] = []

    async def request_permission(
        self,
        session_id: str,
        tool_call: ToolCallUpdate,
        options: list[PermissionOption],
        **_kwargs: Any,
    ) -> RequestPermissionResponse:
        self.requests.append((session_id, tool_call, options))
        response = self.responses.popleft()
        if isinstance(response, BaseException):
            raise response
        return RequestPermissionResponse.model_validate(response)

    async def session_update(
        self,
        session_id: str,
        update: Any,
        **_kwargs: Any,
    ) -> None:
        self.updates.append((session_id, update))


class _BlockingApprovalClient(_ApprovalClient):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def request_permission(self, **kwargs: Any) -> RequestPermissionResponse:
        self.requests.append((
            kwargs["session_id"],
            kwargs["tool_call"],
            kwargs["options"],
        ))
        self.started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


class _FailAfterSessionGrantClient(_ApprovalClient):
    def __init__(self) -> None:
        super().__init__(_selected("allow_session"))
        self.granted = False

    async def request_permission(self, **kwargs: Any) -> RequestPermissionResponse:
        response = await super().request_permission(**kwargs)
        self.granted = True
        return response

    async def session_update(self, **kwargs: Any) -> None:
        if self.granted:
            raise RuntimeError("private update marker")
        await super().session_update(**kwargs)


def _agent(
    project,
    executed: list[str],
    tool_call_ids: list[str],
) -> Agent:
    def write(content: str) -> str:
        """Record one deterministic write-like side effect."""

        executed.append(content)
        return f"wrote {content}"

    responses: list[LLMResponse] = []
    for index, tool_call_id in enumerate(tool_call_ids):
        responses.extend([
            LLMResponse(
                content="",
                tool_calls=[ToolCall(
                    name="write",
                    arguments={"content": f"value-{index}"},
                    id=tool_call_id,
                )],
                raw_response={},
            ),
            LLMResponse(
                content=f"finished-{index}",
                tool_calls=[],
                raw_response={},
            ),
        ])
    return Agent(
        name="acp-approval",
        tools=[write],
        plugins=[tool_approval],
        llm=MockLLM(responses=responses),
        max_iterations=max(2, len(tool_call_ids) * 2),
        log=False,
        quiet=True,
        co_dir=project / ".co",
    )


def _server(state_dir, factory) -> ConnectOnionACPAgent:
    return ConnectOnionACPAgent(
        model="test",
        max_iterations=4,
        yolo=False,
        yolo_turns=2,
        agent_factory=factory,
        session_co_dir=state_dir,
    )


def _project(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return project


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


@pytest.mark.asyncio
async def test_allow_once_uses_exact_acp_schema_without_persisting_grant(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    executed: list[str] = []
    client = _ApprovalClient(_selected("allow_once"))
    server = _server(
        tmp_path / "state",
        lambda **_: _agent(project, executed, ["same-call-id"]),
    )
    server.on_connect(client)
    session = await server.new_session(str(project), mcp_servers=[])

    response = await server.prompt(session.session_id, [text_block("write it")])

    assert response.stop_reason == "end_turn"
    assert executed == ["value-0"]
    assert len(client.requests) == 1
    request_session, tool_call, options = client.requests[0]
    assert request_session == session.session_id
    assert _dump(tool_call) == {
        "toolCallId": "same-call-id",
        "status": "pending",
        "title": "write",
        "rawInput": {"content": "value-0"},
    }
    assert [_dump(option) for option in options] == [
        {
            "optionId": "allow_once",
            "name": "Allow this call",
            "kind": "allow_once",
        },
        {
            "optionId": "allow_session",
            "name": "Allow for this session",
            "kind": "allow_always",
        },
        {
            "optionId": "reject_once",
            "name": "Reject and stop this turn",
            "kind": "reject_once",
        },
    ]
    stored, _ = load_snapshot(tmp_path / "state", session.session_id)
    assert "write" not in stored.get("permissions", {})


@pytest.mark.asyncio
async def test_allow_session_commits_once_and_survives_resume(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    first_executed: list[str] = []
    first_client = _ApprovalClient(_selected("allow_session"))
    first = _server(
        state_dir,
        lambda **_: _agent(project, first_executed, ["call-1"]),
    )
    first.on_connect(first_client)
    session = await first.new_session(str(project), mcp_servers=[])

    await first.prompt(session.session_id, [text_block("first")])

    assert first_executed == ["value-0"]
    assert len(first_client.requests) == 1
    stored, _ = load_snapshot(state_dir, session.session_id)
    assert stored["permissions"]["write"]["source"] == "user"
    await first.close_session(session.session_id)

    resumed_executed: list[str] = []
    resumed_client = _ApprovalClient(RuntimeError("must not ask again"))
    resumed = _server(
        state_dir,
        lambda **_: _agent(project, resumed_executed, ["call-3"]),
    )
    resumed.on_connect(resumed_client)
    await resumed.resume_session(session.session_id, str(project), mcp_servers=[])
    response = await resumed.prompt(
        session.session_id,
        [text_block("after resume")],
    )

    assert response.stop_reason == "end_turn"
    assert resumed_executed == ["value-0"]
    assert resumed_client.requests == []
    await resumed.close_session(session.session_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "decision",
    [
        _cancelled(),
        _selected("unknown-option"),
        _selected("reject_once"),
        {"not": "an ACP outcome"},
    ],
)
async def test_cancelled_unknown_and_reject_outcomes_execute_no_tool(
    tmp_path,
    monkeypatch,
    decision,
):
    project = _project(tmp_path, monkeypatch)
    executed: list[str] = []
    client = _ApprovalClient(decision)
    server = _server(
        tmp_path / "state",
        lambda **_: _agent(project, executed, ["call-reject"]),
    )
    server.on_connect(client)
    session = await server.new_session(str(project), mcp_servers=[])

    response = await server.prompt(session.session_id, [text_block("do not write")])

    assert response.stop_reason == "refusal"
    assert executed == []
    stored, _ = load_snapshot(tmp_path / "state", session.session_id)
    assert stored["turn"] == 0


@pytest.mark.asyncio
async def test_permission_transport_failure_rolls_back_without_private_details(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    executed: list[str] = []
    client = _ApprovalClient(RuntimeError("private transport marker"))
    server = _server(
        state_dir,
        lambda **_: _agent(project, executed, ["call-fail"]),
    )
    server.on_connect(client)
    session = await server.new_session(str(project), mcp_servers=[])

    response = await server.prompt(
        session.session_id,
        [text_block("private prompt")],
    )

    assert response.stop_reason == "refusal"
    assert executed == []
    stored, _ = load_snapshot(state_dir, session.session_id)
    assert stored["turn"] == 0


@pytest.mark.asyncio
async def test_session_grant_rolls_back_when_atomic_persistence_fails(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    executed: list[str] = []
    client = _ApprovalClient(_selected("allow_session"))
    server = _server(
        state_dir,
        lambda **_: _agent(project, executed, ["call-save-fail"]),
    )
    server.on_connect(client)
    session = await server.new_session(str(project), mcp_servers=[])

    def fail_save(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("private persistence marker")

    monkeypatch.setattr(acp_server, "save_snapshot", fail_save)

    with pytest.raises(RequestError) as exc_info:
        await server.prompt(session.session_id, [text_block("write then fail")])

    assert "private persistence marker" not in str(exc_info.value)
    assert executed == ["value-0"]
    runtime = server._sessions[session.session_id]
    assert "write" not in runtime.agent.current_session.get("permissions", {})
    stored, _ = load_snapshot(state_dir, session.session_id)
    assert "write" not in stored.get("permissions", {})


@pytest.mark.asyncio
async def test_session_grant_rolls_back_when_a_later_acp_update_fails(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    executed: list[str] = []
    client = _FailAfterSessionGrantClient()
    server = _server(
        state_dir,
        lambda **_: _agent(project, executed, ["call-update-fail"]),
    )
    server.on_connect(client)
    session = await server.new_session(str(project), mcp_servers=[])

    with pytest.raises(RequestError) as exc_info:
        await server.prompt(session.session_id, [text_block("write then fail")])

    assert "private update marker" not in str(exc_info.value)
    assert executed == ["value-0"]
    runtime = server._sessions[session.session_id]
    assert "write" not in runtime.agent.current_session.get("permissions", {})
    stored, _ = load_snapshot(state_dir, session.session_id)
    assert "write" not in stored.get("permissions", {})
    assert stored["turn"] == 0


@pytest.mark.asyncio
async def test_cancel_while_permission_is_pending_is_bounded_and_fail_closed(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    executed: list[str] = []
    client = _BlockingApprovalClient()
    server = _server(
        tmp_path / "state",
        lambda **_: _agent(project, executed, ["call-blocked"]),
    )
    server.on_connect(client)
    session = await server.new_session(str(project), mcp_servers=[])
    prompting = asyncio.create_task(
        server.prompt(session.session_id, [text_block("wait")])
    )
    await asyncio.wait_for(client.started.wait(), timeout=1)

    await server.cancel(session.session_id)
    response = await asyncio.wait_for(prompting, timeout=1)

    assert response.stop_reason == "cancelled"
    assert executed == []
    await asyncio.wait_for(client.cancelled.wait(), timeout=1)


@pytest.mark.asyncio
async def test_close_while_permission_is_pending_waits_then_releases_lease(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    executed: list[str] = []
    client = _BlockingApprovalClient()
    server = _server(
        state_dir,
        lambda **_: _agent(project, executed, ["call-close"]),
    )
    server.on_connect(client)
    session = await server.new_session(str(project), mcp_servers=[])
    prompting = asyncio.create_task(
        server.prompt(session.session_id, [text_block("wait")])
    )
    await asyncio.wait_for(client.started.wait(), timeout=1)

    closing = asyncio.create_task(server.close_session(session.session_id))
    response = await asyncio.wait_for(prompting, timeout=1)
    await asyncio.wait_for(closing, timeout=1)

    assert response.stop_reason == "cancelled"
    assert executed == []
    with session_lock(state_dir, session.session_id):
        pass


@pytest.mark.asyncio
async def test_eof_cleanup_while_permission_is_pending_releases_lease(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    state_dir = tmp_path / "state"
    executed: list[str] = []
    client = _BlockingApprovalClient()
    server = _server(
        state_dir,
        lambda **_: _agent(project, executed, ["call-eof"]),
    )
    server.on_connect(client)
    session = await server.new_session(str(project), mcp_servers=[])
    prompting = asyncio.create_task(
        server.prompt(session.session_id, [text_block("wait")])
    )
    await asyncio.wait_for(client.started.wait(), timeout=1)

    closing = asyncio.create_task(server.close_all())
    response = await asyncio.wait_for(prompting, timeout=1)
    await asyncio.wait_for(closing, timeout=1)

    assert response.stop_reason == "cancelled"
    assert executed == []
    assert server._sessions == {}
    with session_lock(state_dir, session.session_id):
        pass


@pytest.mark.asyncio
async def test_identical_tool_ids_in_two_sessions_cannot_cross_decisions(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path, monkeypatch)
    executed: dict[str, list[str]] = {"first": [], "second": []}
    created = 0

    def factory(**_kwargs: Any) -> Agent:
        nonlocal created
        key = "first" if created == 0 else "second"
        created += 1
        return _agent(project, executed[key], ["shared-tool-id"])

    class SessionClient(_ApprovalClient):
        async def request_permission(self, **kwargs: Any) -> RequestPermissionResponse:
            self.requests.append((
                kwargs["session_id"],
                kwargs["tool_call"],
                kwargs["options"],
            ))
            option = "allow_once" if kwargs["session_id"] == first.session_id else "reject_once"
            return RequestPermissionResponse.model_validate(_selected(option))

    client = SessionClient()
    server = _server(tmp_path / "state", factory)
    server.on_connect(client)
    first = await server.new_session(str(project), mcp_servers=[])
    second = await server.new_session(str(project), mcp_servers=[])

    first_result, second_result = await asyncio.gather(
        server.prompt(first.session_id, [text_block("first")]),
        server.prompt(second.session_id, [text_block("second")]),
    )

    assert first_result.stop_reason == "end_turn"
    assert second_result.stop_reason == "refusal"
    assert executed == {"first": ["value-0"], "second": []}
    assert {session_id for session_id, _, _ in client.requests} == {
        first.session_id,
        second.session_id,
    }


@pytest.mark.asyncio
async def test_late_cancelled_reply_cannot_enter_the_next_generation(
    tmp_path,
    monkeypatch,
):
    _project(tmp_path, monkeypatch)
    first_started = asyncio.Event()
    release_late_reply = asyncio.Event()
    calls = 0

    async def requester(
        _session_id: str,
        _tool_call: ToolCallUpdate,
        _options: list[PermissionOption],
    ) -> RequestPermissionResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            first_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                # Simulate a client/proxy that cannot abort its remote dialog.
                await release_late_reply.wait()
                return RequestPermissionResponse.model_validate(
                    _selected("allow_once")
                )
        return RequestPermissionResponse.model_validate(_selected("reject_once"))

    bridge = _ACPEventBridge(
        asyncio.get_running_loop(),
        "session-one",
        requester,
    )
    first_generation, first_io = bridge.begin_turn()

    def ask(io, tool_call_id: str) -> dict[str, Any]:
        io.send({
            "type": "approval_needed",
            "tool_call_id": tool_call_id,
            "tool": "write",
            "arguments": {"content": tool_call_id},
        })
        return io.receive()

    first_waiter = asyncio.create_task(
        asyncio.to_thread(ask, first_io, "shared-id")
    )
    await asyncio.wait_for(first_started.wait(), timeout=1)
    bridge.interrupt()
    assert await asyncio.wait_for(first_waiter, timeout=1) == {
        "type": "INTERRUPT"
    }
    bridge.retire_turn(first_generation)

    second_generation, second_io = bridge.begin_turn()
    second_response = await asyncio.wait_for(
        asyncio.to_thread(ask, second_io, "shared-id"),
        timeout=1,
    )
    assert second_response == {"approved": False, "mode": "reject_hard"}

    release_late_reply.set()
    await asyncio.sleep(0)
    bridge.retire_turn(second_generation)
    assert calls == 2
