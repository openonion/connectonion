"""Production stdio checks for ``co ai --acp`` without a live model."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from asyncio.subprocess import PIPE, Process
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import acp as acp_package
import pytest


@asynccontextmanager
async def _server(state_root: Path):
    child_env = acp_package.default_environment()
    child_env["HOME"] = str(state_root)
    child_env["USERPROFILE"] = str(state_root)
    child_env["APPDATA"] = str(state_root / "AppData" / "Roaming")
    child_env["LOCALAPPDATA"] = str(state_root / "AppData" / "Local")
    repo_root = Path(__file__).resolve().parents[3]
    acp_site_packages = Path(acp_package.__file__).resolve().parents[1]
    child_env["PYTHONPATH"] = os.pathsep.join(
        (str(repo_root), str(acp_site_packages))
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(Path(__file__).with_name("acp_test_agent.py")),
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
async def test_acp_subprocess_does_not_inherit_unapproved_environment(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ACP_TEST_SECRET", "must-not-cross-process-boundary")

    async with _server(tmp_path / "home") as process:
        session_id = await _initialize_and_create_session(process, tmp_path)
        response, notifications = await _request(
            process,
            3,
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "environment"}],
            },
        )

        assert response["result"]["stopReason"] == "end_turn"
        assert notifications[0]["params"]["update"]["content"]["text"] == (
            "secret inherited: False"
        )


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
        assert resumed["result"]["modes"]["currentModeId"] == "safe"
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
        assert resumed["result"]["modes"]["currentModeId"] == "safe"
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


@pytest.mark.asyncio
async def test_acp_subprocess_sets_and_resumes_the_official_mode_state(tmp_path):
    state_root = tmp_path / "home"
    async with _server(state_root) as first:
        await _initialize(first)
        created, notifications = await _request(
            first,
            2,
            "session/new",
            {"cwd": str(tmp_path), "mcpServers": []},
        )
        session_id = created["result"]["sessionId"]
        modes = created["result"]["modes"]
        assert modes["currentModeId"] == "safe"
        assert [mode["id"] for mode in modes["availableModes"]] == [
            "safe",
            "accept_edits",
        ]
        assert notifications == []

        changed, notifications = await _request(
            first,
            3,
            "session/set_mode",
            {"sessionId": session_id, "modeId": "accept_edits"},
        )
        assert changed["result"] == {}
        assert notifications == []
        closed, _ = await _request(
            first,
            4,
            "session/close",
            {"sessionId": session_id},
        )
        assert closed["result"] == {}

    async with _server(state_root) as second:
        await _initialize(second)
        resumed, notifications = await _request(
            second,
            2,
            "session/resume",
            {"sessionId": session_id, "cwd": str(tmp_path), "mcpServers": []},
        )
        assert resumed["result"]["modes"]["currentModeId"] == "accept_edits"
        assert notifications == []
