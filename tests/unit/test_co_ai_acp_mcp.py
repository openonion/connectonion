"""ACP stdio MCP authority and session-lifecycle tests."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from acp import PROTOCOL_VERSION, RequestError, text_block
from acp.schema import (
    EnvVariable,
    McpServerStdio,
    RequestPermissionResponse,
    ToolCallProgress,
)

from connectonion import Agent
from connectonion.cli.co_ai import acp_mcp, acp_server
from connectonion.cli.co_ai.acp_mcp import (
    MAX_MCP_ARGUMENT_BYTES,
    MAX_MCP_RESULT_BYTES,
    MCP_CONNECT_TIMEOUT_SECONDS,
    MCPConfigError,
    MCPPool,
    MCPTool,
    MCPToolError,
    connect_mcp_servers,
    mcp_tool_name,
    validate_stdio_servers,
)
from connectonion.cli.co_ai.acp_server import ConnectOnionACPAgent
from connectonion.cli.co_ai.one_shot_sessions import load_snapshot
from connectonion.core.interrupt import UserInterrupt
from connectonion.core.llm import LLMResponse, ToolCall
from connectonion.core.tool_registry import ToolRegistry
from connectonion.useful_plugins import tool_approval
from tests.utils.mock_helpers import MockLLM


@pytest.fixture(autouse=True)
def _isolated_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


class _Agent:
    system_prompt = "system"

    def __init__(self) -> None:
        self.io: Any = None
        self.tools = ToolRegistry()
        self.current_session: dict[str, Any] = {"trace": [], "turn": 0}

    def add_tool(self, tool: Any) -> None:
        self.tools.add(tool)

    def input(self, _prompt: str, session: dict[str, Any] | None = None) -> str:
        if session is not None:
            self.current_session = deepcopy(session)
        return "done"


class _Tool:
    name = "mcp__notes_abc123__read_def456"
    description = "Read a note"

    def to_function_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": {}},
            },
        }


class _Pool:
    def __init__(self) -> None:
        self.tools = [_Tool()]
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def _server_spec() -> McpServerStdio:
    return McpServerStdio(
        name="notes",
        command="/usr/bin/true",
        args=[],
        env=[EnvVariable(name="EXPLICIT", value="yes")],
    )


def test_mcp_cold_start_timeout_remains_bounded_with_import_headroom():
    assert MCP_CONNECT_TIMEOUT_SECONDS == 30.0


async def _assert_process_reaped(pid: int, message: str) -> None:
    for _ in range(100):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        await asyncio.sleep(0.01)
    pytest.fail(message)


@pytest.mark.asyncio
async def test_mcp_is_rejected_before_connect_without_launch_authority(tmp_path):
    connected = False

    async def connector(*_args: Any, **_kwargs: Any) -> _Pool:
        nonlocal connected
        connected = True
        return _Pool()

    server = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _Agent(),
        session_co_dir=tmp_path / "state",
        mcp_connector=connector,
    )

    await server.initialize(protocol_version=PROTOCOL_VERSION)
    with pytest.raises(RequestError, match="Invalid params"):
        await server.new_session(str(tmp_path), mcp_servers=[_server_spec()])

    assert connected is False


@pytest.mark.asyncio
async def test_authorized_mcp_tools_are_session_scoped_and_closed(tmp_path):
    pool = _Pool()
    connection: dict[str, Any] = {}

    async def connector(
        servers: list[Any], *, cwd: Any, loop: asyncio.AbstractEventLoop
    ) -> _Pool:
        connection.update(servers=servers, cwd=cwd, loop=loop)
        return pool

    agent = _Agent()
    server = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: agent,
        session_co_dir=tmp_path / "state",
        allow_mcp=True,
        mcp_connector=connector,
    )

    await server.initialize(protocol_version=PROTOCOL_VERSION)
    session = await server.new_session(str(tmp_path), mcp_servers=[_server_spec()])

    assert connection["servers"] == [_server_spec()]
    assert connection["cwd"] == tmp_path.resolve()
    assert connection["loop"] is asyncio.get_running_loop()
    assert agent.tools.names() == [_Tool.name]

    await server.close_session(session.session_id)

    assert pool.closed is True


@pytest.mark.asyncio
async def test_runtime_construction_failure_closes_connected_mcp_pool(tmp_path):
    pool = _Pool()

    async def connector(*_args: Any, **_kwargs: Any) -> _Pool:
        return pool

    def broken_factory(**_kwargs: Any) -> _Agent:
        raise RuntimeError("agent construction failed")

    server = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=broken_factory,
        session_co_dir=tmp_path / "state",
        allow_mcp=True,
        mcp_connector=connector,
    )

    await server.initialize(protocol_version=PROTOCOL_VERSION)
    with pytest.raises(RequestError, match="Unable to create"):
        await server.new_session(str(tmp_path), mcp_servers=[_server_spec()])

    assert pool.closed is True


@pytest.mark.asyncio
async def test_existing_tool_name_collision_closes_connected_mcp_pool(tmp_path):
    pool = _Pool()
    agent = _Agent()
    agent.add_tool(_Tool())

    async def connector(*_args: Any, **_kwargs: Any) -> _Pool:
        return pool

    server = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: agent,
        session_co_dir=tmp_path / "state",
        allow_mcp=True,
        mcp_connector=connector,
    )

    await server.initialize(protocol_version=PROTOCOL_VERSION)
    with pytest.raises(RequestError, match="Unable to create"):
        await server.new_session(str(tmp_path), mcp_servers=[_server_spec()])

    assert pool.closed is True


@pytest.mark.asyncio
async def test_locked_resume_is_rejected_before_connecting_mcp(tmp_path):
    owner = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _Agent(),
        session_co_dir=tmp_path / "state",
    )
    await owner.initialize(protocol_version=PROTOCOL_VERSION)
    created = await owner.new_session(str(tmp_path), mcp_servers=[])
    connected = False

    async def connector(*_args: Any, **_kwargs: Any) -> _Pool:
        nonlocal connected
        connected = True
        return _Pool()

    contender = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _Agent(),
        session_co_dir=tmp_path / "state",
        allow_mcp=True,
        mcp_connector=connector,
    )

    await contender.initialize(protocol_version=PROTOCOL_VERSION)
    with pytest.raises(RequestError, match="Unable to resume"):
        await contender.resume_session(
            created.session_id,
            str(tmp_path),
            mcp_servers=[_server_spec()],
        )

    assert connected is False
    await owner.close_session(created.session_id)


def test_stdio_server_configuration_is_bounded_and_requires_absolute_commands():
    with pytest.raises(MCPConfigError, match="absolute"):
        validate_stdio_servers([
            McpServerStdio(name="notes", command="python", args=[], env=[])
        ])

    duplicate = McpServerStdio(
        name="notes",
        command="/usr/bin/true",
        args=[],
        env=[],
    )
    with pytest.raises(MCPConfigError, match="unique"):
        validate_stdio_servers([duplicate, duplicate])


def test_mcp_tool_names_are_stable_bounded_and_disambiguated():
    first = mcp_tool_name("My Server / production", "read file")
    second = mcp_tool_name("My Server / staging", "read file")

    assert first == mcp_tool_name("My Server / production", "read file")
    assert first.startswith("mcp__my_server_")
    assert first != second
    assert len(first) <= 64


@pytest.mark.asyncio
async def test_discovery_rejects_a_non_object_input_schema():
    class Client:
        async def list_tools(self, **_kwargs: Any):
            return SimpleNamespace(
                tools=[SimpleNamespace(
                    name="bad-schema",
                    description=None,
                    input_schema={"type": "string"},
                )],
                next_cursor=None,
            )

    pool = object.__new__(MCPPool)
    pool._loop = asyncio.get_running_loop()

    with pytest.raises(MCPConfigError, match="inputSchema must be an object"):
        await pool._discover_tools(Client(), 0, "context", set())


class _MCPClient:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any], **_kwargs: Any):
        self.calls.append((name, arguments))
        return SimpleNamespace(
            is_error=False,
            model_dump=lambda **_kwargs: self.result,
        )


@pytest.mark.asyncio
async def test_mcp_tool_runs_on_the_owner_loop_and_returns_bounded_json():
    client = _MCPClient({"content": [{"type": "text", "text": "hello"}]})
    tool = MCPTool(
        client=client,
        server_name="notes",
        remote_name="read_note",
        description="Read one note",
        input_schema={"type": "object", "properties": {"id": {"type": "string"}}},
        loop=asyncio.get_running_loop(),
    )
    agent = SimpleNamespace(io=SimpleNamespace(is_cancelled=lambda: False))

    result = await asyncio.to_thread(tool, agent=agent, id="42")

    assert result["content"][0]["text"] == "hello"
    assert client.calls == [("read_note", {"id": "42"})]
    assert tool._needs_agent is True
    assert tool.to_function_schema()["parameters"] == tool.get_parameters_schema()


@pytest.mark.asyncio
async def test_mcp_tool_honors_cancellation_before_remote_execution():
    client = _MCPClient({"content": []})
    tool = MCPTool(
        client=client,
        server_name="notes",
        remote_name="read_note",
        description="Read one note",
        input_schema={"type": "object"},
        loop=asyncio.get_running_loop(),
    )
    agent = SimpleNamespace(io=SimpleNamespace(is_cancelled=lambda: True))

    with pytest.raises(UserInterrupt):
        await asyncio.to_thread(tool, agent=agent)

    assert client.calls == []


@pytest.mark.asyncio
async def test_mcp_tool_timeout_cancels_the_remote_request(monkeypatch):
    cancelled = asyncio.Event()

    class BlockingClient:
        async def call_tool(self, *_args: Any, **_kwargs: Any):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    monkeypatch.setattr(acp_mcp, "MCP_CALL_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(acp_mcp, "_TOOL_POLL_SECONDS", 0.001)
    tool = MCPTool(
        client=BlockingClient(),
        server_name="notes",
        remote_name="read_note",
        description="Read one note",
        input_schema={"type": "object"},
        loop=asyncio.get_running_loop(),
    )
    agent = SimpleNamespace(io=SimpleNamespace(is_cancelled=lambda: False))

    with pytest.raises(MCPToolError, match="exceeded the timeout"):
        await asyncio.to_thread(tool, agent=agent)

    await asyncio.wait_for(cancelled.wait(), timeout=1)


@pytest.mark.asyncio
async def test_mcp_tool_recovers_when_call_finishes_at_poll_timeout(monkeypatch):
    payload = {"content": [{"type": "text", "text": "finished"}]}

    class RacyFuture:
        def __init__(self) -> None:
            self.result_calls = 0

        def result(self, timeout: float | None = None):
            self.result_calls += 1
            if self.result_calls == 1:
                raise concurrent.futures.TimeoutError()
            return SimpleNamespace(
                is_error=False,
                model_dump=lambda **_kwargs: payload,
            )

        def done(self) -> bool:
            return True

        def cancel(self) -> None:
            pass

    racy = RacyFuture()

    def run_racy(coroutine: Any, _loop: asyncio.AbstractEventLoop) -> RacyFuture:
        coroutine.close()
        return racy

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", run_racy)
    tool = MCPTool(
        client=_MCPClient(payload),
        server_name="notes",
        remote_name="read_note",
        description="Read one note",
        input_schema={"type": "object"},
        loop=asyncio.get_running_loop(),
    )
    agent = SimpleNamespace(io=SimpleNamespace(is_cancelled=lambda: False))

    result = await asyncio.to_thread(tool, agent=agent)

    assert result == payload
    assert racy.result_calls == 2


@pytest.mark.asyncio
async def test_mcp_tool_refuses_oversized_results():
    client = _MCPClient({"content": [{"type": "text", "text": "x" * MAX_MCP_RESULT_BYTES}]})
    tool = MCPTool(
        client=client,
        server_name="notes",
        remote_name="read_note",
        description="Read one note",
        input_schema={"type": "object"},
        loop=asyncio.get_running_loop(),
    )
    agent = SimpleNamespace(io=SimpleNamespace(is_cancelled=lambda: False))

    with pytest.raises(MCPToolError, match="result limit"):
        await asyncio.to_thread(tool, agent=agent)


@pytest.mark.asyncio
async def test_mcp_tool_refuses_oversized_arguments_before_remote_execution():
    client = _MCPClient({"content": []})
    tool = MCPTool(
        client=client,
        server_name="notes",
        remote_name="read_note",
        description="Read one note",
        input_schema={"type": "object"},
        loop=asyncio.get_running_loop(),
    )
    agent = SimpleNamespace(io=SimpleNamespace(is_cancelled=lambda: False))

    with pytest.raises(MCPToolError, match="argument limit"):
        await asyncio.to_thread(
            tool,
            agent=agent,
            content="x" * MAX_MCP_ARGUMENT_BYTES,
        )

    assert client.calls == []


@pytest.mark.asyncio
async def test_mcp_tool_replaces_oversized_transport_errors_with_bounded_message():
    class FailingClient:
        async def call_tool(self, *_args: Any, **_kwargs: Any):
            raise RuntimeError("remote-secret-" + "x" * (MAX_MCP_RESULT_BYTES * 2))

    tool = MCPTool(
        client=FailingClient(),
        server_name="notes",
        remote_name="read_note",
        description="Read one note",
        input_schema={"type": "object"},
        loop=asyncio.get_running_loop(),
    )
    agent = SimpleNamespace(io=SimpleNamespace(is_cancelled=lambda: False))

    with pytest.raises(MCPToolError) as exc_info:
        await asyncio.to_thread(tool, agent=agent)

    assert str(exc_info.value) == "MCP tool call failed"
    assert "remote-secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_real_mcp_v2_stdio_is_environment_isolated_and_reaped(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ACP_MCP_PARENT_SECRET", "must-not-be-inherited")
    fixture = Path(__file__).parents[1] / "fixtures" / "acp_mcp_server.py"
    spec = McpServerStdio(
        name="context",
        command=sys.executable,
        args=[str(fixture)],
        env=[EnvVariable(name="ACP_MCP_EXPLICIT", value="yes")],
    )
    pool = await connect_mcp_servers(
        [spec],
        cwd=tmp_path,
        loop=asyncio.get_running_loop(),
    )
    tool = next(item for item in pool.tools if "process_context" in item.name)
    agent = SimpleNamespace(io=SimpleNamespace(is_cancelled=lambda: False))

    result = await asyncio.to_thread(tool, agent=agent, value="hello")
    structured = result["structuredContent"]

    assert structured["value"] == "hello"
    assert structured["cwd"] == str(tmp_path)
    assert structured["explicit"] == "yes"
    assert structured["parent_secret_present"] is False
    pid = structured["pid"]

    await pool.close()
    await _assert_process_reaped(
        pid,
        "MCP stdio child was still alive after pool.close()",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup", ["session_close", "client_eof"])
async def test_acp_session_teardown_reaps_real_mcp_process(tmp_path, cleanup):
    fixture = Path(__file__).parents[1] / "fixtures" / "acp_mcp_server.py"
    pid_file = tmp_path / f"{cleanup}.pid"
    spec = McpServerStdio(
        name="context",
        command=sys.executable,
        args=[str(fixture)],
        env=[EnvVariable(name="ACP_MCP_PID_FILE", value=str(pid_file))],
    )
    server = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _Agent(),
        session_co_dir=tmp_path / "state",
        allow_mcp=True,
    )
    await server.initialize(protocol_version=PROTOCOL_VERSION)
    created = await server.new_session(str(tmp_path), mcp_servers=[spec])
    pid = int(pid_file.read_text(encoding="utf-8"))

    if cleanup == "session_close":
        await server.close_session(created.session_id)
    else:
        await server.close_all()

    assert created.session_id not in server._sessions
    await _assert_process_reaped(
        pid,
        f"MCP child survived ACP {cleanup}",
    )


@pytest.mark.asyncio
async def test_partial_mcp_startup_failure_reaps_already_started_servers(tmp_path):
    fixture = Path(__file__).parents[1] / "fixtures" / "acp_mcp_server.py"
    pid_file = tmp_path / "first.pid"
    first = McpServerStdio(
        name="first",
        command=sys.executable,
        args=[str(fixture)],
        env=[EnvVariable(name="ACP_MCP_PID_FILE", value=str(pid_file))],
    )
    second = McpServerStdio(
        name="second",
        command=str(tmp_path / "missing-executable"),
        args=[],
        env=[],
    )

    with pytest.raises(Exception):
        await connect_mcp_servers(
            [first, second],
            cwd=tmp_path,
            loop=asyncio.get_running_loop(),
        )

    assert pid_file.exists()
    pid = int(pid_file.read_text(encoding="utf-8"))
    await _assert_process_reaped(
        pid,
        "First MCP child survived a later server startup failure",
    )


@pytest.mark.asyncio
async def test_resume_reconnects_mcp_without_persisting_launch_data(tmp_path):
    fixture = Path(__file__).parents[1] / "fixtures" / "acp_mcp_server.py"
    secret_value = "session-only-explicit-value"
    spec = McpServerStdio(
        name="context",
        command=sys.executable,
        args=[str(fixture)],
        env=[EnvVariable(name="ACP_MCP_EXPLICIT", value=secret_value)],
    )
    server = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _Agent(),
        session_co_dir=tmp_path / "state",
        allow_mcp=True,
    )
    await server.initialize(protocol_version=PROTOCOL_VERSION)
    first = await server.new_session(str(tmp_path), mcp_servers=[spec])
    first_runtime = server._sessions[first.session_id]
    first_tool = next(
        tool for tool in first_runtime.agent.tools if "process_context" in tool.name
    )
    first_result = await asyncio.to_thread(
        first_tool,
        agent=SimpleNamespace(io=SimpleNamespace(is_cancelled=lambda: False)),
        value="first",
    )
    first_pid = first_result["structuredContent"]["pid"]
    await server.close_session(first.session_id)

    stored = json.dumps(
        load_snapshot(tmp_path / "state", first.session_id),
        default=str,
    )
    assert str(fixture) not in stored
    assert secret_value not in stored

    await server.resume_session(
        first.session_id,
        str(tmp_path),
        mcp_servers=[spec],
    )
    resumed_runtime = server._sessions[first.session_id]
    resumed_tool = next(
        tool for tool in resumed_runtime.agent.tools if "process_context" in tool.name
    )
    resumed_result = await asyncio.to_thread(
        resumed_tool,
        agent=SimpleNamespace(io=SimpleNamespace(is_cancelled=lambda: False)),
        value="resumed",
    )

    assert resumed_result["structuredContent"]["pid"] != first_pid
    assert resumed_result["structuredContent"]["explicit"] == secret_value
    await server.close_session(first.session_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_stop", "should_write"),
    [
        ("allow_once", "end_turn", True),
        ("reject_once", "refusal", False),
    ],
)
async def test_real_mcp_side_effect_waits_for_acp_permission(
    tmp_path,
    monkeypatch,
    decision,
    expected_stop,
    should_write,
):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    marker = project / "approved.txt"
    fixture = Path(__file__).parents[1] / "fixtures" / "acp_mcp_server.py"
    spec = McpServerStdio(
        name="context",
        command=sys.executable,
        args=[str(fixture)],
        env=[],
    )
    exported_name = mcp_tool_name("context", "write_marker")

    class ApprovalClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, Any]] = []
            self.updates: list[Any] = []

        async def request_permission(self, **kwargs: Any):
            assert marker.exists() is False
            self.requests.append(
                kwargs["tool_call"].model_dump(
                    mode="json", by_alias=True, exclude_none=True
                )
            )
            return RequestPermissionResponse.model_validate({
                "outcome": {
                    "outcome": "selected",
                    "optionId": decision,
                }
            })

        async def session_update(self, **kwargs: Any) -> None:
            self.updates.append(kwargs["update"])

    def factory(**_kwargs: Any) -> Agent:
        return Agent(
            name="acp-mcp-approval",
            tools=[],
            plugins=[tool_approval],
            llm=MockLLM(responses=[
                LLMResponse(
                    content="",
                    tool_calls=[ToolCall(
                        name=exported_name,
                        arguments={"path": str(marker), "content": "approved"},
                        id="mcp-write-1",
                    )],
                    raw_response={},
                ),
                LLMResponse(
                    content="done",
                    tool_calls=[],
                    raw_response={},
                ),
            ]),
            max_iterations=2,
            log=False,
            quiet=True,
            co_dir=project / ".co",
        )

    client = ApprovalClient()
    server = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=factory,
        session_co_dir=tmp_path / "state",
        allow_mcp=True,
    )
    server.on_connect(client)  # type: ignore[arg-type]
    await server.initialize(protocol_version=PROTOCOL_VERSION)
    session = await server.new_session(str(project), mcp_servers=[spec])

    response = await server.prompt(session.session_id, [text_block("write")])

    assert response.stop_reason == expected_stop
    assert marker.exists() is should_write
    assert len(client.requests) == 1
    assert client.requests[0]["title"] == exported_name
    assert client.requests[0]["rawInput"]["content"] == "approved"
    completed = [
        update
        for update in client.updates
        if isinstance(update, ToolCallProgress) and update.status == "completed"
    ]
    if should_write:
        assert len(completed) == 1
        assert isinstance(completed[0].raw_output, dict)
        assert completed[0].content[0].content.text
    else:
        assert completed == []
    await server.close_session(session.session_id)


@pytest.mark.asyncio
async def test_mcp_session_approval_is_not_reused_after_resume(
    tmp_path,
    monkeypatch,
):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    fixture = Path(__file__).parents[1] / "fixtures" / "acp_mcp_server.py"
    first_marker = project / "first.txt"
    resumed_marker = project / "resumed.txt"
    exported_name = mcp_tool_name("context", "write_marker")
    markers = iter((first_marker, resumed_marker))

    class ApprovalClient:
        def __init__(self, decision: str) -> None:
            self.decision = decision
            self.requests: list[dict[str, Any]] = []

        async def request_permission(self, **kwargs: Any):
            self.requests.append(kwargs["tool_call"].model_dump(mode="json"))
            return RequestPermissionResponse.model_validate({
                "outcome": {
                    "outcome": "selected",
                    "optionId": self.decision,
                }
            })

        async def session_update(self, **_kwargs: Any) -> None:
            pass

    def factory(**_kwargs: Any) -> Agent:
        marker = next(markers)
        return Agent(
            name="acp-mcp-resume-approval",
            tools=[],
            plugins=[tool_approval],
            llm=MockLLM(responses=[
                LLMResponse(
                    content="",
                    tool_calls=[ToolCall(
                        name=exported_name,
                        arguments={"path": str(marker), "content": "written"},
                        id=f"write-{marker.stem}",
                    )],
                    raw_response={},
                ),
                LLMResponse(content="done", tool_calls=[], raw_response={}),
            ]),
            max_iterations=2,
            log=False,
            quiet=True,
            co_dir=project / ".co",
        )

    server = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=factory,
        session_co_dir=tmp_path / "state",
        allow_mcp=True,
    )
    first_client = ApprovalClient("allow_session")
    server.on_connect(first_client)  # type: ignore[arg-type]
    await server.initialize(protocol_version=PROTOCOL_VERSION)
    first_spec = McpServerStdio(
        name="context",
        command=sys.executable,
        args=[str(fixture)],
        env=[EnvVariable(name="ACP_MCP_EXPLICIT", value="first-launch")],
    )
    created = await server.new_session(str(project), mcp_servers=[first_spec])

    first_response = await server.prompt(created.session_id, [text_block("write")])

    assert first_response.stop_reason == "end_turn"
    assert first_marker.read_text(encoding="utf-8") == "written"
    assert len(first_client.requests) == 1
    stored, _ = load_snapshot(tmp_path / "state", created.session_id)
    assert exported_name not in stored.get("permissions", {})
    await server.close_session(created.session_id)

    second_client = ApprovalClient("reject_once")
    server.on_connect(second_client)  # type: ignore[arg-type]
    resumed_spec = McpServerStdio(
        name="context",
        command=sys.executable,
        args=[str(fixture)],
        env=[EnvVariable(name="ACP_MCP_EXPLICIT", value="changed-launch")],
    )
    await server.resume_session(
        created.session_id,
        str(project),
        mcp_servers=[resumed_spec],
    )
    try:
        resumed_response = await server.prompt(
            created.session_id,
            [text_block("write again")],
        )

        assert resumed_response.stop_reason == "refusal"
        assert len(second_client.requests) == 1
        assert resumed_marker.exists() is False
    finally:
        await server.close_session(created.session_id)


@pytest.mark.asyncio
async def test_operator_mcp_permission_remains_configured_after_resume(
    tmp_path,
    monkeypatch,
):
    project = tmp_path / "project"
    co_dir = project / ".co"
    co_dir.mkdir(parents=True)
    monkeypatch.chdir(project)
    fixture = Path(__file__).parents[1] / "fixtures" / "acp_mcp_server.py"
    exported_name = mcp_tool_name("context", "write_marker")
    (co_dir / "host.yaml").write_text(
        "permissions:\n"
        f"  {exported_name}:\n"
        "    allowed: true\n"
        "    source: config\n"
        "    reason: operator configured\n"
        "    expires:\n"
        "      type: never\n",
        encoding="utf-8",
    )
    first_marker = project / "configured-first.txt"
    resumed_marker = project / "configured-resumed.txt"
    markers = iter((first_marker, resumed_marker))
    spec = McpServerStdio(
        name="context",
        command=sys.executable,
        args=[str(fixture)],
        env=[],
    )

    class Client:
        async def request_permission(self, **_kwargs: Any):
            raise AssertionError("host.yaml MCP permission should not prompt")

        async def session_update(self, **_kwargs: Any) -> None:
            pass

    def factory(**_kwargs: Any) -> Agent:
        marker = next(markers)
        return Agent(
            name="acp-mcp-configured-permission",
            tools=[],
            plugins=[tool_approval],
            llm=MockLLM(responses=[
                LLMResponse(
                    content="",
                    tool_calls=[ToolCall(
                        name=exported_name,
                        arguments={"path": str(marker), "content": "configured"},
                        id=f"configured-{marker.stem}",
                    )],
                    raw_response={},
                ),
                LLMResponse(content="done", tool_calls=[], raw_response={}),
            ]),
            max_iterations=2,
            log=False,
            quiet=True,
            co_dir=co_dir,
        )

    server = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=factory,
        session_co_dir=tmp_path / "state",
        allow_mcp=True,
    )
    server.on_connect(Client())  # type: ignore[arg-type]
    await server.initialize(protocol_version=PROTOCOL_VERSION)
    created = await server.new_session(str(project), mcp_servers=[spec])

    first_response = await server.prompt(created.session_id, [text_block("write")])

    assert first_response.stop_reason == "end_turn"
    assert first_marker.read_text(encoding="utf-8") == "configured"
    stored, _ = load_snapshot(tmp_path / "state", created.session_id)
    assert stored["permissions"][exported_name]["source"] == "config"
    await server.close_session(created.session_id)

    await server.resume_session(
        created.session_id,
        str(project),
        mcp_servers=[spec],
    )
    try:
        resumed_response = await server.prompt(
            created.session_id,
            [text_block("write again")],
        )

        assert resumed_response.stop_reason == "end_turn"
        assert resumed_marker.read_text(encoding="utf-8") == "configured"
    finally:
        await server.close_session(created.session_id)


@pytest.mark.asyncio
async def test_failed_restore_reaps_mcp_process_before_releasing_session(
    tmp_path,
    monkeypatch,
):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    fixture = Path(__file__).parents[1] / "fixtures" / "acp_mcp_server.py"
    pid_file = tmp_path / "restore.pid"
    spec = McpServerStdio(
        name="context",
        command=sys.executable,
        args=[str(fixture)],
        env=[EnvVariable(name="ACP_MCP_PID_FILE", value=str(pid_file))],
    )

    class Client:
        async def session_update(self, **_kwargs: Any) -> None:
            pass

    def factory(**_kwargs: Any) -> Agent:
        return Agent(
            name="acp-mcp-failed-restore",
            tools=[],
            llm=MockLLM(responses=[
                LLMResponse(content="done", tool_calls=[], raw_response={})
            ]),
            max_iterations=1,
            log=False,
            quiet=True,
            co_dir=project / ".co",
        )

    server = ConnectOnionACPAgent(
        model="test",
        max_iterations=1,
        yolo=False,
        yolo_turns=1,
        agent_factory=factory,
        session_co_dir=tmp_path / "state",
        allow_mcp=True,
    )
    server.on_connect(Client())  # type: ignore[arg-type]
    await server.initialize(protocol_version=PROTOCOL_VERSION)
    created = await server.new_session(str(project), mcp_servers=[spec])
    runtime = server._sessions[created.session_id]
    pid = int(pid_file.read_text(encoding="utf-8"))

    def fail_save(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("disk full")

    def fail_restore(_runtime: Any) -> None:
        raise RuntimeError("restore failed")

    monkeypatch.setattr(acp_server, "save_snapshot", fail_save)
    monkeypatch.setattr(server, "_restore_runtime", fail_restore)
    try:
        with pytest.raises(RequestError):
            await server.prompt(created.session_id, [text_block("fail")])

        assert created.session_id not in server._sessions
        await _assert_process_reaped(
            pid,
            "MCP child survived failed runtime restoration",
        )
    finally:
        await runtime.mcp_pool.close()
