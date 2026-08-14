"""Run Claude Code once while streaming its inner tools to ConnectOnion IO."""

import hashlib
import json
import math
import os
import queue
import shlex
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

from acp import default_environment

PERMISSION_MODES = (
    "default",
    "manual",
    "acceptEdits",
    "plan",
    "auto",
    "dontAsk",
    "bypassPermissions",
)

_MAX_ARGUMENT_CHARS = 4_000
_MAX_FIELD_CHARS = 1_000
_MAX_RESULT_CHARS = 4_000
_MAX_STDERR_CHARS = 16_000
_MAX_COLLECTION_ITEMS = 20
_MAX_STREAM_LINE_CHARS = 1024 * 1024
_MAX_FINAL_RESULT_CHARS = 64 * 1024
_MAX_USAGE_CHARS = 16 * 1024
_MAX_IDENTIFIER_CHARS = 512
_MAX_LIVE_EVENTS = 2_048
_MAX_ACTIVE_TOOLS = 256
_MAX_MAILBOX_LINES = 1_024
_MAX_CAPTURE_PARTS = 1_024
_MAX_PROMPT_CHARS = 1024 * 1024
_MAX_SESSION_CHARS = 512
_MAX_PATH_CHARS = 4_096
_MAX_MODEL_CHARS = 128
_MAX_TIMEOUT_SECONDS = 3_600
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
)
_CLAUDE_ENVIRONMENT_KEYS = (
    "ANTHROPIC_API_KEY",
    "APPDATA",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CONFIG_DIR",
    "COMSPEC",
    "HOMEDRIVE",
    "HOMEPATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOCALAPPDATA",
    "NODE_EXTRA_CA_CERTS",
    "PATHEXT",
    "PROGRAMDATA",
    "SSL_CERT_FILE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "WINDIR",
)


def claude_code(
    prompt: str,
    session_id: str = "",
    cwd: str = "",
    model: str = "",
    timeout: int = 600,
    agent=None,
) -> str:
    """Run Claude Code in manual mode and return one stable JSON envelope.

    The permission policy is deliberately absent from this Agent-facing
    signature. Use ``ClaudeCode(permission_mode=...)`` when an operator needs
    to bind a different mode before registering the tool.
    """
    return _run_claude_code(
        prompt=prompt,
        session_id=session_id,
        cwd=cwd,
        permission_mode="default",
        model=model,
        timeout=timeout,
        agent=agent,
        workspace=Path.cwd() if agent is not None else None,
    )


class ClaudeCode:
    """Claude Code tool with an operator-owned permission policy."""

    def __init__(
        self,
        permission_mode: str = "default",
        workspace: str | Path | None = None,
    ) -> None:
        if permission_mode not in PERMISSION_MODES:
            choices = ", ".join(PERMISSION_MODES)
            raise ValueError(
                f"Invalid permission mode {permission_mode!r}. Use one of: {choices}."
            )
        self._permission_mode = permission_mode
        self._workspace = _resolve_workspace(workspace)

    def claude_code(
        self,
        prompt: str,
        session_id: str = "",
        cwd: str = "",
        model: str = "",
        timeout: int = 600,
        agent=None,
    ) -> str:
        """Run or resume Claude Code with the operator-bound permission mode."""
        return _run_claude_code(
            prompt=prompt,
            session_id=session_id,
            cwd=cwd,
            permission_mode=self._permission_mode,
            model=model,
            timeout=timeout,
            agent=agent,
            workspace=self._workspace,
        )


