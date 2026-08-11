"""Production stdio checks for ``co ai --acp`` without a live model."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import textwrap
from asyncio.subprocess import PIPE, Process
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import acp as acp_package
import pytest

_FAKE_ACP_SERVER = textwrap.dedent(
    """
    import asyncio
    import time

    from connectonion.cli.co_ai.acp_server import serve_acp
    from connectonion.cli.commands import ai_commands


    class FakeAgent:
        system_prompt = "system"

        def __init__(self):
            self.io = None
            self.current_session = {"trace": [], "turn": 0}

        def finish(self, reason):
            event = {
                "type": "turn_result",
                "turn": self.current_session["turn"],
                "reason": reason,
                "usage": None,
            }
            self.current_session["trace"].append(event)
            self.io.send(event)

        def input(self, prompt, session=None):
            if session is not None:
                self.current_session = dict(session)
                self.current_session["messages"] = list(session["messages"])
                self.current_session["trace"] = list(session["trace"])
            print(f"fake agent received: {prompt}", flush=True)
            self.current_session["turn"] += 1
            if prompt == "large":
                result = "x" * 5_000_000
                self.finish("natural")
                return result
            if prompt != "block":
                result = f"answer: {prompt}"
                self.finish("natural")
                return result
            while not self.io.receive_all("INTERRUPT"):
                time.sleep(0.01)
            self.finish("interrupted")
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
async def _server(state_root: Path):
    child_env = dict(os.environ)
    child_env["HOME"] = str(state_root)
    repo_root = Path(__file__).resolve().parents[3]
    acp_site_packages = Path(acp_package.__file__).resolve().parents[1]
    child_env["PYTHONPATH"] = os.pathsep.join(
        (str(repo_root), str(acp_site_packages))
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _FAKE_ACP_SERVER,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
        env=child_env,
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
    await _initialize(process)
    created, _ = await _request(
        process,
        2,
        "session/new",
        {"cwd": str(cwd), "mcpServers": []},
    )
    return created["result"]["sessionId"]


async def _initialize(process: Process) -> None:
    initialized, _ = await _request(
        process,
        1,
        "initialize",
        {"protocolVersion": 1, "clientCapabilities": {}},
    )
    assert initialized["result"]["protocolVersion"] == 1


async def _close_stdin(process: Process) -> None:
    assert process.stdin is not None
    process.stdin.close()
    await process.stdin.wait_closed()


@pytest.fixture(autouse=True)
def _isolate_project_lookup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.mark.asyncio
async def test_acp_subprocess_keeps_stdout_protocol_only_and_exits_on_eof(tmp_path):
    async with _server(tmp_path / "home") as process:
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
    async with _server(tmp_path / "home") as process:
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
    async with _server(tmp_path / "home") as process:
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


@pytest.mark.asyncio
async def test_acp_subprocess_lease_blocks_a_second_process_until_close(tmp_path):
    state_root = tmp_path / "home"
    async with _server(state_root) as owner, _server(state_root) as contender:
        session_id = await _initialize_and_create_session(owner, tmp_path)
        await _initialize(contender)

        rejected, _ = await _request(
            contender,
            2,
            "session/resume",
            {"sessionId": session_id, "cwd": str(tmp_path), "mcpServers": []},
        )
        assert rejected["error"]["code"] == -32002

        closed, _ = await _request(
            owner,
            3,
            "session/close",
            {"sessionId": session_id},
        )
        assert closed["result"] == {}

        resumed, notifications = await _request(
            contender,
            3,
            "session/resume",
            {"sessionId": session_id, "cwd": str(tmp_path), "mcpServers": []},
        )
        assert resumed["result"] == {}
        assert notifications == []

@pytest.mark.asyncio
async def test_acp_subprocess_eof_releases_lease_for_later_resume(tmp_path):
    state_root = tmp_path / "home"
    async with _server(state_root) as first:
        session_id = await _initialize_and_create_session(first, tmp_path)
        await _close_stdin(first)
        assert await asyncio.wait_for(first.wait(), timeout=2) == 0

    async with _server(state_root) as second:
        await _initialize(second)
        resumed, notifications = await _request(
            second,
            2,
            "session/resume",
            {"sessionId": session_id, "cwd": str(tmp_path), "mcpServers": []},
        )
        assert resumed["result"] == {}
        assert notifications == []

        response, notifications = await _request(
            second,
            3,
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "continued"}],
            },
        )
        assert response["result"]["stopReason"] == "end_turn"
        assert notifications[0]["params"]["update"]["content"]["text"] == (
            "answer: continued"
        )
