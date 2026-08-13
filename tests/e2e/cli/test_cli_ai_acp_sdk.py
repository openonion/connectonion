"""Official ACP client SDK conformance checks for ``co ai --acp``."""

from __future__ import annotations

import asyncio
import base64
import os
import sys
from asyncio.subprocess import Process
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import acp
import pytest
from acp.schema import (
    AgentMessageChunk,
    BlobResourceContents,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    ImageContentBlock,
    Implementation,
    PermissionOption,
    RequestPermissionResponse,
    ToolCallUpdate,
)


class _ConformanceClient:
    def __init__(self) -> None:
        self.updates: list[tuple[str, Any]] = []
        self.permission_requests: list[
            tuple[str, ToolCallUpdate, list[PermissionOption]]
        ] = []

    async def session_update(
        self,
        session_id: str,
        update: Any,
        **_kwargs: Any,
    ) -> None:
        self.updates.append((session_id, update))

    async def request_permission(
        self,
        session_id: str,
        tool_call: ToolCallUpdate,
        options: list[PermissionOption],
        **_kwargs: Any,
    ) -> RequestPermissionResponse:
        self.permission_requests.append((session_id, tool_call, options))
        return RequestPermissionResponse.model_validate({
            "outcome": {
                "outcome": "selected",
                "optionId": "reject_once",
            }
        })


def _agent_environment(state_root: Path) -> dict[str, str]:
    repo_root = Path(__file__).resolve().parents[3]
    acp_site_packages = Path(acp.__file__).resolve().parents[1]
    return {
        "HOME": str(state_root),
        "USERPROFILE": str(state_root),
        "APPDATA": str(state_root / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(state_root / "AppData" / "Local"),
        "PYTHONPATH": os.pathsep.join((str(repo_root), str(acp_site_packages))),
    }


async def _drain_stderr(
    reader: asyncio.StreamReader,
    captured: bytearray,
) -> None:
    """Drain child diagnostics continuously while retaining at most 64 KiB."""

    while chunk := await reader.read(8192):
        remaining = 64 * 1024 - len(captured)
        if remaining > 0:
            captured.extend(chunk[:remaining])


@asynccontextmanager
async def _sdk_agent(
    client: _ConformanceClient,
    tmp_path: Path,
) -> AsyncIterator[tuple[Any, Process]]:
    fixture = Path(__file__).with_name("acp_test_agent.py")
    captured = bytearray()
    stderr_task: asyncio.Task[None] | None = None
    process: Process | None = None
    failed = False
    try:
        async with acp.spawn_agent_process(
            client,
            sys.executable,
            str(fixture),
            env=_agent_environment(tmp_path / "home"),
            cwd=tmp_path,
            transport_kwargs={"limit": 10 * 1024 * 1024},
        ) as (agent, process):
            assert process.stderr is not None
            stderr_task = asyncio.create_task(
                _drain_stderr(process.stderr, captured)
            )
            yield agent, process
    except BaseException:
        failed = True
        raise
    finally:
        if stderr_task is not None:
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stderr_task, timeout=2)
        if failed and captured:
            print(captured.decode(errors="replace"), file=sys.stderr)
    if process is None or process.returncode != 0:
        raise AssertionError(
            "ACP fixture did not exit cleanly:\n"
            + captured.decode(errors="replace")
        )


@pytest.fixture(autouse=True)
def _isolate_project_lookup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.mark.asyncio
async def test_official_sdk_validates_lifecycle_content_mode_and_resume(tmp_path):
    async def scenario() -> None:
        client = _ConformanceClient()
        async with _sdk_agent(client, tmp_path) as (agent, process):
            initialized = await agent.initialize(
                protocol_version=acp.PROTOCOL_VERSION,
                client_capabilities=ClientCapabilities(),
                client_info=Implementation(
                    name="connectonion-conformance",
                    version="test",
                ),
            )
            assert initialized.protocol_version == acp.PROTOCOL_VERSION == 1
            capabilities = initialized.agent_capabilities.session_capabilities
            assert capabilities.resume is not None
            assert capabilities.close is not None
            prompt_capabilities = initialized.agent_capabilities.prompt_capabilities
            assert prompt_capabilities.image is True
            assert prompt_capabilities.embedded_context is True
            assert prompt_capabilities.audio is False

            created = await agent.new_session(str(tmp_path), mcp_servers=[])
            assert created.modes.current_mode_id == ":read-only"
            await agent.set_session_mode(created.session_id, ":workspace")
            prompted = await agent.prompt(
                created.session_id,
                [
                    acp.text_block("hello"),
                    acp.resource_link_block(
                        "api.md",
                        "file:///workspace/docs/api.md",
                        title="API guide",
                        mime_type="text/markdown",
                    ),
                ],
            )
            assert prompted.stop_reason == "end_turn"
            assert [
                update.content.text
                for session_id, update in client.updates
                if session_id == created.session_id
                and isinstance(update, AgentMessageChunk)
            ] == [
                "answer: hello\n\n"
                "Referenced resource: API guide "
                "(file:///workspace/docs/api.md)"
            ]

            attached = await agent.prompt(
                created.session_id,
                [
                    acp.text_block("attachments"),
                    ImageContentBlock(
                        type="image",
                        data=base64.b64encode(b"image").decode("ascii"),
                        mime_type="image/png",
                    ),
                    EmbeddedResourceContentBlock(
                        type="resource",
                        resource=BlobResourceContents(
                            uri="connectonion-upload:/notes.txt",
                            mime_type="text/plain",
                            blob=base64.b64encode(b"notes").decode("ascii"),
                        ),
                    ),
                ],
            )
            assert attached.stop_reason == "end_turn"
            assert [
                update.content.text
                for session_id, update in client.updates
                if session_id == created.session_id
                and isinstance(update, AgentMessageChunk)
            ][-1] == (
                "attachments: images=['data:image/png;base64,aW1hZ2U='], "
                "files=[('notes.txt', 'data:text/plain;base64,bm90ZXM=')]"
            )

            await agent.close_session(created.session_id)
            resumed = await agent.resume_session(
                created.session_id,
                str(tmp_path),
                mcp_servers=[],
            )
            assert resumed.modes.current_mode_id == ":workspace"
            await agent.close_session(created.session_id)
            assert process.returncode is None

    await asyncio.wait_for(scenario(), timeout=30)


@pytest.mark.asyncio
async def test_official_sdk_routes_permission_request_and_typed_rejection(tmp_path):
    async def scenario() -> None:
        client = _ConformanceClient()
        async with _sdk_agent(client, tmp_path) as (agent, _process):
            await agent.initialize(protocol_version=acp.PROTOCOL_VERSION)
            created = await agent.new_session(str(tmp_path), mcp_servers=[])

            prompted = await agent.prompt(
                created.session_id,
                [acp.text_block("approval")],
            )

            assert prompted.stop_reason == "end_turn"
            assert len(client.permission_requests) == 1
            session_id, tool_call, options = client.permission_requests[0]
            assert session_id == created.session_id
            assert tool_call.tool_call_id == "sdk-permission"
            assert tool_call.raw_input == {"content": "value"}
            assert [option.option_id for option in options] == [
                "allow_once",
                "allow_session",
                "reject_once",
            ]
            messages = [
                update.content.text
                for _, update in client.updates
                if isinstance(update, AgentMessageChunk)
            ]
            assert messages == ["permission approved: False"]

    await asyncio.wait_for(scenario(), timeout=30)
