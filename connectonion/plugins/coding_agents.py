"""Provider plugins for bounded Codex and Claude Code delegation."""

from __future__ import annotations

import json
import time
from enum import Enum
from pathlib import Path
from typing import Any

from ..core.events import on_agent_ready
from ..useful_tools.claude_code import _run_claude_code
from ..useful_tools.codex import codex as _run_codex


class PermissionMode(str, Enum):
    """The three authority choices exposed to operators and user interfaces."""

    MANUAL = "manual"
    AUTO_APPROVE = "auto_approve"
    FULL_ACCESS = "full_access"


_COMPATIBILITY_MODES = {
    ":read-only": PermissionMode.MANUAL,
    ":workspace": PermissionMode.AUTO_APPROVE,
    ":danger-full-access": PermissionMode.FULL_ACCESS,
}


def _permission_mode(value: PermissionMode | str) -> PermissionMode:
    if isinstance(value, PermissionMode):
        return value
    compatibility = _COMPATIBILITY_MODES.get(value)
    if compatibility is not None:
        return compatibility
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
        permission_mode: PermissionMode | str = PermissionMode.MANUAL,
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
            candidate.relative_to(self.workspace)
        except (OSError, RuntimeError, ValueError):
            return None, f"Working directory must stay inside workspace {self.workspace}."
        if not candidate.is_dir():
            return None, f"Working directory is not a directory: {candidate}."
        return candidate, ""

    def _invoke(self, agent, prompt: str, run) -> str:
        started = time.monotonic()
        parent_id = _parent_tool_call_id(agent)
        invocation_id = f"{self.provider}:{parent_id}" if parent_id else f"{self.provider}:untracked"
        _emit(
            agent,
            "provider_invocation",
            invocationId=invocation_id,
            parentToolCallId=parent_id,
            provider=self.provider,
            providerDisplayName=self.display_name,
            taskSummary=_bounded(prompt, 500),
            permissionMode=self.permission_mode.value,
            status="running",
        )
        try:
            result = run()
        except BaseException as exc:
            _emit(
                agent,
                "provider_invocation",
                invocationId=invocation_id,
                parentToolCallId=parent_id,
                provider=self.provider,
                providerDisplayName=self.display_name,
                status="cancelled" if exc.__class__.__name__ == "UserInterrupt" else "failed",
                elapsedMs=round((time.monotonic() - started) * 1000),
                error=_bounded(exc, 1000),
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
            result=_bounded(envelope.get("result", envelope.get("last_message", "")), 4000),
            error=_bounded(error or "", 1000),
        )
        return result


class CodexPlugin(_CodingAgentPlugin):
    """Install a Codex tool whose workspace and authority are operator-owned."""

    provider = "codex"
    display_name = "Codex"

    def codex(
        self,
        prompt: str,
        cwd: str = "",
        session_id: str = "",
        model: str = "",
        timeout: int = 600,
        agent=None,
    ) -> str:
        """Run or resume Codex inside the operator-configured workspace."""
        working_directory, error = self._cwd(cwd)
        if error:
            return json.dumps({"provider": "codex", "session_id": session_id, "error": error})
        sandbox, approval = {
            PermissionMode.MANUAL: ("workspace-write", "manual"),
            PermissionMode.AUTO_APPROVE: ("workspace-write", "auto"),
            PermissionMode.FULL_ACCESS: ("danger-full-access", "auto"),
        }[self.permission_mode]
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
        )


class ClaudeCodePlugin(_CodingAgentPlugin):
    """Install a Claude Code tool with an operator-owned permission ceiling."""

    provider = "claude_code"
    display_name = "Claude Code"

    def claude_code(
        self,
        prompt: str,
        cwd: str = "",
        session_id: str = "",
        model: str = "",
        timeout: int = 600,
        agent=None,
    ) -> str:
        """Run or resume Claude Code inside the configured workspace."""
        working_directory, error = self._cwd(cwd)
        if error:
            return json.dumps({"provider": "claude_code", "session_id": session_id, "error": error})
        provider_mode = {
            PermissionMode.MANUAL: "manual",
            PermissionMode.AUTO_APPROVE: "acceptEdits",
            PermissionMode.FULL_ACCESS: "auto",
        }[self.permission_mode]
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
        )


def _parent_tool_call_id(agent) -> str | None:
    session = getattr(agent, "current_session", None)
    value = session.get("_active_tool_call_id") if isinstance(session, dict) else None
    return value if isinstance(value, str) and value else None


def _emit(agent, event_type: str, **fields: Any) -> None:
    record = getattr(agent, "_record_trace", None)
    if callable(record) and isinstance(getattr(agent, "current_session", None), dict):
        record({"type": event_type, **fields})
        return
    io = getattr(agent, "io", None)
    if io is not None:
        io.log(event_type, **fields)


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
