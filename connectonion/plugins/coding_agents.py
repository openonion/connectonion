"""Provider plugins for bounded Codex and Claude Code delegation.

LLM-Note:
  This is the lifecycle writer for the OIP Work Room: it creates the monotonic
  provider state revisions consumed by @connectonion/react and O Chat. Native
  event producers live in useful_tools/codex.py and useful_tools/claude_code.py;
  image validation/cache rules live in core/provider_events.py.
"""

from __future__ import annotations

import json
import time
from enum import Enum
from pathlib import Path
from typing import Any

from ..core.events import on_agent_ready
from ..core.mode import AUTO, FULL_ACCESS, READ_ONLY, mode_of
from ..core.provider_events import (
    clear_provider_activity_history,
    clear_provider_artifact,
    next_provider_state_revision,
    provider_artifact_for_state,
    provider_status_summary,
    provider_task_title,
    provider_terminal_summary,
    take_provider_activity_history,
)
from ..useful_tools.claude_code import _run_claude_code
from ..useful_tools.codex import codex as _run_codex


class PermissionMode(str, Enum):
    """The three authority choices exposed to operators and user interfaces."""

    READ_ONLY = READ_ONLY
    AUTO = AUTO
    FULL_ACCESS = FULL_ACCESS


def _permission_mode(value: PermissionMode | str) -> PermissionMode:
    if isinstance(value, PermissionMode):
        return value
    try:
        return PermissionMode(value)
    except ValueError as exc:
        choices = ", ".join(mode.value for mode in PermissionMode)
        raise ValueError(f"Unknown permission mode {value!r}; use {choices}.") from exc


class _CodingAgentPlugin(list):
    """Event-plugin lifecycle plus a model-callable provider tool.

    Subclassing ``list`` preserves the existing event-plugin protocol while
    making installation explicit and configurable. The registered tool is a
    bound method, so operator state never appears in its model-visible schema.
    """

    provider: str
    display_name: str

    def __init__(
        self,
        *,
        permission_mode: PermissionMode | str = PermissionMode.AUTO,
        workspace: str | Path | None = None,
    ) -> None:
        self.permission_mode = _permission_mode(permission_mode)
        self.workspace = Path(workspace or Path.cwd()).expanduser().resolve()
        if not self.workspace.is_dir():
            raise ValueError(f"Plugin workspace is not a directory: {self.workspace}")
        super().__init__([self._install])

    @on_agent_ready
    def _install(self, agent) -> None:
        agent.add_tool(getattr(self, self.provider))
        installed = getattr(agent, "installed_plugins", None)
        if installed is None:
            installed = []
            agent.installed_plugins = installed
        installed.append(self)

    def _cwd(self, cwd: str) -> tuple[Path | None, str]:
        try:
            candidate = Path(cwd).expanduser() if cwd else self.workspace
            if not candidate.is_absolute():
                candidate = self.workspace / candidate
            candidate = candidate.resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            return None, "Working directory is unavailable."
        try:
            candidate.relative_to(self.workspace)
        except ValueError:
            return None, "Working directory must stay inside the configured workspace."
        if not candidate.is_dir():
            return None, "Working directory is not a directory."
        return candidate, ""

    def _invoke(
        self,
        agent,
        prompt: str,
        run,
        permission_mode: PermissionMode | None = None,
    ) -> str:
        started = time.monotonic()
        effective_mode = permission_mode or self.permission_mode
        parent_id = _parent_tool_call_id(agent)
        invocation_id = f"{self.provider}:{parent_id}" if parent_id else f"{self.provider}:untracked"
        task_title = provider_task_title(prompt)
        clear_provider_activity_history(agent, invocation_id)
        clear_provider_artifact(agent, invocation_id)
        _emit(
            agent,
            "provider_invocation",
            invocationId=invocation_id,
            parentToolCallId=parent_id,
            provider=self.provider,
            providerDisplayName=self.display_name,
            # Legacy readers use taskSummary, so make that compatibility field
            # safe too. Raw provider instructions never belong in a Work Room.
            taskTitle=task_title,
            taskSummary=task_title,
            currentSummary=provider_status_summary("running"),
            permissionMode=effective_mode.value,
            status="running",
        )
        try:
            result = run()
        except BaseException as exc:
            take_provider_activity_history(agent, invocation_id)
            _emit(
                agent,
                "provider_invocation",
                invocationId=invocation_id,
                parentToolCallId=parent_id,
                provider=self.provider,
                providerDisplayName=self.display_name,
                status="cancelled" if exc.__class__.__name__ == "UserInterrupt" else "failed",
                elapsedMs=round((time.monotonic() - started) * 1000),
                currentSummary=provider_status_summary(
                    "cancelled" if exc.__class__.__name__ == "UserInterrupt" else "failed"
                ),
                errorSummary=provider_terminal_summary(
                    "cancelled" if exc.__class__.__name__ == "UserInterrupt" else "failed"
                ),
            )
            raise
        envelope = _envelope(result)
        error = envelope.get("error")
        status = envelope.get("status")
        if status == "cancelled" or (isinstance(error, str) and "interrupt" in error.lower()):
            terminal = "cancelled"
        elif error or envelope.get("exit_code") not in (None, 0):
            terminal = "failed"
        else:
            terminal = "completed"
        terminal_summary = provider_terminal_summary(
            terminal,
            take_provider_activity_history(agent, invocation_id),
        )
        _emit(
            agent,
            "provider_invocation",
            invocationId=invocation_id,
            parentToolCallId=parent_id,
            provider=self.provider,
            providerDisplayName=self.display_name,
            status=terminal,
            sessionId=_bounded(envelope.get("session_id", ""), 512),
            elapsedMs=round((time.monotonic() - started) * 1000),
            currentSummary=terminal_summary,
            resultSummary=terminal_summary,
            **(
                {"errorSummary": terminal_summary}
                if terminal == "failed"
                else {}
            ),
        )
        return result