def _run_claude_code(
    prompt: str,
    session_id: str = "",
    cwd: str = "",
    permission_mode: str = "default",
    model: str = "",
    timeout: int = 600,
    agent=None,
    workspace: str | Path | None = None,
) -> str:
    """Private runner shared by safe, configured, and co-ai entry points."""
    validation = _validate_request(prompt, session_id, cwd, model, timeout)
    if validation:
        return _envelope(session_id if isinstance(session_id, str) else "", error=validation)
    if permission_mode not in PERMISSION_MODES:
        choices = ", ".join(PERMISSION_MODES)
        return _envelope(
            session_id,
            error=f"Invalid permission mode {permission_mode!r}. Use one of: {choices}.",
        )

    working_directory, error = _working_directory(cwd, workspace)
    if error:
        return _envelope(session_id, error=error)
    command, error = _claude_command()
    if error:
        return _envelope(session_id, error=error)

    argv = _stream_command(command, prompt, session_id, permission_mode, model)
    forwarder = _ClaudeStreamForwarder(agent)
    cancelled = getattr(getattr(agent, "io", None), "is_cancelled", None)
    try:
        completed = _run_process(
            argv,
            cwd=str(working_directory),
            timeout=timeout,
            cancelled=cancelled if callable(cancelled) else None,
            on_event=forwarder.handle,
        )
    except FileNotFoundError:
        return _envelope(session_id, error="Claude Code CLI not found during launch.")
    except subprocess.TimeoutExpired:
        return _envelope(
            session_id,
            status="timeout",
            error=f"Claude Code timed out after {timeout}s.",
        )
    except _ProviderCancelled:
        return _envelope(session_id, error="Claude Code was interrupted.")
    except _ProviderStreamError as exc:
        return _envelope(
            session_id,
            error=f"Claude Code live event forwarding failed: {_one_line(exc)}",
        )
    except OSError as exc:
        return _envelope(session_id, error=f"Claude Code could not start: {exc}")
    except ValueError as exc:
        return _envelope(
            session_id,
            error=f"Claude Code received an invalid launch argument: {_one_line(exc)}",
        )
    return _completed_envelope(completed, session_id)


def _validate_request(prompt, session_id, cwd, model, timeout) -> str:
    if not isinstance(session_id, str):
        return "Session ID must be a string."
    if not isinstance(prompt, str) or not prompt.strip():
        return "Prompt must be a non-empty string."
    if len(prompt) > _MAX_PROMPT_CHARS:
        return "Prompt must not exceed 1 MiB."
    if len(session_id) > _MAX_SESSION_CHARS:
        return "Session ID is too long."
    if session_id and not _is_uuid(session_id):
        return "Session ID must be a canonical UUID."
    if not isinstance(cwd, str):
        return "Working directory must be a string."
    if not isinstance(model, str):
        return "Model must be a string."
    if len(cwd) > _MAX_PATH_CHARS:
        return "Working directory path is too long."
    if len(model) > _MAX_MODEL_CHARS:
        return "Model name is too long."
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        return "Timeout must be a positive integer."
    if timeout > _MAX_TIMEOUT_SECONDS:
        return "Timeout must not exceed 3600 seconds."
    return ""


def _is_uuid(value: str) -> bool:
    try:
        return str(UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _resolve_workspace(workspace: str | Path | None) -> Path:
    root = Path.cwd() if workspace is None else Path(workspace)
    try:
        resolved = root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"Claude Code workspace is unavailable: {exc}") from exc
    if not resolved.is_dir():
        raise ValueError(f"Claude Code workspace is not a directory: {resolved}")
    return resolved


def _working_directory(
    cwd: str, workspace: str | Path | None
) -> tuple[Path | None, str]:
    try:
        root = _resolve_workspace(workspace) if workspace is not None else None
        requested = Path(cwd).expanduser() if cwd else (root or Path.cwd())
        if not requested.is_absolute():
            requested = (root or Path.cwd()) / requested
        directory = requested.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        return None, f"Working directory is unavailable: {exc}"
    if not directory.is_dir():
        return None, f"Working directory is not a directory: {directory}"
    if root is not None and not directory.is_relative_to(root):
        return None, f"Working directory must stay inside workspace: {root}"
    return directory, ""


def _claude_command() -> tuple[list[str] | None, str]:
    try:
        command = _base_command()
    except ValueError as exc:
        return None, f"Invalid $CLAUDE_CODE_CMD: {_one_line(exc)}"
    if command is None:
        return None, "Claude Code CLI not found. Install it or set $CLAUDE_CODE_CMD."
    if _is_unsafe_windows_batch(command[0]):
        return None, (
            "Claude Code resolved to a Windows .cmd/.bat wrapper, which cannot "
            "safely receive arbitrary prompts. Install the native executable or "
            "set $CLAUDE_CODE_CMD to a native .exe."
        )
    return command, ""


