"""Private typed ACP transport used by the public ``acp_agent`` tool."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import acp
from acp.client.connection import ClientSideConnection
from acp.schema import (
    AgentCapabilities,
    AgentMessageChunk,
    AllowedOutcome,
    ClientCapabilities,
    DeniedOutcome,
    Implementation,
    PermissionOption,
    RequestPermissionResponse,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
)

from .._version import __version__
from ..core.acp_transport import StrictACPTransport

APPROVAL_MODES = ("manual", "auto", "deny")
_STDIO_LIMIT = 10 * 1024 * 1024
_RESULT_LIMIT = 64 * 1024
_ERROR_LIMIT = 4 * 1024
_EVENT_TEXT_LIMIT = 512
_EVENT_LIMIT = 2048
_ACTIVE_TOOL_LIMIT = 256
_MESSAGE_CHUNK_LIMIT = 2048
_POLL_SECONDS = 0.1
_PROMPT_LIMIT = 1024 * 1024
_SESSION_ID_LIMIT = 512
_PATH_LIMIT = 4096
_ENGINE_LIMIT = 64
_TIMEOUT_LIMIT = 3600
_STARTUP_LIMIT = 120.0
_TRUNCATED_SUFFIX = "\n... (ACP result truncated at 64 KiB)"
_GEMINI_ENV_VARS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_PROJECT_ID",
    "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_APPLICATION_CREDENTIALS",
)


def validate_inputs(
    prompt: Any, engine: Any, session_id: Any, cwd: Any, timeout: Any
) -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        return "Prompt must be a non-empty string."
    if len(prompt.encode("utf-8")) > _PROMPT_LIMIT:
        return "Prompt must not exceed 1 MiB."
    if not isinstance(engine, str):
        return "Engine must be a string."
    if len(engine.encode("utf-8")) > _ENGINE_LIMIT:
        return "Engine name is too long."
    if not isinstance(session_id, str):
        return "Session ID must be a string."
    if len(session_id.encode("utf-8")) > _SESSION_ID_LIMIT:
        return "Session ID is too long."
    if not isinstance(cwd, str):
        return "Working directory must be a string."
    if len(cwd.encode("utf-8")) > _PATH_LIMIT:
        return "Working directory path is too long."
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        return "Timeout must be a positive integer."
    if timeout > _TIMEOUT_LIMIT:
        return "Timeout must not exceed 3600 seconds."
    return ""


def engine_environment(engine: str, approval: str) -> dict[str, str]:
    if engine == "claude-code":
        return {
            name: os.environ[name]
            for name in ("CLAUDE_CONFIG_DIR", "ANTHROPIC_API_KEY")
            if os.getenv(name)
        }
    if engine == "gemini":
        environment = {
            name: os.environ[name]
            for name in _GEMINI_ENV_VARS
            if os.getenv(name)
        }
        environment["NO_BROWSER"] = "1"
        return environment
    if engine != "codex":
        return {}
    environment = {
        "INITIAL_AGENT_MODE": "agent" if approval == "auto" else "read-only",
        "CODEX_CONFIG": json.dumps({"approvals_reviewer": "user"}),
        "NO_BROWSER": "1",
    }
    api_key_name = next(
        (name for name in ("CODEX_API_KEY", "OPENAI_API_KEY") if os.getenv(name)),
        None,
    )
    if api_key_name is not None:
        environment[api_key_name] = os.environ[api_key_name]
        environment["DEFAULT_AUTH_REQUEST"] = json.dumps({"methodId": "api-key"})
        return environment

    if "CODEX_HOME" in os.environ:
        environment["CODEX_HOME"] = os.environ["CODEX_HOME"]
    return environment


def session_metadata(engine: str) -> dict[str, Any]:
    if engine != "claude-code":
        return {}
    # Do not inherit persistent allow rules from the interactive Claude CLI.
    return {"claudeCode": {"options": {"settingSources": []}}}


def required_mode(engine: str, approval: str) -> str | None:
    if engine == "claude-code":
        return "dontAsk" if approval == "deny" else "default"
    if engine == "codex":
        return "agent" if approval == "auto" else "read-only"
    if engine == "gemini":
        if approval == "auto":
            return "yolo"
        return "plan" if approval == "deny" else "default"
    return None


@asynccontextmanager
async def _spawn_guarded_agent_process(
    command: tuple[str, ...],
    cwd: Path,
    client: "ToolClient",
    environment: dict[str, str],
):
    """Put child callbacks through the same strict boundary as native ACP."""

    async with acp.spawn_stdio_transport(
        command[0],
        *command[1:],
        env=environment,
        cwd=cwd,
        limit=_STDIO_LIMIT,
        shutdown_timeout=2.0,
    ) as (reader, writer, process):
        connection = ClientSideConnection(
            client,
            StrictACPTransport(
                reader,
                writer,
                max_frame_bytes=_STDIO_LIMIT,
            ),
            observers=[client.observe_stream],
        )
        try:
            yield connection, process
        finally:
            await connection.close()


async def run_agent(
    command: tuple[str, ...],
    engine: str,
    prompt: str,
    session_id: str,
    cwd: Path,
    timeout: int,
    client: "ToolClient",
    environment: dict[str, str],
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    startup_deadline = (
        min(deadline, loop.time() + _STARTUP_LIMIT)
        if engine == "gemini"
        else deadline
    )
    stderr_task: asyncio.Task | None = None
    failure: Exception | None = None
    result: dict[str, Any] | None = None
    stderr_signals = {"authentication": False}

    try:
        async with _spawn_guarded_agent_process(
            command,
            cwd,
            client,
            environment,
        ) as (connection, process):
            if process.stderr is not None:
                stderr_task = asyncio.create_task(
                    _drain_stderr(process.stderr, stderr_signals)
                )
            initialized = await _before_deadline(
                connection.initialize(
                    protocol_version=acp.PROTOCOL_VERSION,
                    client_capabilities=ClientCapabilities(),
                    client_info=Implementation(
                        name="connectonion", title="ConnectOnion", version=__version__
                    ),
                ),
                startup_deadline,
                timeout,
            )
            if initialized.protocol_version != acp.PROTOCOL_VERSION:
                raise RuntimeError(
                    f"{engine} selected unsupported ACP protocol version "
                    f"{initialized.protocol_version}; client supports "
                    f"{acp.PROTOCOL_VERSION}"
                )
            agent_capabilities = (
                initialized.agent_capabilities or AgentCapabilities()
            )
            resumed = False
            metadata = session_metadata(engine)
            if session_id:
                client.active_session = session_id
                session_capabilities = agent_capabilities.session_capabilities
                resume_capability = getattr(session_capabilities, "resume", None)
                if resume_capability is not None:
                    session = await _before_deadline(
                        connection.resume_session(
                            session_id, str(cwd), mcp_servers=[], **metadata
                        ),
                        startup_deadline,
                        timeout,
                    )
                elif agent_capabilities.load_session:
                    session = await _before_deadline(
                        connection.load_session(
                            str(cwd), session_id, mcp_servers=[], **metadata
                        ),
                        startup_deadline,
                        timeout,
                    )
                else:
                    raise RuntimeError(
                        f"{engine} does not advertise session/resume or session/load"
                    )
                active_session = session_id
                resumed = True
            else:
                session = await _before_deadline(
                    connection.new_session(str(cwd), mcp_servers=[], **metadata),
                    startup_deadline,
                    timeout,
                )
                active_session = _session_id(session.session_id)
            client.active_session = active_session
            await _enforce_session_mode(
                connection,
                engine,
                client.approval,
                active_session,
                session.modes,
                startup_deadline,
                timeout,
            )
            await client.drain_updates(startup_deadline, timeout)
            client.begin_prompt()
            try:
                response = await _prompt_until_done(
                    connection,
                    active_session,
                    prompt,
                    deadline,
                    timeout,
                    client.cancelled,
                )
                await client.drain_updates(deadline, timeout)
            finally:
                client.end_prompt()
            result = {
                "session_id": active_session,
                "resumed": resumed,
                "stop_reason": response.stop_reason,
                "result": client.message_text(),
            }
    except Exception as exc:
        client.revoke()
        failure = exc
    finally:
        await _finish_stderr(stderr_task)

    if failure is not None:
        if (
            engine == "gemini"
            and isinstance(failure, TimeoutError)
            and stderr_signals["authentication"]
        ):
            message = (
                "Authentication required; configure Gemini CLI before using "
                "ACP (interactive login is disabled)."
            )
        else:
            message = str(failure) or failure.__class__.__name__
        raise RuntimeError(message) from failure
    assert result is not None
    return result


async def _enforce_session_mode(
    connection,
    engine: str,
    approval: str,
    session_id: str,
    modes,
    deadline: float,
    timeout: int,
) -> None:
    required = required_mode(engine, approval)
    if required is None:
        return
    if modes is None:
        raise RuntimeError(f"{engine} did not advertise permission modes")
    available = {mode.id for mode in modes.available_modes}
    if required not in available:
        raise RuntimeError(
            f"{engine} does not offer required permission mode {required!r}"
        )
    if modes.current_mode_id != required:
        await _before_deadline(
            connection.set_session_mode(session_id, required), deadline, timeout
        )


async def _before_deadline(awaitable, deadline: float, timeout: int):
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining <= 0:
        raise TimeoutError(f"run timed out after {timeout}s")
    try:
        return await asyncio.wait_for(awaitable, timeout=remaining)
    except asyncio.TimeoutError as exc:
        raise TimeoutError(f"run timed out after {timeout}s") from exc


async def _prompt_until_done(
    connection,
    session_id: str,
    prompt: str,
    deadline: float,
    timeout: int,
    cancelled,
):
    if cancelled():
        raise RuntimeError("prompt interrupted")
    task = asyncio.create_task(connection.prompt(session_id, [acp.text_block(prompt)]))
    try:
        while not task.done():
            if cancelled():
                await _cancel(connection, session_id)
                raise RuntimeError("prompt interrupted")
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                await _cancel(connection, session_id)
                raise TimeoutError(f"run timed out after {timeout}s")
            await asyncio.wait({task}, timeout=min(_POLL_SECONDS, remaining))
        return task.result()
    finally:
        if not task.done():
            task.cancel()
            with suppress(BaseException):
                await task


async def _cancel(connection, session_id: str) -> None:
    with suppress(Exception):
        await asyncio.wait_for(connection.cancel(session_id), timeout=1)


async def _drain_stderr(
    reader: asyncio.StreamReader, signals: dict[str, bool]
) -> None:
    while chunk := await reader.read(8192):
        lowered = chunk.lower()
        if any(
            marker in lowered
            for marker in (b"authentication", b"credential", b"oauth", b"api key")
        ):
            signals["authentication"] = True


async def _finish_stderr(task: asyncio.Task | None) -> None:
    if task is None:
        return
    try:
        await asyncio.wait_for(task, timeout=2)
    except asyncio.TimeoutError:
        task.cancel()
        with suppress(BaseException):
            await task
    except Exception:
        return


class ToolClient:
    """ACP client callback that exposes one bounded native child-activity view."""

    def __init__(self, agent, approval: str) -> None:
        self.agent = agent
        self.approval = approval
        self.active_session = ""
        self._messages: list[str] = []
        self._message_id: str | None = None
        self._message_bytes = 0
        self._message_chunks = 0
        self._message_truncated = False
        self._tool_titles: dict[str, str] = {}
        self._event_count = 0
        self._events_disabled = False
        self._in_prompt = False
        self._updates_seen = 0
        self._updates_handled = 0

    def observe_stream(self, event) -> None:
        """Count updates before their independently scheduled callbacks run."""
        if (
            getattr(event.direction, "value", "") == "incoming"
            and event.message.get("method") == "session/update"
        ):
            self._updates_seen += 1

    async def drain_updates(self, deadline: float, timeout: int) -> None:
        """Wait for every update received before an RPC response boundary."""
        target = self._updates_seen
        while self._updates_handled < target:
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"run timed out after {timeout}s")
            await asyncio.sleep(0)

    async def session_update(
        self, session_id: str, update: Any, **_kwargs: Any
    ) -> None:
        try:
            if not self._in_prompt or (
                self.active_session and session_id != self.active_session
            ):
                return
            if isinstance(update, AgentMessageChunk):
                if isinstance(update.content, TextContentBlock):
                    self._append_message(update.content.text, update.message_id)
                return
            if isinstance(update, ToolCallStart):
                self._forward_tool_start(update)
                return
            if isinstance(update, ToolCallProgress):
                self._forward_tool_progress(update)
        finally:
            self._updates_handled += 1

    async def request_permission(
        self,
        session_id: str,
        tool_call: ToolCallUpdate,
        options: list[PermissionOption],
        **_kwargs: Any,
    ) -> RequestPermissionResponse:
        if (
            not self._in_prompt
            or
            not tool_call.tool_call_id
            or (self.active_session and session_id != self.active_session)
        ):
            return _cancelled_permission()
        selected = await self._select_permission(tool_call, options)
        if selected is None:
            return _cancelled_permission()
        return RequestPermissionResponse(
            outcome=AllowedOutcome(outcome="selected", optionId=selected)
        )

    async def _select_permission(
        self, tool_call: ToolCallUpdate, options: list[PermissionOption]
    ) -> str | None:
        allow = _option(options, "allow_once")
        reject = _option(options, "reject_once") or _option(options, "reject_always")
        if self.approval == "deny":
            return reject
        if self.approval == "auto":
            return allow
        if allow is None:
            return None
        requester = (
            getattr(self.agent, "current_session", {}).get("requester")
            if self.agent is not None
            else None
        )
        if requester and requester.get("level") != "admin":
            return reject
        io = getattr(self.agent, "io", None) if self.agent is not None else None
        if io is None or not callable(getattr(io, "cancel", None)):
            return reject
        details = {
            "title": _bounded_text(tool_call.title or "", _EVENT_TEXT_LIMIT),
            "tool_call_id": _event_id(tool_call.tool_call_id),
            "input_preview": _input_preview(tool_call.raw_input),
        }
        try:
            approved = bool(await asyncio.to_thread(
                io.request_approval, "acp_agent", details
            ))
        except Exception:
            approved = False
        return allow if approved else reject

    def _forward_tool_start(self, update: ToolCallStart) -> None:
        if not update.tool_call_id:
            return
        title = _bounded_text(update.title or "acp", _EVENT_TEXT_LIMIT)
        tool_id = _event_id(update.tool_call_id)
        if len(self._tool_titles) < _ACTIVE_TOOL_LIMIT:
            self._tool_titles[tool_id] = title
        self._emit(
            "tool_call",
            tool_id=tool_id,
            name=title,
            args={},
            status="in_progress",
        )

    def _forward_tool_progress(self, update: ToolCallProgress) -> None:
        if not update.tool_call_id:
            return
        tool_id = _event_id(update.tool_call_id)
        title = _bounded_text(
            update.title or self._tool_titles.get(tool_id, "acp"),
            _EVENT_TEXT_LIMIT,
        )
        if update.status not in ("completed", "failed"):
            self._emit(
                "tool_call",
                tool_id=tool_id,
                name=title,
                args={},
                status="in_progress",
            )
            return
        self._tool_titles.pop(tool_id, None)
        self._emit(
            "tool_result",
            tool_id=tool_id,
            status=update.status,
            result=title,
        )

    def _emit(self, event_type: str, **fields: Any) -> None:
        if self._events_disabled or self._event_count >= _EVENT_LIMIT:
            return
        io = getattr(self.agent, "io", None) if self.agent is not None else None
        if io is not None:
            self._event_count += 1
            try:
                io.log(event_type, **fields)
            except Exception:
                self._events_disabled = True

    def message_text(self) -> str:
        text = "".join(self._messages)
        if self._message_truncated:
            remaining = _RESULT_LIMIT - len(_TRUNCATED_SUFFIX.encode("utf-8"))
            text = _bounded_text(text, remaining) + _TRUNCATED_SUFFIX
        return text

    def _append_message(self, text: str, message_id: str | None) -> None:
        if not text:
            return
        if message_id is not None:
            bounded_id = _event_id(message_id)
            if bounded_id != self._message_id:
                self._reset_message()
                self._message_id = bounded_id
        if self._message_chunks >= _MESSAGE_CHUNK_LIMIT:
            self._message_truncated = True
            return
        remaining = _RESULT_LIMIT - self._message_bytes
        if remaining <= 0:
            self._message_truncated = True
            return
        chunk = _bounded_text(text, remaining)
        self._messages.append(chunk)
        self._message_chunks += 1
        used = len(chunk.encode("utf-8"))
        self._message_bytes += used
        if used < len(text.encode("utf-8")):
            self._message_truncated = True

    def begin_prompt(self) -> None:
        """Discard updates received before this delegated turn starts."""
        self._reset_message()
        self._message_chunks = 0
        self._tool_titles.clear()
        self._event_count = 0
        self._events_disabled = False
        self._in_prompt = True

    def _reset_message(self) -> None:
        self._messages.clear()
        self._message_id = None
        self._message_bytes = 0
        self._message_truncated = False

    def end_prompt(self) -> None:
        self._in_prompt = False

    def cancelled(self) -> bool:
        check = getattr(getattr(self.agent, "io", None), "is_cancelled", None)
        return bool(check()) if callable(check) else False

    def revoke(self) -> None:
        io = getattr(self.agent, "io", None) if self.agent is not None else None
        cancel = getattr(io, "cancel", None)
        if callable(cancel):
            cancel()


def _option(options: list[PermissionOption], kind: str) -> str | None:
    for option in options:
        if option.kind == kind:
            return option.option_id
    return None


def _cancelled_permission() -> RequestPermissionResponse:
    return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))


def _bounded_text(value: str, limit: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore")


def _event_id(value: str) -> str:
    if len(value.encode("utf-8")) <= _EVENT_TEXT_LIMIT:
        return value
    return "acp-" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _input_preview(value: Any) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError, OverflowError, RecursionError):
        rendered = "<unavailable>"
    return _bounded_text(rendered, _EVENT_TEXT_LIMIT)


def _session_id(value: str) -> str:
    if not value or len(value.encode("utf-8")) > _SESSION_ID_LIMIT:
        raise RuntimeError("ACP agent returned an invalid session ID")
    return value


def envelope(
    engine: str,
    session_id: str = "",
    resumed: bool = False,
    stop_reason: str = "",
    result: str = "",
    error: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "engine": engine,
        "session_id": session_id,
        "resumed": resumed,
        "stop_reason": stop_reason,
        "result": result,
    }
    if error:
        payload["error"] = _bounded_text(error, _ERROR_LIMIT)
    return json.dumps(payload)
