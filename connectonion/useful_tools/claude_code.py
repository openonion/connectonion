"""Run or resume Claude Code through its headless JSON CLI contract."""

import json
import os
import shlex
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

PERMISSION_MODES = (
    "default",
    "manual",
    "acceptEdits",
    "plan",
    "auto",
    "dontAsk",
    "bypassPermissions",
)


def claude_code(
    prompt: str,
    session_id: str = "",
    cwd: str = "",
    permission_mode: str = "default",
    model: str = "",
    timeout: int = 600,
    agent=None,
) -> str:
    """Run or resume Claude Code and return one stable JSON envelope.

    ``default`` is ConnectOnion's stable name for Claude Code's current
    ``manual`` CLI mode. ``bypassPermissions`` is available only when the
    caller explicitly requests it.
    """
    if not isinstance(session_id, str):
        return _envelope("", error="Session ID must be a string.")
    if not isinstance(prompt, str) or not prompt.strip():
        return _envelope(session_id, error="Prompt must be a non-empty string.")
    if not isinstance(cwd, str):
        return _envelope(session_id, error="Working directory must be a string.")
    if not isinstance(model, str):
        return _envelope(session_id, error="Model must be a string.")
    if permission_mode not in PERMISSION_MODES:
        choices = ", ".join(PERMISSION_MODES)
        return _envelope(
            session_id,
            error=f"Invalid permission mode {permission_mode!r}. Use one of: {choices}.",
        )
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        return _envelope(session_id, error="Timeout must be a positive integer.")

    try:
        working_directory = Path(cwd or ".").expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        return _envelope(session_id, error=f"Working directory is unavailable: {exc}")
    if not working_directory.is_dir():
        return _envelope(
            session_id,
            error=f"Working directory is not a directory: {working_directory}",
        )

    try:
        command = _base_command()
    except ValueError as exc:
        return _envelope(
            session_id,
            error=f"Invalid $CLAUDE_CODE_CMD: {_one_line(exc)}",
        )
    if command is None:
        return _envelope(
            session_id,
            error=(
                "Claude Code CLI not found. Install it or set $CLAUDE_CODE_CMD."
            ),
        )
    if _is_unsafe_windows_batch(command[0]):
        return _envelope(
            session_id,
            error=(
                "Claude Code resolved to a Windows .cmd/.bat wrapper, which cannot "
                "safely receive arbitrary prompts. Install the native executable or "
                "set $CLAUDE_CODE_CMD to a native .exe (or node.exe plus its script)."
            ),
        )

    cli_mode = "manual" if permission_mode == "default" else permission_mode
    argv = [
        *command,
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
        cli_mode,
    ]
    if session_id:
        argv.extend(["--resume", session_id])
    if model:
        argv.extend(["--model", model])
    argv.extend(["--", prompt])

    try:
        completed = _run_process(
            argv,
            cwd=str(working_directory),
            timeout=timeout,
        )
    except FileNotFoundError:
        return _envelope(
            session_id,
            error=(
                "Claude Code CLI not found. Install it or set $CLAUDE_CODE_CMD."
            ),
        )
    except subprocess.TimeoutExpired:
        return _envelope(
            session_id,
            status="timeout",
            error=f"Claude Code timed out after {timeout}s.",
        )
    except OSError as exc:
        return _envelope(session_id, error=f"Claude Code could not start: {exc}")
    except ValueError as exc:
        return _envelope(
            session_id,
            error=f"Claude Code received an invalid launch argument: {_one_line(exc)}",
        )

    try:
        output = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError):
        detail = _one_line(completed.stderr or completed.stdout)
        suffix = f": {detail}" if detail else ""
        return _envelope(
            session_id,
            exit_code=completed.returncode,
            error=f"Claude Code returned invalid JSON{suffix}",
        )
    payload = _result_payload(output)
    if payload is None:
        detail = _one_line(completed.stderr)
        suffix = f": {detail}" if detail else ""
        return _envelope(
            session_id,
            exit_code=completed.returncode,
            error=f"Claude Code JSON did not contain a result object{suffix}.",
        )

    provider_session = payload.get("session_id")
    valid_provider_session = (
        isinstance(provider_session, str) and bool(provider_session.strip())
    )
    returned_session = provider_session if valid_provider_session else session_id
    result = payload.get("result", "")
    result = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    failed = completed.returncode != 0 or bool(payload.get("is_error"))
    error = _provider_error(payload, completed.stderr, completed.returncode) if failed else ""
    if not failed and not valid_provider_session:
        failed = True
        error = "Claude Code completed without a resumable session ID."
    elif not failed and session_id and returned_session != session_id:
        failed = True
        error = (
            f"Claude Code resumed {session_id!r} but returned a different session "
            f"ID {returned_session!r}."
        )
    return _envelope(
        returned_session,
        resumed=bool(session_id),
        status="error" if failed else "completed",
        result=result,
        error=error,
        exit_code=completed.returncode,
        usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else {},
        total_cost_usd=payload.get("total_cost_usd"),
    )