def _stream_command(command, prompt, session_id, permission_mode, model):
    cli_mode = "manual" if permission_mode == "default" else permission_mode
    argv = [
        *command,
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--forward-subagent-text",
        "--safe-mode",
        "--permission-mode",
        cli_mode,
    ]
    if session_id:
        argv.extend(["--resume", session_id])
    if model:
        argv.extend(["--model", model])
    argv.extend(["--", prompt])
    return argv


def _completed_envelope(completed, requested_session: str) -> str:
    payload = completed.payload
    if not isinstance(payload, dict) or payload.get("type") != "result":
        detail = _one_line(completed.stderr or completed.invalid_output)
        suffix = f": {detail}" if detail else ""
        return _envelope(
            requested_session,
            exit_code=completed.returncode,
            error=f"Claude Code stream did not contain a result object{suffix}",
        )

    provider_session = payload.get("session_id")
    valid_session = (
        isinstance(provider_session, str)
        and bool(provider_session.strip())
        and len(provider_session) <= _MAX_SESSION_CHARS
        and _is_uuid(provider_session)
    )
    returned_session = requested_session or (provider_session if valid_session else "")
    result = _bounded_result(payload.get("result", ""), _MAX_FINAL_RESULT_CHARS)
    failed = completed.returncode != 0 or bool(payload.get("is_error"))
    error = _provider_error(payload, completed.stderr, completed.returncode) if failed else ""
    if requested_session and valid_session and provider_session != requested_session:
        mismatch = (
            f"Claude Code resumed {requested_session!r} but returned a different "
            f"session ID {provider_session!r}."
        )
        failed = True
        error = f"{mismatch} Provider error: {error}" if error else mismatch
    elif not failed and not valid_session:
        failed = True
        error = "Claude Code completed without a resumable session ID."
    return _envelope(
        returned_session,
        resumed=bool(requested_session),
        status="error" if failed else "completed",
        result=result,
        error=error,
        exit_code=completed.returncode,
        usage=_bounded_usage(payload.get("usage")),
        total_cost_usd=_finite_number(payload.get("total_cost_usd")),
    )


class _ClaudeStreamForwarder:
    """Translate Claude stream-json messages into native live tool events."""

    def __init__(self, agent) -> None:
        self._agent = agent
        self._io = getattr(agent, "io", None) if agent is not None else None
        session = getattr(agent, "current_session", None)
        self._parent_tool_call_id = (
            session.get("_active_tool_call_id") if isinstance(session, dict) else None
        )
        self._correlation = (
            {"invocationId": f"claude_code:{self._parent_tool_call_id}",
             "parentToolCallId": self._parent_tool_call_id}
            if self._parent_tool_call_id else {}
        )
        self._tools: dict[str, dict[str, Any]] = {}
        self._event_count = 0

    def handle(self, event: dict[str, Any]) -> None:
        if self._io is None or not isinstance(event, dict):
            return
        event_type = event.get("type")
        if event_type == "assistant":
            self._assistant(event)
        elif event_type == "user":
            self._user(event)

    def _assistant(self, event: dict[str, Any]) -> None:
        for block in _content_blocks(event):
            if block.get("type") != "tool_use":
                continue
            provider_id = block.get("id")
            if not isinstance(provider_id, str) or not provider_id:
                continue
            tool_id = _stable_identifier(provider_id)
            if tool_id in self._tools:
                continue
            if len(self._tools) >= _MAX_ACTIVE_TOOLS:
                continue
            # Reserve one later event for this tool's matching result. This
            # keeps the hard cap from leaving a visible card permanently open.
            if self._event_count + len(self._tools) + 2 > _MAX_LIVE_EVENTS:
                continue
            metadata = _event_metadata(event)
            metadata["name"] = _bounded_text(block.get("name") or "Tool")
            self._emit(
                "tool_call",
                tool_id=_wire_tool_id(provider_id),
                name=f"Claude Code › {metadata['name']}",
                args=_bounded_args(block.get("input")),
                status="in_progress",
                provider="claude_code",
                child_session_id=metadata["session_id"],
                parent_tool_id=metadata["parent_tool_id"],
                **self._correlation,
            )
            self._tools[tool_id] = metadata

    def _user(self, event: dict[str, Any]) -> None:
        for block in _content_blocks(event):
            if block.get("type") != "tool_result":
                continue
            provider_id = block.get("tool_use_id")
            if not isinstance(provider_id, str) or not provider_id:
                continue
            tool_id = _stable_identifier(provider_id)
            metadata = self._tools.get(tool_id) or _event_metadata(event)
            if tool_id not in self._tools:
                if self._event_count + len(self._tools) + 2 > _MAX_LIVE_EVENTS:
                    continue
                self._emit_unknown_start(provider_id, metadata)
            self._emit(
                "tool_result",
                tool_id=_wire_tool_id(provider_id),
                status="failed" if block.get("is_error") else "completed",
                result=_bounded_result(block.get("content")),
                provider="claude_code",
                child_session_id=metadata["session_id"],
                parent_tool_id=metadata["parent_tool_id"],
                **self._correlation,
            )
            self._tools.pop(tool_id, None)

    def _emit_unknown_start(self, provider_id: str, metadata: dict[str, Any]) -> None:
        self._emit(
            "tool_call",
            tool_id=_wire_tool_id(provider_id),
            name="Claude Code › Tool",
            args={},
            status="in_progress",
            provider="claude_code",
            child_session_id=metadata["session_id"],
            parent_tool_id=metadata["parent_tool_id"],
            **self._correlation,
        )

    def _emit(self, event_type: str, **fields: Any) -> None:
        if self._event_count >= _MAX_LIVE_EVENTS:
            return
        self._event_count += 1
        record = getattr(self._agent, "_record_trace", None)
        if callable(record) and isinstance(getattr(self._agent, "current_session", None), dict):
            record({"type": event_type, **fields})
        else:
            self._io.log(event_type, **fields)


