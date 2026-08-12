"""Run ACP coding agents through the official typed client SDK.

Named engines are safe, exact-version launch recipes.  Custom commands and the
permission policy belong to the operator-created :class:`ACPAgent` instance;
they are deliberately absent from the model-facing tool signature.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import acp
from acp.schema import (
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentThoughtChunk,
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


APPROVAL_MODES = ("manual", "auto", "deny")
_STDIO_LIMIT = 10 * 1024 * 1024
_STDERR_LIMIT = 64 * 1024
_POLL_SECONDS = 0.1


@dataclass(frozen=True)
class EngineSpec:
    command: tuple[str, ...]
    launcher: str
    auth_hint: str
    adapter_version: str | None


ENGINES = {
    "claude-code": EngineSpec(
        command=(
            "npx",
            "--yes",
            "@agentclientprotocol/claude-agent-acp@0.66.0",
        ),
        launcher="npx",
        auth_hint="~/.claude/.credentials.json",
        adapter_version="0.66.0",
    ),
    "codex": EngineSpec(
        command=("npx", "--yes", "@agentclientprotocol/codex-acp@1.1.14"),
        launcher="npx",
        auth_hint="~/.codex/auth.json",
        adapter_version="1.1.14",
    ),
    "gemini": EngineSpec(
        command=("gemini", "--experimental-acp"),
        launcher="gemini",
        auth_hint="~/.gemini/oauth_creds.json",
        adapter_version=None,
    ),
}


def engine_status() -> str:
    """Report launcher availability and an explicitly heuristic auth hint."""
    rows = []
    for name, spec in ENGINES.items():
        available = shutil.which(spec.launcher) is not None
        rows.append({
            "engine": name,
            "launcher_available": available,
            "authenticated_hint": (
                Path(spec.auth_hint).expanduser().is_file() if available else False
            ),
            "auth_check": "credential file presence only",
            "adapter_version": spec.adapter_version,
        })
    return json.dumps({"engines": rows})


class ACPAgent:
    """Operator-configured ACP tool.

    ``command`` is an argv sequence, never a shell string.  When omitted, the
    model may select one of the exact-version recipes in :data:`ENGINES`.
    """

    def __init__(
        self,
        *,
        command: Sequence[str] | None = None,
        name: str = "custom",
        approval: str = "manual",
    ) -> None:
        if approval not in APPROVAL_MODES:
            raise ValueError(f"Invalid approval {approval!r}; use {APPROVAL_MODES}.")
        if command is not None and isinstance(command, (str, bytes)):
            raise TypeError("ACP command must be an argv sequence, not a shell string.")
        argv = tuple(command or ())
        if command is not None and (not argv or not all(isinstance(v, str) and v for v in argv)):
            raise ValueError("ACP command must contain non-empty argv strings.")
        if not isinstance(name, str) or not name:
            raise ValueError("ACP engine name must be a non-empty string.")
        self._command = argv or None
        self._name = name
        self._approval = approval

    def acp_agent(
        self,
        prompt: str,
        engine: str = "",
        session_id: str = "",
        cwd: str = "",
        timeout: int = 600,
        agent=None,
    ) -> str:
        """Run or resume an ACP coding-agent turn.

        The returned JSON includes ``session_id`` for an exact later resume.
        Named engines are ``claude-code``, ``codex``, and ``gemini``.
        """
        error = _validate_inputs(prompt, session_id, cwd, timeout)
        selected, command = self._resolve_engine(engine)
        if error or command is None:
            return _envelope(selected, session_id=session_id, error=error or (
                f"Unknown engine {selected!r}. Use one of {sorted(ENGINES)}."
            ))

        try:
            working_directory = Path(cwd or os.getcwd()).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as exc:
            return _envelope(
                selected,
                session_id=session_id,
                error=f"Working directory is unavailable: {exc}",
            )
        if not working_directory.is_dir():
            return _envelope(
                selected,
                session_id=session_id,
                error=f"Working directory is not a directory: {working_directory}",
            )
        if shutil.which(command[0]) is None:
            return _envelope(
                selected,
                session_id=session_id,
                error=f"ACP launcher {command[0]!r} was not found on PATH.",
            )

        client = _ToolClient(agent, self._approval)
        try:
            result = asyncio.run(_run_agent(
                command,
                selected,
                prompt,
                session_id,
                working_directory,
                timeout,
                client,
                _engine_environment(selected, self._approval),
            ))
        except Exception as exc:
            return _envelope(
                selected,
                session_id=session_id,
                error=f"ACP {selected}: {exc}",
            )
        return _envelope(selected, **result)

    def _resolve_engine(self, engine: str) -> tuple[str, tuple[str, ...] | None]:
        if self._command is not None:
            if engine and engine != self._name:
                return engine, None
            return self._name, self._command
        selected = engine or "claude-code"
        spec = ENGINES.get(selected)
        return selected, spec.command if spec else None


_DEFAULT_TOOL = ACPAgent()


def acp_agent(
    prompt: str,
    engine: str = "",
    session_id: str = "",
    cwd: str = "",
    timeout: int = 600,
    agent=None,
) -> str:
    """Run a named ACP engine with operator-approved permissions."""
    return _DEFAULT_TOOL.acp_agent(
        prompt=prompt,
        engine=engine,
        session_id=session_id,
        cwd=cwd,
        timeout=timeout,
        agent=agent,
    )


def _validate_inputs(prompt: Any, session_id: Any, cwd: Any, timeout: Any) -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        return "Prompt must be a non-empty string."
    if not isinstance(session_id, str):
        return "Session ID must be a string."
    if not isinstance(cwd, str):
        return "Working directory must be a string."
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        return "Timeout must be a positive integer."
    return ""


def _engine_environment(engine: str, approval: str) -> dict[str, str]:
    if engine != "codex":
        return {}
    return {
        "INITIAL_AGENT_MODE": "agent" if approval == "auto" else "read-only",
        "CODEX_CONFIG": json.dumps({"approvals_reviewer": "user"}),
        "NO_BROWSER": "1",
    }


async def _run_agent(
    command: tuple[str, ...],
    engine: str,
    prompt: str,
    session_id: str,
    cwd: Path,
    timeout: int,
    client: "_ToolClient",
    environment: dict[str, str],
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout
    stderr = bytearray()
    stderr_task: asyncio.Task | None = None
    failure: BaseException | None = None
    result: dict[str, Any] | None = None

    try:
        async with acp.spawn_agent_process(
            client,
            command[0],
            *command[1:],
            env=environment,
            cwd=cwd,
            transport_kwargs={"limit": _STDIO_LIMIT, "shutdown_timeout": 2.0},
        ) as (connection, process):
            if process.stderr is not None:
                stderr_task = asyncio.create_task(_drain_stderr(process.stderr, stderr))
            initialized = await _before_deadline(
                connection.initialize(
                    protocol_version=acp.PROTOCOL_VERSION,
                    client_capabilities=ClientCapabilities(),
                    client_info=Implementation(
                        name="connectonion", title="ConnectOnion", version=__version__
                    ),
                ),
                deadline,
                timeout,
            )
            resumed = False
            if session_id:
                if not initialized.agent_capabilities.load_session:
                    raise RuntimeError(f"{engine} does not advertise session/load")
                client.active_session = session_id
                await _before_deadline(
                    connection.load_session(str(cwd), session_id, mcp_servers=[]),
                    deadline,
                    timeout,
                )
                active_session = session_id
                resumed = True
            else:
                created = await _before_deadline(
                    connection.new_session(str(cwd), mcp_servers=[]),
                    deadline,
                    timeout,
                )
                active_session = created.session_id
            client.active_session = active_session
            client.begin_prompt()
            response = await _prompt_until_done(
                connection,
                active_session,
                prompt,
                deadline,
                timeout,
                client.cancelled,
            )
            client.finish_thoughts()
            result = {
                "session_id": active_session,
                "resumed": resumed,
                "stop_reason": response.stop_reason,
                "result": client.message_text(),
            }
    except Exception as exc:
        failure = exc
    finally:
        await _finish_stderr(stderr_task)

    if failure is not None:
        detail = stderr.decode(errors="replace").strip().replace("\n", " ")[-1000:]
        message = str(failure) or failure.__class__.__name__
        raise RuntimeError(f"{message}: {detail}" if detail else message) from failure
    assert result is not None
    return result


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


async def _drain_stderr(reader: asyncio.StreamReader, captured: bytearray) -> None:
    while chunk := await reader.read(8192):
        captured.extend(chunk)
        if len(captured) > _STDERR_LIMIT:
            del captured[:-_STDERR_LIMIT]


async def _finish_stderr(task: asyncio.Task | None) -> None:
    if task is None:
        return
    try:
        await asyncio.wait_for(task, timeout=2)
    except asyncio.TimeoutError:
        task.cancel()
        with suppress(BaseException):
            await task


class _ToolClient:
    def __init__(self, agent, approval: str) -> None:
        self.agent = agent
        self.approval = approval
        self.active_session = ""
        self._messages: list[str] = []
        self._thoughts: dict[str, str] = {}
        self._tool_titles: dict[str, str] = {}

    async def session_update(
        self, session_id: str, update: Any, **_kwargs: Any
    ) -> None:
        if self.active_session and session_id != self.active_session:
            return
        if isinstance(update, AgentMessageChunk):
            if isinstance(update.content, TextContentBlock):
                self._messages.append(update.content.text)
            return
        if isinstance(update, AgentThoughtChunk):
            self._forward_thought(update)
            return
        if isinstance(update, AgentPlanUpdate):
            self._emit("plan", entries=[
                entry.model_dump(by_alias=False, exclude_none=True)
                for entry in update.entries
            ])
            return
        if isinstance(update, ToolCallStart):
            self._forward_tool_start(update)
            return
        if isinstance(update, ToolCallProgress):
            self._forward_tool_progress(update)

    async def request_permission(
        self,
        session_id: str,
        tool_call: ToolCallUpdate,
        options: list[PermissionOption],
        **_kwargs: Any,
    ) -> RequestPermissionResponse:
        if self.active_session and session_id != self.active_session:
            return _cancelled_permission()
        selected = self._select_permission(tool_call, options)
        if selected is None:
            return _cancelled_permission()
        return RequestPermissionResponse(
            outcome=AllowedOutcome(outcome="selected", optionId=selected)
        )

    def _select_permission(
        self, tool_call: ToolCallUpdate, options: list[PermissionOption]
    ) -> str | None:
        allow = _first_option(options, "allow")
        reject = _first_option(options, "reject")
        if self.approval == "deny":
            return reject
        if self.approval == "auto":
            return allow
        requester = (
            getattr(self.agent, "current_session", {}).get("requester")
            if self.agent is not None
            else None
        )
        if requester and requester.get("level") != "admin":
            return reject
        io = getattr(self.agent, "io", None) if self.agent is not None else None
        if io is None:
            return reject
        details = {
            "title": tool_call.title or "",
            "tool_call_id": tool_call.tool_call_id,
        }
        try:
            approved = bool(io.request_approval("acp_agent", details))
        except Exception:
            approved = False
        return allow if approved else reject

    def _forward_thought(self, update: AgentThoughtChunk) -> None:
        if not isinstance(update.content, TextContentBlock):
            return
        message_id = update.message_id or "acp-thought"
        text = self._thoughts.get(message_id, "") + update.content.text
        self._thoughts[message_id] = text
        self._emit(
            "thinking", id=message_id, status="running", content=text, kind="acp"
        )

    def finish_thoughts(self) -> None:
        for message_id, text in self._thoughts.items():
            self._emit(
                "thinking", id=message_id, status="done", content=text, kind="acp"
            )

    def _forward_tool_start(self, update: ToolCallStart) -> None:
        self._tool_titles[update.tool_call_id] = update.title
        args = update.raw_input if isinstance(update.raw_input, dict) else {}
        self._emit(
            "tool_call",
            tool_id=update.tool_call_id,
            name=update.title or "acp",
            args=args,
            status="in_progress",
        )

    def _forward_tool_progress(self, update: ToolCallProgress) -> None:
        title = update.title or self._tool_titles.get(update.tool_call_id, "acp")
        if update.status not in ("completed", "failed"):
            self._emit(
                "tool_call",
                tool_id=update.tool_call_id,
                name=title,
                args=update.raw_input if isinstance(update.raw_input, dict) else {},
                status="in_progress",
            )
            return
        result = update.raw_output if update.raw_output is not None else title
        self._emit(
            "tool_result",
            tool_id=update.tool_call_id,
            status=update.status,
            result=result,
        )

    def _emit(self, event_type: str, **fields: Any) -> None:
        io = getattr(self.agent, "io", None) if self.agent is not None else None
        if io is not None:
            io.log(event_type, **fields)

    def message_text(self) -> str:
        return "".join(self._messages)

    def begin_prompt(self) -> None:
        """Discard history replayed by session/load before this turn starts."""
        self._messages.clear()
        self._thoughts.clear()
        self._tool_titles.clear()

    def cancelled(self) -> bool:
        check = getattr(getattr(self.agent, "io", None), "is_cancelled", None)
        return bool(check()) if callable(check) else False


def _first_option(options: list[PermissionOption], prefix: str) -> str | None:
    for option in options:
        if option.kind.startswith(prefix):
            return option.option_id
    return None


def _cancelled_permission() -> RequestPermissionResponse:
    return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))


def _envelope(
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
        payload["error"] = error
    return json.dumps(payload)