def _base_command() -> list[str] | None:
    override = os.environ.get("CLAUDE_CODE_CMD", "").strip()
    if override:
        command = _split_command(override)
        return command or None
    found = shutil.which("claude")
    return [found] if found else None


def _split_command(value: str, *, windows: bool | None = None) -> list[str]:
    windows = os.name == "nt" if windows is None else windows
    parts = shlex.split(value, posix=not windows)
    if not windows:
        return parts
    return [
        part[1:-1]
        if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'"
        else part
        for part in parts
    ]


def _is_unsafe_windows_batch(command: str, *, windows: bool | None = None) -> bool:
    windows = os.name == "nt" if windows is None else windows
    return windows and Path(command).suffix.lower() in (".cmd", ".bat")


def _run_process(argv: list[str], *, cwd: str, timeout: int):
    """Run one headless process and terminate its process tree on timeout."""
    platform_options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        **platform_options,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            # A detached descendant can keep inherited pipes open even after the
            # process tree has been signalled. Never let that defeat our public
            # timeout contract.
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            try:
                process.kill()
                process.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                pass
            stdout, stderr = "", ""
        raise subprocess.TimeoutExpired(
            argv, timeout, output=stdout, stderr=stderr
        ) from None
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def _terminate_process_tree(process) -> None:
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
                shell=False,
            )
            if result.returncode != 0:
                process.kill()
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    # The group leader can exit while grandchildren continue to own stdout or
    # stderr. Observe the process group itself, then force-kill whatever remains.
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _provider_error(payload: dict, stderr: str, exit_code: int) -> str:
    error = payload.get("error")
    if isinstance(error, str) and error.strip():
        return _one_line(error)
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return _one_line(message)
    result = payload.get("result")
    if payload.get("is_error") and isinstance(result, str) and result.strip():
        return _one_line(result)
    detail = _one_line(stderr)
    if detail:
        return detail
    if isinstance(result, str) and result.strip():
        return _one_line(result)
    return f"Claude Code exited with status {exit_code}."


def _result_payload(output: Any) -> dict | None:
    """Accept documented object output and newer event-array output."""
    if isinstance(output, dict):
        return output
    if not isinstance(output, list):
        return None
    results = [
        item
        for item in output
        if isinstance(item, dict) and item.get("type") == "result"
    ]
    return results[-1] if results else None


def _one_line(value: Any, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _envelope(
    session_id: str,
    *,
    resumed: bool | None = None,
    status: str = "error",
    result: str = "",
    error: str = "",
    exit_code: int = -1,
    usage: dict | None = None,
    total_cost_usd: Any = None,
) -> str:
    return json.dumps(
        {
            "provider": "claude_code",
            "session_id": session_id,
            "resumed": bool(session_id) if resumed is None else resumed,
            "status": status,
            "result": result,
            "error": error,
            "exit_code": exit_code,
            "usage": usage or {},
            "total_cost_usd": total_cost_usd,
        },
        ensure_ascii=False,
    )