def _content_blocks(event: dict[str, Any]) -> list[dict[str, Any]]:
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, dict):
        content = [content]
    if not isinstance(content, list):
        return []
    return [block for block in content[:_MAX_COLLECTION_ITEMS] if isinstance(block, dict)]


def _event_metadata(event: dict[str, Any]) -> dict[str, Any]:
    session_id = event.get("session_id")
    parent_id = event.get("parent_tool_use_id")
    return {
        "session_id": _stable_identifier(session_id) if isinstance(session_id, str) else "",
        "parent_tool_id": (
            _stable_identifier(parent_id) if isinstance(parent_id, str) else None
        ),
    }


def _wire_tool_id(provider_id: str) -> str:
    return f"claude:{_stable_identifier(provider_id)}"


def _stable_identifier(value: str) -> str:
    if len(value) <= _MAX_IDENTIFIER_CHARS:
        return value
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bounded_text(value: Any) -> str:
    return _bounded_result(value, _MAX_FIELD_CHARS)


def _bounded_args(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"value": _bounded_result(value)}
    safe, truncated, redacted = _redact_value(value)
    if truncated:
        safe["_truncated"] = True
    if redacted:
        safe["_redacted"] = True
    encoded = json.dumps(safe, ensure_ascii=False, default=str)
    if len(encoded) > _MAX_ARGUMENT_CHARS:
        safe = _argument_summary(safe, encoded)
        safe["_truncated"] = True
        if redacted:
            safe["_redacted"] = True
    return safe


def _redact_value(
    value: Any, key: str = "", depth: int = 0
) -> tuple[Any, bool, bool]:
    if any(part in key.lower() for part in _SENSITIVE_KEY_PARTS):
        return "[redacted]", False, True
    if isinstance(value, str):
        if len(value) <= _MAX_FIELD_CHARS:
            return value, False, False
        return value[: _MAX_FIELD_CHARS - 1] + "…", True, False
    if isinstance(value, dict):
        if depth >= 4:
            return _redact_deep_mapping(value)
        return _redact_mapping(value, depth)
    if isinstance(value, (list, tuple)):
        if depth >= 4:
            return ["[omitted]"], True, False
        return _redact_sequence(value, depth)
    return value, False, False


