"""ACP lifecycle tests that do not require a live model or external client."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import threading
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from acp import PROTOCOL_VERSION, RequestError, connect_to_agent, run_agent, text_block
from acp.interfaces import Client
from acp.schema import (
    AudioContentBlock,
    BlobResourceContents,
    EmbeddedResourceContentBlock,
    ImageContentBlock,
    TextResourceContents,
)

from connectonion import Agent
from connectonion.cli.co_ai import acp_server
from connectonion.cli.co_ai.acp_server import (
    ConnectOnionACPAgent,
    _BoundNetworkWorkspace,
    _FailClosedACPInput,
    capture_network_workspace,
)
from connectonion.cli.co_ai.acp_transport import (
    _BoundStdoutWriter,
    _StrictNDJSONTransport,
)
from connectonion.cli.co_ai.one_shot_sessions import save_snapshot
from connectonion.core.llm import LLMResponse
from connectonion.core.usage import TokenUsage
from connectonion.useful_plugins.tool_approval import check_approval
from tests.utils.mock_helpers import MockLLM


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
    system_prompt = "system"

    def __init__(self) -> None:
        self.io: Any = None
        self.prompts: list[str] = []
        self.current_session: dict[str, Any] = {"trace": [], "turn": 0}

    def _finish(self, reason: str, usage: dict[str, Any] | None = None) -> None:
        event = {
            "type": "turn_result",
            "turn": self.current_session["turn"],
            "reason": reason,
            "usage": usage,
        }
        self.current_session["trace"].append(event)
        self.io.send(event)

    def input(
        self,
        prompt: str,
        session: dict[str, Any] | None = None,
    ) -> str:
        if session is not None:
            self.current_session = deepcopy(session)
        print("deliberate fake-agent stdout noise")
        self.prompts.append(prompt)
        self.current_session["turn"] += 1
        self._finish("natural")
        return f"answer {len(self.prompts)}: {prompt}"


class _ServedACPAdapter:
    def __init__(self) -> None:
        self.cancelled = False
        self.closed = False

    def cancel_all(self) -> None:
        self.cancelled = True

    async def close_all(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_serve_acp_routes_explicit_state_to_sessions_and_agent(
    tmp_path,
    monkeypatch,
):
    state_dir = (tmp_path / "acp-state").resolve()
    adapter = _ServedACPAdapter()
    captured = {}

    async def fake_open_stdio_transport():
        return object()

    def fake_create_acp_agent(**kwargs):
        captured["adapter_kwargs"] = kwargs
        return adapter

    def fake_create_runtime_agent(**kwargs):
        captured["runtime_kwargs"] = kwargs
        return object()

    async def fake_run_agent(agent, **_kwargs):
        assert agent is adapter
        captured["adapter_kwargs"]["agent_factory"](
            model="test",
            max_iterations=2,
            yolo=False,
            yolo_turns=2,
            resumable=True,
        )

    monkeypatch.setattr(acp_server, "open_stdio_transport", fake_open_stdio_transport)
    monkeypatch.setattr(acp_server, "create_acp_agent", fake_create_acp_agent)
    monkeypatch.setattr(acp_server, "run_agent", fake_run_agent)
    monkeypatch.setattr(
        "connectonion.cli.commands.ai_commands._create_agent",
        fake_create_runtime_agent,
    )

    await acp_server.serve_acp(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        state_dir=state_dir,
    )

    assert captured["adapter_kwargs"]["session_co_dir"] == state_dir
    assert captured["runtime_kwargs"]["state_dir"] == state_dir
    assert adapter.cancelled is True
    assert adapter.closed is True


@pytest.mark.asyncio
async def test_serve_acp_keeps_the_global_default(monkeypatch):
    adapter = _ServedACPAdapter()
    captured = {}

    async def fake_open_stdio_transport():
        return object()

    def fake_create_acp_agent(**kwargs):
        captured.update(kwargs)
        return adapter

    async def fake_run_agent(agent, **_kwargs):
        assert agent is adapter

    monkeypatch.setattr(acp_server, "open_stdio_transport", fake_open_stdio_transport)
    monkeypatch.setattr(acp_server, "create_acp_agent", fake_create_acp_agent)
    monkeypatch.setattr(acp_server, "run_agent", fake_run_agent)

    await acp_server.serve_acp(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
    )

    assert captured["session_co_dir"] is None
    assert captured["agent_factory"] is None


class _BlockingFakeAgent(_FakeAgent):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()

    def input(
        self,
        prompt: str,
        session: dict[str, Any] | None = None,
    ) -> str:
        if session is not None:
            self.current_session = deepcopy(session)
        self.current_session["turn"] += 1
        self.started.set()
        while not self.io.receive_all("INTERRUPT"):
            time.sleep(0.01)
        self._finish("interrupted")
        return f"cancelled: {prompt}"


class _AttachmentRecordingAgent(_FakeAgent):
    def __init__(self) -> None:
        super().__init__()
        self.inputs: list[dict[str, Any]] = []

    def input(
        self,
        prompt: str,
        session: dict[str, Any] | None = None,
        images: list[str] | None = None,
        files: list[dict[str, str]] | None = None,
        _upload_reservation: Any = None,
    ) -> str:
        try:
            self.inputs.append(
                {
                    "prompt": prompt,
                    "images": deepcopy(images),
                    "files": deepcopy(files),
                }
            )
            return super().input(prompt, session=session)
        finally:
            if _upload_reservation is not None:
                _upload_reservation.release()


@pytest.fixture(autouse=True)
def _isolate_acp_session_state(monkeypatch, tmp_path):
    monkeypatch.setattr(acp_server, "GLOBAL_CO_DIR", tmp_path / "acp-state")
    monkeypatch.chdir(tmp_path)


async def _initialize_agent(agent: ConnectOnionACPAgent) -> None:
    await agent.initialize(protocol_version=PROTOCOL_VERSION)


@pytest.mark.asyncio
async def test_acp_requires_initialize_before_creating_session(tmp_path):
    constructed = 0

    def factory(**_kwargs: Any) -> _FakeAgent:
        nonlocal constructed
        constructed += 1
        return _FakeAgent()

    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=factory,
    )

    with pytest.raises(RequestError) as exc_info:
        await acp_agent.new_session(str(tmp_path), mcp_servers=[])

    assert exc_info.value.code == -32600
    assert exc_info.value.data == {"details": "Connection is not initialized"}
    for operation in (
        lambda: acp_agent.resume_session("missing", str(tmp_path), mcp_servers=[]),
        lambda: acp_agent.set_session_mode("missing", ":read-only"),
        lambda: acp_agent.close_session("missing"),
        lambda: acp_agent.prompt("missing", [text_block("hello")]),
    ):
        with pytest.raises(RequestError) as operation_error:
            await operation()
        assert operation_error.value.code == -32600
        assert operation_error.value.data == {
            "details": "Connection is not initialized"
        }
    await acp_agent.cancel("missing")
    assert constructed == 0
    assert acp_agent._sessions == {}
    assert not (tmp_path / "acp-state" / "ai" / "sessions").exists()


@pytest.mark.asyncio
async def test_acp_rejects_repeated_initialize_without_resetting_connection(tmp_path):
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _FakeAgent(),
    )

    initialized = await acp_agent.initialize(protocol_version=PROTOCOL_VERSION)
    with pytest.raises(RequestError) as exc_info:
        await acp_agent.initialize(protocol_version=PROTOCOL_VERSION)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])

    assert initialized.protocol_version == PROTOCOL_VERSION
    assert exc_info.value.code == -32600
    assert exc_info.value.data == {"details": "Connection is already initialized"}
    assert session.session_id in acp_agent._sessions


@pytest.mark.asyncio
async def test_acp_session_conflicts_never_emit_auth_required(tmp_path):
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _FakeAgent(),
    )
    await _initialize_agent(acp_agent)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])

    with pytest.raises(RequestError) as already_open:
        await acp_agent.resume_session(
            session.session_id,
            str(tmp_path),
            mcp_servers=[],
        )

    runtime = acp_agent._sessions[session.session_id]
    async with runtime.prompt_lock:
        operations = (
            lambda: acp_agent.set_session_mode(session.session_id, ":read-only"),
            lambda: acp_agent.prompt(session.session_id, [text_block("hello")]),
        )
        conflict_errors = []
        for operation in operations:
            with pytest.raises(RequestError) as conflict:
                await operation()
            conflict_errors.append(conflict.value)

    for error in (already_open.value, *conflict_errors):
        assert error.code == acp_server.ACP_SESSION_CONFLICT_ERROR_CODE == -32001
        assert error.data == {"sessionId": session.session_id}
    assert str(already_open.value) == "Session is already open"
    assert {str(error) for error in conflict_errors} == {"Session is busy"}


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
    older_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _FakeAgent(),
    )
    newer_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _FakeAgent(),
    )

    older = await older_agent.initialize(protocol_version=0)
    newer = await newer_agent.initialize(protocol_version=PROTOCOL_VERSION + 1)

    assert older.protocol_version == PROTOCOL_VERSION
    assert newer.protocol_version == PROTOCOL_VERSION
    assert newer.agent_capabilities.prompt_capabilities.image is True
    assert newer.agent_capabilities.prompt_capabilities.embedded_context is True
    assert newer.agent_capabilities.prompt_capabilities.audio is False


@pytest.mark.asyncio
async def test_acp_passes_official_image_and_embedded_file_blocks_to_agent(tmp_path):
    fake_agent = _AttachmentRecordingAgent()
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: fake_agent,
        input_limits={"max_file_size": 1, "max_files_per_request": 3},
    )
    acp_agent.on_connect(_RecordingClient())
    await _initialize_agent(acp_agent)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])

    response = await acp_agent.prompt(
        session.session_id,
        [
            ImageContentBlock(
                type="image",
                data=base64.b64encode(b"image-bytes").decode("ascii"),
                mime_type="image/png",
            ),
            EmbeddedResourceContentBlock(
                type="resource",
                resource=TextResourceContents(
                    uri="connectonion-upload:/notes%20one.txt",
                    mime_type="text/plain",
                    text="hello",
                ),
            ),
            EmbeddedResourceContentBlock(
                type="resource",
                resource=BlobResourceContents(
                    uri="connectonion-upload:/report.bin",
                    mime_type="application/octet-stream",
                    blob=base64.b64encode(b"binary").decode("ascii"),
                ),
            ),
            text_block("inspect these"),
        ],
    )

    assert response.stop_reason == "end_turn"
    assert fake_agent.inputs == [
        {
            "prompt": "inspect these",
            "images": [
                "data:image/png;base64,"
                + base64.b64encode(b"image-bytes").decode("ascii")
            ],
            "files": [
                {
                    "name": "notes one.txt",
                    "data": "data:text/plain;base64,"
                    + base64.b64encode(b"hello").decode("ascii"),
                },
                {
                    "name": "report.bin",
                    "data": "data:application/octet-stream;base64,"
                    + base64.b64encode(b"binary").decode("ascii"),
                },
            ],
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "block",
    [
        ImageContentBlock(type="image", data="%%%", mime_type="image/png"),
        ImageContentBlock(
            type="image",
            data=base64.b64encode(b"image").decode("ascii"),
            mime_type="image/svg+xml",
        ),
        AudioContentBlock(
            type="audio",
            data=base64.b64encode(b"audio").decode("ascii"),
            mime_type="audio/wav",
        ),
        EmbeddedResourceContentBlock(
            type="resource",
            resource=BlobResourceContents(
                uri="file:///private/secret.txt",
                blob=base64.b64encode(b"secret").decode("ascii"),
            ),
        ),
        EmbeddedResourceContentBlock(
            type="resource",
            resource=BlobResourceContents(
                uri="connectonion-upload:/..%2Fsecret.txt",
                blob=base64.b64encode(b"secret").decode("ascii"),
            ),
        ),
        EmbeddedResourceContentBlock(
            type="resource",
            resource=BlobResourceContents(
                uri="connectonion-upload:/CON.txt",
                blob=base64.b64encode(b"device").decode("ascii"),
            ),
        ),
        EmbeddedResourceContentBlock(
            type="resource",
            resource=BlobResourceContents(
                uri="connectonion-upload:/trailing.",
                blob=base64.b64encode(b"ambiguous").decode("ascii"),
            ),
        ),
        EmbeddedResourceContentBlock(
            type="resource",
            resource=BlobResourceContents(
                uri="connectonion-upload:/bad%3Aname.txt",
                blob=base64.b64encode(b"colon").decode("ascii"),
            ),
        ),
    ],
)
async def test_acp_rejects_unsafe_attachment_blocks_before_turn_mutation(
    tmp_path,
    block,
):
    fake_agent = _AttachmentRecordingAgent()
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: fake_agent,
    )
    await _initialize_agent(acp_agent)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    runtime = acp_agent._sessions[session.session_id]
    before = deepcopy(runtime.last_good_session)

    with pytest.raises(RequestError, match="Invalid params"):
        await acp_agent.prompt(session.session_id, [block])

    assert fake_agent.inputs == []
    assert runtime.last_good_session == before


@pytest.mark.asyncio
async def test_acp_rejects_oversized_or_excess_attachments_before_turn(tmp_path):
    fake_agent = _AttachmentRecordingAgent()
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: fake_agent,
        input_limits={
            "max_file_size": 1 / (1024 * 1024),
            "max_files_per_request": 1,
        },
    )
    await _initialize_agent(acp_agent)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    image = ImageContentBlock(
        type="image",
        data=base64.b64encode(b"xx").decode("ascii"),
        mime_type="image/png",
    )

    with pytest.raises(RequestError, match="Invalid params"):
        await acp_agent.prompt(session.session_id, [image])

    one_byte = ImageContentBlock(
        type="image",
        data=base64.b64encode(b"x").decode("ascii"),
        mime_type="image/png",
    )
    with pytest.raises(RequestError, match="Invalid params"):
        await acp_agent.prompt(session.session_id, [one_byte, one_byte])

    assert fake_agent.inputs == []


@pytest.mark.parametrize("size", [0, -1, float("nan"), float("inf"), True])
def test_acp_rejects_invalid_attachment_limits(size):
    with pytest.raises(ValueError, match="positive numbers"):
        ConnectOnionACPAgent(
            model="test",
            max_iterations=2,
            yolo=False,
            yolo_turns=2,
            agent_factory=lambda **_kwargs: _FakeAgent(),
            input_limits={"max_file_size": size},
        )


@pytest.mark.parametrize("size", [1e-308, 1e308])
def test_acp_rejects_attachment_size_limits_outside_byte_range(size):
    with pytest.raises(ValueError, match="at least one byte"):
        ConnectOnionACPAgent(
            model="test",
            max_iterations=2,
            yolo=False,
            yolo_turns=2,
            agent_factory=lambda **_kwargs: _FakeAgent(),
            input_limits={"max_file_size": size},
        )


@pytest.mark.parametrize("count", [0, -1, 1.5, True])
def test_acp_rejects_invalid_attachment_count_limits(count):
    with pytest.raises(ValueError, match="positive numbers"):
        ConnectOnionACPAgent(
            model="test",
            max_iterations=2,
            yolo=False,
            yolo_turns=2,
            agent_factory=lambda **_kwargs: _FakeAgent(),
            input_limits={"max_files_per_request": count},
        )


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("max_acp_upload_storage", 0, "positive numbers"),
        ("max_acp_upload_storage", 1e-308, "at least one byte"),
        ("max_acp_upload_storage", 1e308, "at least one byte"),
        ("max_acp_upload_files", 0, "positive numbers"),
        ("max_acp_upload_files", 1.5, "positive numbers"),
        ("max_acp_sessions", 0, "positive numbers"),
        ("max_acp_sessions", 1.5, "positive numbers"),
        ("max_acp_session_storage", 0, "positive numbers"),
        ("max_acp_session_storage", 1e-308, "at least one byte"),
        ("max_acp_session_storage", 1e308, "at least one byte"),
        ("max_acp_snapshot_size", 0, "positive numbers"),
        ("max_acp_snapshot_size", 1e-308, "at least one byte"),
        ("max_acp_snapshot_size", 1e308, "at least one byte"),
    ],
)
def test_acp_rejects_invalid_principal_storage_limits(key, value, message):
    with pytest.raises(ValueError, match=message):
        ConnectOnionACPAgent(
            model="test",
            max_iterations=2,
            yolo=False,
            yolo_turns=2,
            agent_factory=lambda **_kwargs: _FakeAgent(),
            input_limits={key: value},
        )


def test_acp_rejects_single_snapshot_limit_above_total_storage():
    with pytest.raises(ValueError, match="consistent"):
        ConnectOnionACPAgent(
            model="test",
            max_iterations=2,
            yolo=False,
            yolo_turns=2,
            agent_factory=lambda **_kwargs: _FakeAgent(),
            input_limits={
                "max_acp_session_storage": 1,
                "max_acp_snapshot_size": 2,
            },
        )


@pytest.mark.asyncio
async def test_acp_real_agent_uses_existing_image_and_safe_file_path(tmp_path):
    llm = MockLLM(
        responses=[
            LLMResponse(
                content="received",
                tool_calls=[],
                raw_response={},
                usage=TokenUsage(),
            )
        ]
    )
    real_agent = Agent(
        name="attachments",
        llm=llm,
        quiet=True,
        log=False,
        co_dir=tmp_path / ".co",
    )
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: real_agent,
    )
    acp_agent.on_connect(_RecordingClient())
    await _initialize_agent(acp_agent)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])

    response = await acp_agent.prompt(
        session.session_id,
        [
            text_block("inspect"),
            ImageContentBlock(
                type="image",
                data=base64.b64encode(b"image").decode("ascii"),
                mime_type="image/png",
            ),
            EmbeddedResourceContentBlock(
                type="resource",
                resource=BlobResourceContents(
                    uri="connectonion-upload:/..%252Fstill-one-name.txt",
                    mime_type="text/plain",
                    blob=base64.b64encode(b"file body").decode("ascii"),
                ),
            ),
        ],
    )

    assert response.stop_reason == "end_turn"
    saved = list((tmp_path / ".co" / "uploads").iterdir())
    assert len(saved) == 1
    assert saved[0].name.endswith("_..%2Fstill-one-name.txt")
    assert saved[0].read_bytes() == b"file body"
    user = next(
        message
        for message in llm.last_call["messages"]
        if message["role"] == "user" and not message.get("internal")
    )
    assert user["content"] == [
        {"type": "text", "text": "inspect"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,aW1hZ2U="},
        },
    ]


@pytest.mark.asyncio
async def test_network_acp_stages_files_in_the_authenticated_principal_namespace(
    tmp_path,
):
    llm = MockLLM(
        responses=[
            LLMResponse(
                content="received",
                tool_calls=[],
                raw_response={},
                usage=TokenUsage(),
            )
        ]
    )
    global_co_dir = tmp_path / "global-co"
    principal_co_dir = global_co_dir / "acp-principals" / "principal-a"
    real_agent = Agent(
        name="attachments",
        llm=llm,
        quiet=True,
        log=False,
        co_dir=global_co_dir,
    )
    workspace = capture_network_workspace(tmp_path)
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: real_agent,
        session_co_dir=principal_co_dir,
        network_workspace=workspace,
    )
    acp_agent.on_connect(_RecordingClient())
    await _initialize_agent(acp_agent)
    try:
        session = await acp_agent.new_session("/", mcp_servers=[])

        response = await acp_agent.prompt(
            session.session_id,
            [
                EmbeddedResourceContentBlock(
                    type="resource",
                    resource=BlobResourceContents(
                        uri="connectonion-upload:/private.txt",
                        mime_type="text/plain",
                        blob=base64.b64encode(b"principal private").decode("ascii"),
                    ),
                )
            ],
        )

        assert response.stop_reason == "end_turn"
        saved = list((principal_co_dir / "uploads").glob("*_private.txt"))
        assert len(saved) == 1
        assert saved[0].read_bytes() == b"principal private"
        assert (principal_co_dir / "uploads").stat().st_mode & 0o777 == 0o700
        assert not (global_co_dir / "uploads").exists()
    finally:
        workspace.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "limits",
    [
        {
            "max_acp_upload_storage": 2 / (1024 * 1024),
            "max_acp_upload_files": 10,
        },
        {
            "max_acp_upload_storage": 10,
            "max_acp_upload_files": 2,
        },
    ],
    ids=["bytes", "files"],
)
async def test_network_acp_rejects_sequential_prompts_at_principal_storage_quota(
    tmp_path,
    limits,
):
    llm = MockLLM(
        responses=[
            LLMResponse(
                content="received",
                tool_calls=[],
                raw_response={},
                usage=TokenUsage(),
            )
            for _ in range(2)
        ]
    )
    principal_co_dir = tmp_path / "principal"
    real_agent = Agent(
        name="attachments",
        llm=llm,
        quiet=True,
        log=False,
        co_dir=tmp_path / "global-co",
    )
    workspace = capture_network_workspace(tmp_path)
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: real_agent,
        session_co_dir=principal_co_dir,
        network_workspace=workspace,
        input_limits=limits,
    )
    acp_agent.on_connect(_RecordingClient())
    await _initialize_agent(acp_agent)
    try:
        session = await acp_agent.new_session("/", mcp_servers=[])

        for index in range(2):
            response = await acp_agent.prompt(
                session.session_id,
                [
                    EmbeddedResourceContentBlock(
                        type="resource",
                        resource=BlobResourceContents(
                            uri=f"connectonion-upload:/file-{index}.txt",
                            mime_type="text/plain",
                            blob=base64.b64encode(b"x").decode("ascii"),
                        ),
                    )
                ],
            )
            assert response.stop_reason == "end_turn"

        before = list((principal_co_dir / "uploads").iterdir())
        with pytest.raises(RequestError, match="Invalid params"):
            await acp_agent.prompt(
                session.session_id,
                [
                    EmbeddedResourceContentBlock(
                        type="resource",
                        resource=BlobResourceContents(
                            uri="connectonion-upload:/over-quota.txt",
                            mime_type="text/plain",
                            blob=base64.b64encode(b"x").decode("ascii"),
                        ),
                    )
                ],
            )

        assert list((principal_co_dir / "uploads").iterdir()) == before
        assert len(llm.calls) == 2
    finally:
        workspace.close()


@pytest.mark.asyncio
async def test_network_acp_releases_upload_quota_before_model_work(tmp_path):
    model_started = threading.Event()
    allow_model_to_finish = threading.Event()

    def wait_in_model(_messages, _tools):
        model_started.set()
        assert allow_model_to_finish.wait(timeout=1)
        return LLMResponse(
            content="received",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )

    principal_co_dir = tmp_path / "principal"
    workspace = capture_network_workspace(tmp_path)
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: Agent(
            name="attachments",
            llm=MockLLM(on_complete=wait_in_model),
            quiet=True,
            log=False,
            co_dir=tmp_path / "global-co",
        ),
        session_co_dir=principal_co_dir,
        network_workspace=workspace,
    )
    acp_agent.on_connect(_RecordingClient())
    await _initialize_agent(acp_agent)
    try:
        session = await acp_agent.new_session("/", mcp_servers=[])
        prompt = acp_agent.prompt(
            session.session_id,
            [
                EmbeddedResourceContentBlock(
                    type="resource",
                    resource=BlobResourceContents(
                        uri="connectonion-upload:/one.txt",
                        blob=base64.b64encode(b"x").decode("ascii"),
                    ),
                )
            ],
        )
        prompt_task = asyncio.create_task(prompt)
        assert await asyncio.to_thread(model_started.wait, 1)

        parsed = acp_agent._parse_prompt(
            [
                EmbeddedResourceContentBlock(
                    type="resource",
                    resource=BlobResourceContents(
                        uri="connectonion-upload:/two.txt",
                        blob=base64.b64encode(b"y").decode("ascii"),
                    ),
                )
            ]
        )
        reservation = await asyncio.wait_for(
            asyncio.to_thread(acp_agent._reserve_network_uploads, parsed),
            timeout=0.5,
        )
        assert reservation is not None
        reservation.release()
        allow_model_to_finish.set()
        assert (await prompt_task).stop_reason == "end_turn"
    finally:
        allow_model_to_finish.set()
        workspace.close()


def test_network_acp_upload_reservations_are_shared_across_connections(tmp_path):
    workspace = capture_network_workspace(tmp_path)
    limits = {
        "max_acp_upload_storage": 1 / (1024 * 1024),
        "max_acp_upload_files": 1,
    }
    kwargs = {
        "model": "test",
        "max_iterations": 2,
        "yolo": False,
        "yolo_turns": 2,
        "agent_factory": lambda **_kwargs: _FakeAgent(),
        "session_co_dir": tmp_path / "principal",
        "network_workspace": workspace,
        "input_limits": limits,
    }
    first = ConnectOnionACPAgent(**kwargs)
    second = ConnectOnionACPAgent(**kwargs)
    prompt = first._parse_prompt(
        [
            EmbeddedResourceContentBlock(
                type="resource",
                resource=BlobResourceContents(
                    uri="connectonion-upload:/one.txt",
                    blob=base64.b64encode(b"x").decode("ascii"),
                ),
            )
        ]
    )
    (tmp_path / "principal" / "uploads").mkdir(parents=True)

    reservation = first._reserve_network_uploads(prompt)
    result: list[object] = []

    def reserve_second_connection():
        try:
            result.append(second._reserve_network_uploads(prompt))
        except BaseException as exc:
            result.append(exc)

    contender = threading.Thread(target=reserve_second_connection)
    contender.start()
    try:
        time.sleep(0.05)
        assert result == []
        (tmp_path / "principal" / "uploads" / "committed.txt").write_bytes(b"x")
    finally:
        assert reservation is not None
        reservation.release()
        contender.join(timeout=1)
        workspace.close()

    assert len(result) == 1
    assert isinstance(result[0], RequestError)


def test_network_acp_quota_scan_ignores_a_concurrently_rolled_back_file(
    tmp_path,
    monkeypatch,
):
    workspace = capture_network_workspace(tmp_path)
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _FakeAgent(),
        session_co_dir=tmp_path / "principal",
        network_workspace=workspace,
    )
    prompt = acp_agent._parse_prompt(
        [
            EmbeddedResourceContentBlock(
                type="resource",
                resource=BlobResourceContents(
                    uri="connectonion-upload:/new.txt",
                    blob=base64.b64encode(b"x").decode("ascii"),
                ),
            )
        ]
    )
    upload_dir = tmp_path / "principal" / "uploads"
    upload_dir.mkdir(parents=True)
    rolled_back = upload_dir / "old.txt"
    rolled_back.write_bytes(b"old")
    original_scandir = os.scandir

    class StaleEntry:
        def stat(self, *, follow_symlinks):
            assert follow_symlinks is False
            rolled_back.unlink()
            raise FileNotFoundError

    monkeypatch.setattr(
        os,
        "scandir",
        lambda path: [StaleEntry()] if Path(path) == upload_dir else original_scandir(path),
    )
    try:
        reservation = acp_agent._reserve_network_uploads(prompt)
        assert reservation is not None
        reservation.release()
    finally:
        workspace.close()


def test_network_acp_upload_quota_rejects_unexpected_entries(tmp_path):
    workspace = capture_network_workspace(tmp_path)
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _FakeAgent(),
        session_co_dir=tmp_path / "principal",
        network_workspace=workspace,
    )
    prompt = acp_agent._parse_prompt(
        [
            EmbeddedResourceContentBlock(
                type="resource",
                resource=BlobResourceContents(
                    uri="connectonion-upload:/one.txt",
                    blob=base64.b64encode(b"x").decode("ascii"),
                ),
            )
        ]
    )
    upload_dir = tmp_path / "principal" / "uploads"
    upload_dir.mkdir(parents=True)
    (upload_dir / "unexpected").mkdir()
    try:
        with pytest.raises(RequestError, match="Internal error"):
            acp_agent._reserve_network_uploads(prompt)
    finally:
        workspace.close()


@pytest.mark.asyncio
async def test_acp_failed_real_agent_removes_new_upload_before_snapshot_restore(tmp_path):
    class FailingLLM:
        model = "failing"

        def complete(self, *_args, **_kwargs):
            raise RuntimeError("provider failed")

    real_agent = Agent(
        name="attachments",
        llm=FailingLLM(),
        quiet=True,
        log=False,
        co_dir=tmp_path / ".co",
    )
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: real_agent,
    )
    acp_agent.on_connect(_RecordingClient())
    await _initialize_agent(acp_agent)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    runtime = acp_agent._sessions[session.session_id]
    before = deepcopy(runtime.last_good_session)

    with pytest.raises(RequestError, match="co ai prompt failed"):
        await acp_agent.prompt(
            session.session_id,
            [
                EmbeddedResourceContentBlock(
                    type="resource",
                    resource=BlobResourceContents(
                        uri="connectonion-upload:/remove-me.txt",
                        mime_type="text/plain",
                        blob=base64.b64encode(b"temporary").decode("ascii"),
                    ),
                )
            ],
        )

    assert list((tmp_path / ".co" / "uploads").glob("*_remove-me.txt")) == []
    assert runtime.last_good_session == before
    assert real_agent.current_session == before


@pytest.mark.asyncio
async def test_acp_rejects_unknown_session():
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _FakeAgent(),
    )

    await _initialize_agent(acp_agent)
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
    acp_agent.on_connect(_RecordingClient())
    await _initialize_agent(acp_agent)
    session = await acp_agent.new_session(str(tmp_path), mcp_servers=[])
    prompt_task = asyncio.create_task(
        acp_agent.prompt(session.session_id, [text_block("wait")])
    )
    await asyncio.wait_for(asyncio.to_thread(fake_agent.started.wait), timeout=1)

    await acp_agent.cancel(session.session_id)
    response = await asyncio.wait_for(prompt_task, timeout=1)

    assert response.stop_reason == "cancelled"


@pytest.mark.asyncio
async def test_acp_cancel_while_waiting_for_upload_quota_never_starts_agent(tmp_path):
    workspace = capture_network_workspace(tmp_path)
    principal_co_dir = tmp_path / "principal"
    recording_agent = _AttachmentRecordingAgent()
    kwargs = {
        "model": "test",
        "max_iterations": 2,
        "yolo": False,
        "yolo_turns": 2,
        "session_co_dir": principal_co_dir,
        "network_workspace": workspace,
    }
    holder = ConnectOnionACPAgent(
        agent_factory=lambda **_kwargs: _FakeAgent(),
        **kwargs,
    )
    contender = ConnectOnionACPAgent(
        agent_factory=lambda **_kwargs: recording_agent,
        **kwargs,
    )
    contender.on_connect(_RecordingClient())
    await _initialize_agent(contender)
    (principal_co_dir / "uploads").mkdir(parents=True)
    parsed = holder._parse_prompt(
        [
            EmbeddedResourceContentBlock(
                type="resource",
                resource=BlobResourceContents(
                    uri="connectonion-upload:/hold.txt",
                    blob=base64.b64encode(b"x").decode("ascii"),
                ),
            )
        ]
    )
    reservation = holder._reserve_network_uploads(parsed)
    assert reservation is not None
    try:
        session = await contender.new_session("/", mcp_servers=[])
        prompt_task = asyncio.create_task(
            contender.prompt(
                session.session_id,
                [
                    EmbeddedResourceContentBlock(
                        type="resource",
                        resource=BlobResourceContents(
                            uri="connectonion-upload:/cancelled.txt",
                            blob=base64.b64encode(b"y").decode("ascii"),
                        ),
                    )
                ],
            )
        )
        runtime = contender._sessions[session.session_id]
        await asyncio.wait_for(
            asyncio.to_thread(runtime.prompt_active.wait),
            timeout=1,
        )
        await contender.cancel(session.session_id)
        reservation.release()

        response = await asyncio.wait_for(prompt_task, timeout=1)
        assert response.stop_reason == "cancelled"
        assert recording_agent.inputs == []
        assert list((principal_co_dir / "uploads").iterdir()) == []
    finally:
        reservation.release()
        workspace.close()


@pytest.mark.asyncio
async def test_acp_close_while_waiting_for_upload_quota_never_starts_agent(tmp_path):
    workspace = capture_network_workspace(tmp_path)
    principal_co_dir = tmp_path / "principal"
    recording_agent = _AttachmentRecordingAgent()
    kwargs = {
        "model": "test",
        "max_iterations": 2,
        "yolo": False,
        "yolo_turns": 2,
        "session_co_dir": principal_co_dir,
        "network_workspace": workspace,
    }
    holder = ConnectOnionACPAgent(
        agent_factory=lambda **_kwargs: _FakeAgent(),
        **kwargs,
    )
    contender = ConnectOnionACPAgent(
        agent_factory=lambda **_kwargs: recording_agent,
        **kwargs,
    )
    contender.on_connect(_RecordingClient())
    await _initialize_agent(contender)
    (principal_co_dir / "uploads").mkdir(parents=True)
    parsed = holder._parse_prompt(
        [
            EmbeddedResourceContentBlock(
                type="resource",
                resource=BlobResourceContents(
                    uri="connectonion-upload:/hold.txt",
                    blob=base64.b64encode(b"x").decode("ascii"),
                ),
            )
        ]
    )
    reservation = holder._reserve_network_uploads(parsed)
    assert reservation is not None
    try:
        session = await contender.new_session("/", mcp_servers=[])
        prompt_task = asyncio.create_task(
            contender.prompt(
                session.session_id,
                [
                    EmbeddedResourceContentBlock(
                        type="resource",
                        resource=BlobResourceContents(
                            uri="connectonion-upload:/closed.txt",
                            blob=base64.b64encode(b"y").decode("ascii"),
                        ),
                    )
                ],
            )
        )
        runtime = contender._sessions[session.session_id]
        await asyncio.wait_for(
            asyncio.to_thread(runtime.prompt_active.wait),
            timeout=1,
        )
        close_task = asyncio.create_task(contender.close_session(session.session_id))
        await asyncio.sleep(0)
        reservation.release()

        response = await asyncio.wait_for(prompt_task, timeout=1)
        await asyncio.wait_for(close_task, timeout=1)
        assert response.stop_reason == "cancelled"
        assert recording_agent.inputs == []
        assert session.session_id not in contender._sessions
    finally:
        reservation.release()
        workspace.close()


def test_acp_approval_input_denies_sensitive_tools_unless_mode_is_explicit_full_access():
    acp_input = _FailClosedACPInput()
    session = {
        "mode": "default",
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

    # A mode label alone is not authority.  Full access is valid only when the
    # bounded grant written by the ACP mode transaction is complete.
    session["mode"] = ":danger-full-access"
    with pytest.raises(ValueError, match="Connection closed"):
        check_approval(agent)

    session.update({
        "full_access_turns": 20,
        "full_access_turns_used": 0,
        "skip_tool_approval": True,
    })
    check_approval(agent)


@pytest.mark.asyncio
async def test_acp_errors_do_not_echo_agent_exception_details(tmp_path):
    class _FailingAgent(_FakeAgent):
        def input(
            self,
            prompt: str,
            session: dict[str, Any] | None = None,
        ) -> str:
            if session is not None:
                self.current_session = deepcopy(session)
            self.current_session["turn"] += 1
            self._finish("error")
            raise RuntimeError(f"secret-marker in {prompt}")

    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _FailingAgent(),
    )
    await _initialize_agent(acp_agent)
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

    await _initialize_agent(acp_agent)
    with pytest.raises(RequestError, match="Invalid params"):
        await acp_agent.new_session(
            str(tmp_path),
            additional_directories=[str(tmp_path / "extra")],
        )
    with pytest.raises(RequestError, match="Invalid params"):
        await acp_agent.new_session(str(tmp_path), mcp_servers=[object()])
    with pytest.raises(RequestError, match="Invalid params"):
        await acp_agent.new_session("relative/path")


@pytest.mark.asyncio
async def test_network_acp_maps_only_virtual_root_to_host_workspace(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    constructed_in: list[Path] = []

    def factory(**_kwargs: Any) -> _FakeAgent:
        constructed_in.append(Path.cwd())
        return _FakeAgent()

    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=factory,
        network_workspace=capture_network_workspace(workspace),
    )

    await _initialize_agent(acp_agent)
    session = await acp_agent.new_session(
        "/",
        mcp_servers=[],
        _meta={"cwd": "/tmp", "additionalDirectories": ["/private"]},
    )

    assert constructed_in == [workspace.resolve()]
    assert acp_agent._sessions[session.session_id].cwd == workspace.resolve()


@pytest.mark.asyncio
async def test_network_acp_rejects_host_paths_before_agent_construction(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    constructed = 0

    def factory(**_kwargs: Any) -> _FakeAgent:
        nonlocal constructed
        constructed += 1
        return _FakeAgent()

    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=factory,
        network_workspace=capture_network_workspace(workspace),
    )

    await _initialize_agent(acp_agent)
    for cwd in (str(workspace), "/./", "/tmp"):
        with pytest.raises(RequestError, match="Invalid params") as exc_info:
            await acp_agent.new_session(cwd, mcp_servers=[])
        assert str(workspace) not in str(exc_info.value)
        with pytest.raises(RequestError, match="Invalid params"):
            await acp_agent.resume_session("copied-session", cwd, mcp_servers=[])

    with pytest.raises(RequestError, match="Invalid params"):
        await acp_agent.new_session(
            "/",
            additional_directories=[str(tmp_path / "other")],
        )

    assert constructed == 0


@pytest.mark.asyncio
async def test_network_acp_resume_does_not_disclose_saved_host_workspace(tmp_path):
    old_workspace = tmp_path / "old-private-project"
    new_workspace = tmp_path / "new-private-project"
    old_workspace.mkdir()
    new_workspace.mkdir()
    session_id = "40c0397c-972b-4133-899b-5ab4cc5c4883"
    session = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 0,
        "mode": ":read-only",
        "plan": [],
    }
    save_snapshot(
        tmp_path / "network-state",
        session,
        {},
        cwd=old_workspace,
    )
    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=lambda **_kwargs: _FakeAgent(),
        session_co_dir=tmp_path / "network-state",
        network_workspace=capture_network_workspace(new_workspace),
    )

    await _initialize_agent(acp_agent)
    with pytest.raises(RequestError, match="Internal error") as exc_info:
        await acp_agent.resume_session(session_id, "/", mcp_servers=[])

    assert exc_info.value.code == -32603
    assert exc_info.value.data == {"details": "Unable to restore session state"}
    error = str(exc_info.value)
    assert str(old_workspace) not in error
    assert str(new_workspace) not in error


@pytest.mark.asyncio
async def test_network_acp_workspace_does_not_follow_replaced_launch_path(tmp_path):
    launch_path = tmp_path / "project"
    moved_path = tmp_path / "moved-project"
    replacement = tmp_path / "replacement"
    launch_path.mkdir()
    replacement.mkdir()
    (launch_path / "workspace-marker").write_text("original", encoding="utf-8")
    (replacement / "workspace-marker").write_text("replacement", encoding="utf-8")
    workspace = capture_network_workspace(launch_path)
    launch_path.rename(moved_path)
    if os.name == "nt":
        launch_path.mkdir()
    else:
        launch_path.symlink_to(replacement, target_is_directory=True)
    observed: list[str] = []

    def factory(**_kwargs: Any) -> _FakeAgent:
        observed.append(Path("workspace-marker").read_text(encoding="utf-8"))
        return _FakeAgent()

    acp_agent = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=factory,
        network_workspace=workspace,
    )

    await _initialize_agent(acp_agent)
    if hasattr(os, "fchdir"):
        await acp_agent.new_session("/", mcp_servers=[])
        assert observed == ["original"]
    else:
        with pytest.raises(RequestError, match="Unable to create"):
            await acp_agent.new_session("/", mcp_servers=[])
        assert observed == []


@pytest.mark.asyncio
async def test_acp_adapters_share_one_process_context_lock(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first_started = threading.Event()
    release_first = threading.Event()
    observed: list[tuple[str, Path]] = []

    def first_factory(**_kwargs: Any) -> _FakeAgent:
        observed.append(("first-start", Path.cwd()))
        first_started.set()
        assert release_first.wait(timeout=1)
        observed.append(("first-end", Path.cwd()))
        return _FakeAgent()

    def second_factory(**_kwargs: Any) -> _FakeAgent:
        observed.append(("second", Path.cwd()))
        return _FakeAgent()

    first = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=first_factory,
    )
    second = ConnectOnionACPAgent(
        model="test",
        max_iterations=2,
        yolo=False,
        yolo_turns=2,
        agent_factory=second_factory,
    )

    await _initialize_agent(first)
    await _initialize_agent(second)
    first_task = asyncio.create_task(first.new_session(str(first_dir), mcp_servers=[]))
    await asyncio.wait_for(asyncio.to_thread(first_started.wait), timeout=1)
    second_task = asyncio.create_task(second.new_session(str(second_dir), mcp_servers=[]))
    await asyncio.sleep(0.05)
    assert observed == [("first-start", first_dir.resolve())]
    release_first.set()
    await asyncio.gather(first_task, second_task)

    assert observed == [
        ("first-start", first_dir.resolve()),
        ("first-end", first_dir.resolve()),
        ("second", second_dir.resolve()),
    ]


def test_network_acp_rejects_filesystem_without_stable_directory_identity():
    class UnstableDirectory:
        def stat(self):
            return SimpleNamespace(st_dev=1, st_ino=0)

    with pytest.raises(RuntimeError, match="stable workspace identity"):
        _BoundNetworkWorkspace(UnstableDirectory(), None)  # type: ignore[arg-type]


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


@pytest.mark.parametrize(
    "message",
    [
        {"jsonrpc": "2.0", "id": None, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": None, "result": {}},
        {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32603, "message": "failed"},
        },
        {"jsonrpc": "2.0", "id": True, "result": {}},
        {"jsonrpc": "2.0", "id": 1.5, "result": {}},
    ],
)
def test_strict_ndjson_rejects_unsupported_correlation_ids(message):
    assert _StrictNDJSONTransport._is_json_rpc_message(message) is False


@pytest.mark.parametrize(
    "message",
    [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "session/set_mode",
            "params": {},
            "result": {},
        },
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "session/set_mode",
            "params": {},
            "error": {"code": -32603, "message": "failed"},
        },
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "session/set_mode",
            "result": {},
        },
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {},
            "params": {},
        },
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "session/set_mode",
            "params": None,
        },
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "session/set_mode",
            "params": {},
            "extra": True,
        },
    ],
)
def test_strict_ndjson_rejects_mixed_request_and_response_envelopes(message):
    assert _StrictNDJSONTransport._is_json_rpc_message(message) is False


@pytest.mark.parametrize(
    "message",
    [
        {"jsonrpc": "2.0", "id": "request-1", "method": "initialize"},
        {"jsonrpc": "2.0", "id": 1, "result": {}},
        {
            "jsonrpc": "2.0",
            "id": "request-1",
            "error": {"code": -32603, "message": "failed"},
        },
        {"jsonrpc": "2.0", "method": "session/cancel", "params": {}},
    ],
)
def test_strict_ndjson_keeps_supported_ids_and_notifications(message):
    assert _StrictNDJSONTransport._is_json_rpc_message(message) is True


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
