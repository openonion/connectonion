"""ACP lifecycle tests that do not require a live model or external client."""

from __future__ import annotations

import asyncio
import io
import json
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest
from acp import PROTOCOL_VERSION, RequestError, connect_to_agent, run_agent, text_block
from acp.interfaces import Client

from connectonion.cli.co_ai.acp_server import (
    ConnectOnionACPAgent,
    _FailClosedACPInput,
)
from connectonion.cli.co_ai.acp_transport import (
    _BoundStdoutWriter,
    _StrictNDJSONTransport,
)
from connectonion.useful_plugins.tool_approval import check_approval


class _MemoryTransport:
    def __init__(self) -> None:
        self.inbox: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.peer: _MemoryTransport | None = None
        self.closed = False

    async def send(self, message: dict[str, Any]) -> None:
        assert self.peer is not None
        await self.peer.inbox.put(message)

    async def receive(self) -> dict[str, Any] | None:
        return await self.inbox.get()

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        assert self.peer is not None
        await self.peer.inbox.put(None)


def _transport_pair() -> tuple[_MemoryTransport, _MemoryTransport]:
    left = _MemoryTransport()
    right = _MemoryTransport()
    left.peer = right
    right.peer = left
    return left, right


class _RecordingClient(Client):
    def __init__(self) -> None:
        self.updates: list[tuple[str, Any]] = []

    async def session_update(self, session_id: str, update: Any, **_kwargs: Any) -> None:
        self.updates.append((session_id, update))

    async def request_permission(self, **_kwargs: Any) -> dict[str, Any]:
        return {"outcome": {"outcome": "cancelled"}}


class _FakeAgent:
    def __init__(self) -> None:
        self.io: Any = None
        self.prompts: list[str] = []

    def input(self, prompt: str) -> str:
        print("deliberate fake-agent stdout noise")
        self.prompts.append(prompt)
        return f"answer {len(self.prompts)}: {prompt}"


class _BlockingFakeAgent(_FakeAgent):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()

    def input(self, prompt: str) -> str:
        self.started.set()
        while not self.io.receive_all("INTERRUPT"):
            time.sleep(0.01)
        return f"cancelled: {prompt}"


@pytest.mark.asyncio
async def test_acp_lifecycle_reuses_agent_and_exits_on_eof(tmp_path, capsys):
    created: list[_FakeAgent] = []

    def factory(**_kwargs: Any) -> _FakeAgent:
        agent = _FakeAgent()
        created.append(agent)
        return agent

    server_transport, client_transport = _transport_pair()
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=factory,
    )
    server_task = asyncio.create_task(
        run_agent(acp_agent, input_stream=server_transport)
    )
    recording_client = _RecordingClient()
    connection = connect_to_agent(recording_client, client_transport)

    initialized = await connection.initialize(protocol_version=PROTOCOL_VERSION)
    session = await connection.new_session(cwd=str(tmp_path), mcp_servers=[])
    first = await connection.prompt(
        session_id=session.session_id,
        prompt=[text_block("first")],
    )
    second = await connection.prompt(
        session_id=session.session_id,
        prompt=[text_block("second")],
    )
    for _ in range(20):
        if len(recording_client.updates) == 2:
            break
        await asyncio.sleep(0)

    assert initialized.protocol_version == PROTOCOL_VERSION
    assert first.stop_reason == "end_turn"
    assert second.stop_reason == "end_turn"
    assert len(created) == 1
    assert created[0].prompts == ["first", "second"]
    assert [update.content.text for _, update in recording_client.updates] == [
        "answer 1: first",
        "answer 2: second",
    ]
    assert "deliberate fake-agent stdout noise" in capsys.readouterr().err

    await connection.close()
    await asyncio.wait_for(server_task, timeout=1)


@pytest.mark.asyncio
async def test_acp_reports_its_supported_version_for_any_client_version():
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _FakeAgent(),
    )

    older = await acp_agent.initialize(protocol_version=0)
    newer = await acp_agent.initialize(protocol_version=PROTOCOL_VERSION + 1)

    assert older.protocol_version == PROTOCOL_VERSION
    assert newer.protocol_version == PROTOCOL_VERSION


@pytest.mark.asyncio
async def test_acp_rejects_unknown_session():
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _FakeAgent(),
    )

    with pytest.raises(RequestError, match="Session not found"):
        await acp_agent.prompt("missing", [text_block("hello")])


@pytest.mark.asyncio
async def test_acp_cancel_stops_an_active_prompt(tmp_path):
    fake_agent = _BlockingFakeAgent()
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: fake_agent,
    )
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    prompt_task = asyncio.create_task(
        acp_agent.prompt(session.session_id, [text_block("wait")])
    )
    await asyncio.wait_for(asyncio.to_thread(fake_agent.started.wait), timeout=1)

    await acp_agent.cancel(session.session_id)
    response = await asyncio.wait_for(prompt_task, timeout=1)

    assert response.stop_reason == "cancelled"