def _redact_mapping(value: dict, depth: int) -> tuple[dict, bool, bool]:
    result = {}
    truncated = len(value) > _MAX_COLLECTION_ITEMS
    redacted = False
    for item_key, item_value in list(value.items())[:_MAX_COLLECTION_ITEMS]:
        safe, item_truncated, item_redacted = _redact_value(
            item_value, str(item_key), depth + 1
        )
        result[str(item_key)] = safe
        truncated = truncated or item_truncated
        redacted = redacted or item_redacted
    return result, truncated, redacted


def _redact_deep_mapping(value: dict) -> tuple[dict, bool, bool]:
    result = {}
    redacted = False
    for item_key in list(value)[:_MAX_COLLECTION_ITEMS]:
        key = str(item_key)
        sensitive = any(part in key.lower() for part in _SENSITIVE_KEY_PARTS)
        result[key] = "[redacted]" if sensitive else "[omitted]"
        redacted = redacted or sensitive
    return result, True, redacted


def _redact_sequence(value, depth: int) -> tuple[list, bool, bool]:
    result = []
    truncated = len(value) > _MAX_COLLECTION_ITEMS
    redacted = False
    for item in list(value)[:_MAX_COLLECTION_ITEMS]:
        safe, item_truncated, item_redacted = _redact_value(item, depth=depth + 1)
        result.append(safe)
        truncated = truncated or item_truncated
        redacted = redacted or item_redacted
    return result, truncated, redacted


def _argument_summary(value: dict[str, Any], encoded: str) -> dict[str, Any]:
    priority = ("command", "description", "file_path", "path", "query", "pattern")
    summary = {}
    remaining = _MAX_ARGUMENT_CHARS - 100
    for key in priority:
        if key not in value or remaining <= 0:
            continue
        text = _bounded_result(value[key], remaining)
        summary[key] = text
        remaining -= len(text) + len(key)
    if not summary:
        summary["preview"] = encoded[: _MAX_ARGUMENT_CHARS - 100] + "…"
    return summary