class CodexPlugin(_CodingAgentPlugin):
    """Install a Codex tool whose workspace and authority are operator-owned."""

    provider = "codex"
    display_name = "Codex"

    def __init__(
        self,
        *,
        permission_mode: PermissionMode | str = PermissionMode.AUTO,
        workspace: str | Path | None = None,
        use_host_permissions: bool = False,
    ) -> None:
        self.use_host_permissions = use_host_permissions
        super().__init__(permission_mode=permission_mode, workspace=workspace)

    def codex(
        self,
        prompt: str = "",
        cwd: str = "",
        session_id: str = "",
        model: str = "",
        timeout: int = 1800,
        agent=None,
    ) -> str:
        """Run, open, or resume Codex inside the operator-configured workspace."""
        working_directory, error = self._cwd(cwd)
        if error:
            return json.dumps({"provider": "codex", "session_id": session_id, "error": error})
        sandbox, approval, effective_mode = self._policy(agent)
        return self._invoke(
            agent,
            prompt,
            lambda: _run_codex(
                prompt=prompt,
                cwd=str(working_directory),
                session_id=session_id,
                model=model,
                timeout=timeout,
                sandbox=sandbox,
                approval=approval,
                agent=agent,
            ),
            permission_mode=effective_mode,
        )

    def _policy(self, agent) -> tuple[str, str, PermissionMode]:
        if not self.use_host_permissions:
            sandbox, approval = {
                PermissionMode.READ_ONLY: ("read-only", "manual"),
                PermissionMode.AUTO: ("workspace-write", "auto"),
                PermissionMode.FULL_ACCESS: ("danger-full-access", "auto"),
            }[self.permission_mode]
            return sandbox, approval, self.permission_mode

        session = getattr(agent, "current_session", {}) or {}
        current = mode_of(session)
        return {
            READ_ONLY: (
                "read-only", "manual", PermissionMode.READ_ONLY
            ),
            AUTO: (
                "workspace-write", "manual", PermissionMode.AUTO
            ),
            FULL_ACCESS: (
                "danger-full-access", "deny", PermissionMode.FULL_ACCESS
            ),
        }[current]


