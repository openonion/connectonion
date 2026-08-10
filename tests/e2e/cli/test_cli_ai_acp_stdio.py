"""Production stdio checks for ``co ai --acp`` without a live model."""

from __future__ import annotations

import asyncio
import json
import sys
import textwrap
from asyncio.subprocess import PIPE, Process
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import pytest

_FAKE_ACP_SERVER = textwrap.dedent(
    """
    import asyncio
    import time

    from connectonion.cli.co_ai.acp_server import serve_acp
    from connectonion.cli.commands import ai_commands


    class FakeAgent:
        io = None

        def input(self, prompt):
            print(f"fake agent received: {prompt}", flush=True)
            if prompt == "large":
                return "x" * 5_000_000
            if prompt != "block":
                return f"answer: {prompt}"
            while not self.io.receive_all("INTERRUPT"):
                time.sleep(0.01)
            return "late cancelled answer"


    ai_commands._create_agent = lambda **kwargs: FakeAgent()
    asyncio.run(
        serve_acp(
            model="test",
            max_iterations=2,
            yolo=False,
            yolo_turns=2,
        )
    )
    """
)


@asynccontextmanager
async def _server():
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _FAKE_ACP_SERVER,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
        limit=10 * 1024 * 1024,
    )
    try:
        yield process
    finally:
        if process.returncode is None:
            if process.stdin is not None:
                process.stdin.close()
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=1)
            if process.returncode is None:
                process.kill()
                await process.wait()


async def _send(process: Process, message: dict[str, Any]) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
    await process.stdin.drain()


async def _read_frame(process: Process) -> dict[str, Any]:
    assert process.stdout is not None
    line = await asyncio.wait_for(process.stdout.readline(), timeout=30)
    assert line
    return json.loads(line)


async def _request(
    process: Process,
    request_id: int,
    method: str,
    params: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    await _send(
        process,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        },
    )
    notifications = []
    while True:
        frame = await _read_frame(process)
        if frame.get("id") == request_id:
            return frame, notifications
        notifications.append(frame)


async def _initialize_and_create_session(
    process: Process,
    cwd: Path,
) -> str:
    initialized, _ = await _request(
        process,
        1,
        "initialize",
        {"protocolVersion": 1, "clientCapabilities": {}},
    )
    assert initialized["result"]["protocolVersion"] == 1
    created, _ = await _request(
        process,
        2,
        "session/new",
        {"cwd": str(cwd), "mcpServers": []},
    )
    return created["result"]["sessionId"]


async def _close_stdin(process: Process) -> None:
    assert process.stdin is not None
    process.stdin.close()
    await process.stdin.wait_closed()


@pytest.mark.asyncio
async def test_acp_subprocess_keeps_stdout_protocol_only_and_exits_on_eof(tmp_path):
    async with _server() as process:
        session_id = await _initialize_and_create_session(process, tmp_path)

        response, notifications = await _request(
            process,
            3,
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "hello"}],
            },
        )
        await _close_stdin(process)
        return_code = await asyncio.wait_for(process.wait(), timeout=2)
        assert process.stderr is not None
        stderr = (await process.stderr.read()).decode()

        assert return_code == 0
        assert response["result"]["stopReason"] == "end_turn"
        assert [item["method"] for item in notifications] == ["session/update"]
        assert notifications[0]["params"]["update"]["content"]["text"] == (
            "answer: hello"
        )
        assert "fake agent received: hello" in stderr


@pytest.mark.asyncio
async def test_acp_subprocess_eof_cancels_an_active_prompt(tmp_path):
    async with _server() as process:
        session_id = await _initialize_and_create_session(process, tmp_path)
        await _send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": "block"}],
                },
            },
        )
        assert process.stderr is not None
        while True:
            line = await asyncio.wait_for(process.stderr.readline(), timeout=30)
            assert line
            if b"fake agent received: block" in line:
                break

        await _close_stdin(process)
        return_code = await asyncio.wait_for(process.wait(), timeout=2)
        assert process.stdout is not None
        remaining_stdout = await process.stdout.read()

        assert return_code == 0
        assert b"late cancelled answer" not in remaining_stdout


@pytest.mark.asyncio
async def test_acp_subprocess_preserves_a_large_response(tmp_path):
    async with _server() as process:
        session_id = await _initialize_and_create_session(process, tmp_path)

        response, notifications = await _request(
            process,
            3,
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "large"}],
            },
        )
        await _close_stdin(process)
        return_code = await asyncio.wait_for(process.wait(), timeout=2)

        content = notifications[0]["params"]["update"]["content"]["text"]
        assert return_code == 0
        assert response["result"]["stopReason"] == "end_turn"
        assert len(content) == 5_000_000
        assert content.startswith("xxx") and content.endswith("xxx")