def _bounded_result(value: Any, limit: int = _MAX_RESULT_CHARS) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _bounded_usage(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    safe = {}
    for key, item in list(value.items())[:_MAX_COLLECTION_ITEMS]:
        number = _finite_number(item)
        if number is not None:
            safe[_bounded_text(key)] = number
    encoded = json.dumps(safe, ensure_ascii=False, default=str)
    return safe if len(encoded) <= _MAX_USAGE_CHARS else {}


def _finite_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


@dataclass
class _StreamCompleted:
    payload: dict[str, Any] | None
    returncode: int
    stderr: str
    invalid_output: str


class _ProviderCancelled(Exception):
    """The enclosing agent revoked this provider invocation."""


class _ProviderStreamError(Exception):
    """The live IO consumer rejected a provider event."""


def _run_process(
    argv: list[str],
    *,
    cwd: str,
    timeout: int,
    cancelled: Callable[[], bool] | None = None,
    on_event: Callable[[dict[str, Any]], None],
) -> _StreamCompleted:
    """Read Claude NDJSON without blocking cancellation on one quiet stream."""
    process = _start_process(argv, cwd)
    mailbox: queue.Queue = queue.Queue(maxsize=_MAX_MAILBOX_LINES)
    readers_stopped = threading.Event()
    _start_reader(process.stdout, "stdout", mailbox, readers_stopped)
    _start_reader(process.stderr, "stderr", mailbox, readers_stopped)
    deadline = time.monotonic() + timeout
    payload = None
    stderr_parts: list[str] = []
    invalid_parts: list[str] = []
    eof: set[str] = set()

    try:
        while len(eof) < 2 or process.poll() is None:
            _check_process_boundary(process, argv, timeout, deadline, cancelled)
            try:
                source, line = mailbox.get(timeout=0.05)
            except queue.Empty:
                continue
            if line is None:
                eof.add(source)
            elif source == "stderr":
                _append_bounded(stderr_parts, line, _MAX_STDERR_CHARS)
            else:
                event = _parse_stream_line(line, invalid_parts)
                if event is not None:
                    on_event(event)
                    if event.get("type") == "result":
                        payload = event
    except (_ProviderCancelled, subprocess.TimeoutExpired):
        readers_stopped.set()
        raise
    except Exception as exc:
        readers_stopped.set()
        _kill_process_tree(process)
        _close_pipes(process)
        raise _ProviderStreamError(_one_line(exc)) from exc
    readers_stopped.set()
    returncode = process.wait(timeout=1)
    _close_pipes(process)
    return _StreamCompleted(
        payload=payload,
        returncode=returncode,
        stderr="".join(stderr_parts),
        invalid_output="".join(invalid_parts),
    )


def _start_process(argv: list[str], cwd: str):
    platform_options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    return subprocess.Popen(
        argv,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_claude_environment(),
        shell=False,
        **platform_options,
    )


def _claude_environment() -> dict[str, str]:
    environment = default_environment()
    for key in _CLAUDE_ENVIRONMENT_KEYS:
        value = os.environ.get(key)
        if value and not value.startswith("()"):
            environment[key] = value
    return environment


def _start_reader(
    stream, source: str, mailbox: queue.Queue, stopped: threading.Event
) -> threading.Thread:
    def put(item) -> None:
        while not stopped.is_set():
            try:
                mailbox.put(item, timeout=0.1)
                return
            except queue.Full:
                continue

    def read() -> None:
        try:
            while True:
                line = stream.readline(_MAX_STREAM_LINE_CHARS + 1)
                if not line:
                    break
                if len(line) > _MAX_STREAM_LINE_CHARS:
                    while line and not line.endswith("\n"):
                        line = stream.readline(_MAX_STREAM_LINE_CHARS + 1)
                    put(("stderr", f"Claude Code {source} line exceeded 1 MiB\n"))
                    continue
                put((source, line))
        except (OSError, ValueError) as exc:
            put(("stderr", f"Claude Code {source} reader failed: {exc}\n"))
        finally:
            put((source, None))

    thread = threading.Thread(
        target=read,
        name=f"claude-code-{source}",
        daemon=True,
    )
    thread.start()
    return thread


def _check_process_boundary(process, argv, timeout, deadline, cancelled) -> None:
    if cancelled is not None and cancelled():
        _kill_process_tree(process)
        _close_pipes(process)
        raise _ProviderCancelled()
    if time.monotonic() >= deadline:
        _terminate_process_tree(process)
        _close_pipes(process)
        raise subprocess.TimeoutExpired(argv, timeout)


def _parse_stream_line(line: str, invalid_parts: list[str]) -> dict | None:
    if len(line) > _MAX_STREAM_LINE_CHARS:
        _append_bounded(invalid_parts, "oversized stream line\n", _MAX_STDERR_CHARS)
        return None
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        _append_bounded(invalid_parts, line, _MAX_STDERR_CHARS)
        return None
    if isinstance(event, dict):
        return event
    _append_bounded(invalid_parts, line, _MAX_STDERR_CHARS)
    return None


def _append_bounded(parts: list[str], value: str, limit: int) -> None:
    if len(parts) >= _MAX_CAPTURE_PARTS:
        return
    used = sum(map(len, parts))
    if used < limit:
        parts.append(value[: limit - used])


def _close_pipes(process) -> None:
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass


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


def _kill_process_tree(process) -> None:
    if os.name == "nt":
        _terminate_process_tree(process)
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        _try_process_signal(process.kill)
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def _terminate_process_tree(process) -> None:
    if os.name == "nt":
        _terminate_windows_tree(process)
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        _try_process_signal(process.terminate)
        return
    _wait_for_process_group(process)


def _terminate_windows_tree(process) -> None:
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
            _try_process_signal(process.kill)
    except (OSError, subprocess.TimeoutExpired):
        _try_process_signal(process.kill)


def _wait_for_process_group(process) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        process.poll()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        except OSError:
            break
        time.sleep(0.05)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        _try_process_signal(process.kill)


def _try_process_signal(action: Callable[[], Any]) -> None:
    try:
        action()
    except OSError:
        pass


def _provider_error(payload: dict, stderr: str, exit_code: int) -> str:
    error = payload.get("error")
    if isinstance(error, str) and error.strip():
        return _one_line(error)
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return _one_line(error["message"])
    result = payload.get("result")
    if payload.get("is_error") and isinstance(result, str) and result.strip():
        return _one_line(result)
    detail = _one_line(stderr)
    if detail:
        return detail
    if isinstance(result, str) and result.strip():
        return _one_line(result)
    return f"Claude Code exited with status {exit_code}."


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