class ClaudeCodePlugin(_CodingAgentPlugin):
    """Install a Claude Code tool with an operator-owned permission ceiling."""

    provider = "claude_code"
    display_name = "Claude Code"

    def __init__(
        self,
        *,
        permission_mode: PermissionMode | str = PermissionMode.AUTO,
        workspace: str | Path | None = None,
        use_host_permissions: bool = False,
    ) -> None:
        self.use_host_permissions = use_host_permissions
        super().__init__(permission_mode=permission_mode, workspace=workspace)

    def claude_code(
        self,
        prompt: str,
        cwd: str,
        session_id: str = "",
        model: str = "",
        timeout: int = 600,
        agent=None,
    ) -> str:
        """Run or resume Claude Code inside the configured workspace."""
        provider_mode, effective_mode = self._policy(agent)
        working_directory, error = self._cwd(cwd)
        if error:
            return json.dumps({"provider": "claude_code", "session_id": session_id, "error": error})
        return self._invoke(
            agent,
            prompt,
            lambda: _run_claude_code(
                prompt=prompt,
                cwd=str(working_directory),
                session_id=session_id,
                permission_mode=provider_mode,
                model=model,
                timeout=timeout,
                agent=agent,
                workspace=self.workspace,
            ),
            permission_mode=effective_mode,
        )

    def _policy(self, agent) -> tuple[str, PermissionMode]:
        if not self.use_host_permissions:
            return {
                PermissionMode.READ_ONLY: "manual",
                PermissionMode.AUTO: "acceptEdits",
                PermissionMode.FULL_ACCESS: "auto",
            }[self.permission_mode], self.permission_mode

        session = getattr(agent, "current_session", {}) or {}
        current = mode_of(session)
        return {
            READ_ONLY: ("manual", PermissionMode.READ_ONLY),
            AUTO: (
                "acceptEdits", PermissionMode.AUTO
            ),
            FULL_ACCESS: (
                "auto", PermissionMode.FULL_ACCESS
            ),
        }[current]

def _parent_tool_call_id(agent) -> str | None:
    session = getattr(agent, "current_session", None)
    value = session.get("_active_tool_call_id") if isinstance(session, dict) else None
    return value if isinstance(value, str) and value else None


def _emit(agent, event_type: str, **fields: Any) -> dict[str, Any]:
    if event_type == "provider_invocation":
        invocation_id = fields.get("invocationId")
        if isinstance(invocation_id, str) and invocation_id:
            # The same entry is later sent through the live and durable lanes;
            # assign once, before either lane observes it.
            fields["stateRevision"] = next_provider_state_revision(
                agent, invocation_id
            )
            fields.update(_provider_workroom_fields(agent, invocation_id))
    entry = {"type": event_type, **fields}
    record = getattr(agent, "_record_trace", None)
    if callable(record) and isinstance(getattr(agent, "current_session", None), dict):
        record(entry)
        stream_live = getattr(getattr(agent, "io", None), "send_live_trace", None)
        if callable(stream_live):
            stream_live(entry)
    else:
        io = getattr(agent, "io", None)
        if io is not None:
            io.log(event_type, **fields)
    if event_type == "provider_invocation":
        _emit_cached_provider_artifact(agent, entry)
    return entry


def _provider_workroom_fields(agent, invocation_id: str) -> dict[str, str]:
    """Attach a stable, Host-owned conversation grouping to provider lifecycle."""
    session = getattr(agent, "current_session", None)
    if not isinstance(session, dict):
        return {"workroomId": invocation_id}
    workroom_id = session.get("_provider_workroom_id", invocation_id)
    fields = {
        "workroomId": workroom_id
        if isinstance(workroom_id, str) and workroom_id
        else invocation_id,
    }
    continuation_of = session.get("_provider_continuation_of")
    if isinstance(continuation_of, str) and continuation_of:
        fields["continuationOf"] = continuation_of
    return fields


def _emit_cached_provider_artifact(agent, lifecycle: dict[str, Any]) -> None:
    """Keep a real latest preview attached after a lifecycle revision changes."""
    artifact = provider_artifact_for_state(
        agent,
        provider=lifecycle.get("provider"),
        invocation_id=lifecycle.get("invocationId"),
        parent_tool_call_id=lifecycle.get("parentToolCallId"),
        state_revision=lifecycle.get("stateRevision"),
    )
    if artifact is not None:
        _emit(agent, "provider_artifact", **_without_type(artifact))


def _without_type(event: dict[str, Any]) -> dict[str, Any]:
    """Pass a canonical event through the local emitter without a duplicate type."""
    return {key: value for key, value in event.items() if key != "type"}


def _envelope(result: Any) -> dict[str, Any]:
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
            return parsed if isinstance(parsed, dict) else {"result": result}
        except json.JSONDecodeError:
            return {"result": result}
    return result if isinstance(result, dict) else {"result": str(result)}


def _bounded(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"