def test_acp_approval_input_denies_sensitive_tools_unless_mode_is_explicit_ulw():
    acp_input = _FailClosedACPInput()
    session = {
        "mode": "safe",
        "permissions": {},
        "pending_tool": {
            "name": "bash",
            "arguments": {"command": "echo hello"},
        },
    }
    agent = SimpleNamespace(
        current_session=session,
        io=acp_input,
        storage=None,
    )

    with pytest.raises(ValueError, match="Connection closed"):
        check_approval(agent)

    session["mode"] = "ulw"
    check_approval(agent)


@pytest.mark.asyncio
async def test_acp_errors_do_not_echo_agent_exception_details(tmp_path):
    class _FailingAgent(_FakeAgent):
        def input(self, prompt: str) -> str:
            raise RuntimeError(f"secret-marker in {prompt}")

    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _FailingAgent(),
    )
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])

    with pytest.raises(RequestError) as exc_info:
        await acp_agent.prompt(session.session_id, [text_block("private-value")])

    assert "secret-marker" not in str(exc_info.value)
    assert "private-value" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_acp_rejects_unsupported_session_inputs(tmp_path):
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _FakeAgent(),
    )

    with pytest.raises(RequestError, match="Invalid params"):
        await acp_agent.new_session(
            str(tmp_path),
            additional_directories=[str(tmp_path / "extra")],
        )
    with pytest.raises(RequestError, match="Invalid params"):
        await acp_agent.new_session(str(tmp_path), mcp_servers=[object()])
    with pytest.raises(RequestError, match="Invalid params"):
        await acp_agent.new_session("relative/path")


class _BufferWriter:
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass


@pytest.mark.asyncio
async def test_strict_ndjson_returns_errors_and_keeps_reading():
    reader = asyncio.StreamReader()
    writer = _BufferWriter()
    transport = _StrictNDJSONTransport(reader, writer)  # type: ignore[arg-type]
    reader.feed_data(b"{not json}\n")
    reader.feed_data(b"[]\n")
    reader.feed_data(
        b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
    )

    message = await transport.receive()

    assert message == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {},
    }
    errors = [json.loads(line) for line in writer.buffer.splitlines()]
    assert [item["error"]["code"] for item in errors] == [-32700, -32600]
    assert [item["id"] for item in errors] == [None, None]


@pytest.mark.asyncio
async def test_strict_ndjson_accepts_a_frame_larger_than_stream_chunk_limit():
    reader = asyncio.StreamReader(limit=64)
    writer = _BufferWriter()
    transport = _StrictNDJSONTransport(reader, writer)
    large_text = "x" * 70_000
    frame = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "session/prompt",
        "params": {"text": large_text},
    }
    reader.feed_data(json.dumps(frame).encode() + b"\n")

    message = await transport.receive()

    assert message == frame


@pytest.mark.asyncio
async def test_strict_ndjson_rejects_a_frame_over_the_configured_limit():
    reader = asyncio.StreamReader(limit=64)
    writer = _BufferWriter()
    transport = _StrictNDJSONTransport(reader, writer, max_frame_bytes=128)
    reader.feed_data(b'{"jsonrpc":"2.0","id":1,"value":"' + b"x" * 200 + b'"}\n')

    message = await transport.receive()

    assert message is None
    error = json.loads(writer.buffer)
    assert error["error"]["code"] == -32700
    assert error["error"]["data"]["details"] == (
        "ACP frame exceeds the configured 128-byte limit"
    )


@pytest.mark.asyncio
async def test_strict_ndjson_rejects_an_oversized_final_frame_without_newline():
    reader = asyncio.StreamReader(limit=512)
    writer = _BufferWriter()
    transport = _StrictNDJSONTransport(reader, writer, max_frame_bytes=128)
    reader.feed_data(b'{"jsonrpc":"2.0","id":1,"value":"' + b"x" * 200 + b'"}')
    reader.feed_eof()

    message = await transport.receive()

    assert message is None
    assert json.loads(writer.buffer)["error"]["code"] == -32700


@pytest.mark.asyncio
async def test_bound_stdout_writer_uses_the_captured_binary_handle():
    captured_stdout = io.BytesIO()
    writer = _BoundStdoutWriter(captured_stdout)

    writer.write(b'{"jsonrpc":"2.0"}\n')
    await writer.drain()

    assert captured_stdout.getvalue() == b'{"jsonrpc":"2.0"}\n'


@pytest.mark.asyncio
async def test_bound_stdout_writer_retries_partial_writes():
    class _PartialWriter:
        def __init__(self) -> None:
            self.buffer = bytearray()
            self.flushes = 0

        def write(self, data: bytes) -> int:
            chunk = bytes(data[:3])
            self.buffer.extend(chunk)
            return len(chunk)

        def flush(self) -> None:
            self.flushes += 1

    output = _PartialWriter()
    writer = _BoundStdoutWriter(output)
    payload = b'{"jsonrpc":"2.0","result":"complete"}\n'

    writer.write(payload)
    await writer.drain()

    assert output.buffer == payload
    assert output.flushes == 1
