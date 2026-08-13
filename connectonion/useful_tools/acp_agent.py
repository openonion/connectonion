"""Run ACP coding agents through a bounded, operator-owned client edge."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ._acp_agent_client import (
    APPROVAL_MODES,
    ToolClient,
    engine_environment,
    envelope,
    run_agent,
    validate_inputs,
)


@dataclass(frozen=True)
class EngineSpec:
    command: tuple[str, ...]
    launcher: str
    credential_hint: str | None
    supported_auth: tuple[str, ...]
    adapter_version: str | None
    supported_approval_modes: tuple[str, ...]
    supports_resume: bool


ENGINES = {
    "claude-code": EngineSpec(
        command=(
            "npx",
            "--yes",
            "@agentclientprotocol/claude-agent-acp@0.66.0",
        ),
        launcher="npx",
        credential_hint="~/.claude/.credentials.json",
        supported_auth=("Claude CLI login", "ANTHROPIC_API_KEY"),
        adapter_version="0.66.0",
        supported_approval_modes=APPROVAL_MODES,
        supports_resume=True,
    ),
    "codex": EngineSpec(
        command=("npx", "--yes", "@agentclientprotocol/codex-acp@1.1.14"),
        launcher="npx",
        credential_hint="~/.codex/auth.json",
        supported_auth=("Codex CLI login", "CODEX_API_KEY", "OPENAI_API_KEY"),
        adapter_version="1.1.14",
        supported_approval_modes=("auto",),
        supports_resume=True,
    ),
    "gemini": EngineSpec(
        command=("npx", "--yes", "@google/gemini-cli@0.55.1", "--acp"),
        launcher="npx",
        # A generic OAuth file is not a useful readiness signal: Google stopped
        # serving individual Gemini CLI OAuth accounts on 2026-06-18.
        credential_hint=None,
        supported_auth=("Gemini API key", "Vertex AI", "enterprise Code Assist"),
        adapter_version="0.55.1",
        supported_approval_modes=APPROVAL_MODES,
        supports_resume=False,
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
            "credential_file_present": (
                Path(spec.credential_hint).expanduser().is_file()
                if available and spec.credential_hint
                else False
            ),
            "auth_check": "configuration hint only; live request required",
            "supported_auth": list(spec.supported_auth),
            "adapter_version": spec.adapter_version,
            "supported_approval_modes": list(spec.supported_approval_modes),
            "supports_resume": spec.supports_resume,
        })
    return json.dumps({"engines": rows})


class ACPAgent:
    """Operator-configured ACP tool.

    ``command`` is an argv sequence, never a shell string. When omitted, the
    model may select one of the exact-version recipes in :data:`ENGINES`.
    """

    def __init__(
        self,
        *,
        command: Sequence[str] | None = None,
        name: str = "custom",
        approval: str = "manual",
        workspace: str | Path | None = None,
    ) -> None:
        if approval not in APPROVAL_MODES:
            raise ValueError(f"Invalid approval {approval!r}; use {APPROVAL_MODES}.")
        if command is not None and isinstance(command, (str, bytes)):
            raise TypeError("ACP command must be an argv sequence, not a shell string.")
        argv = tuple(command or ())
        if command is not None and (
            not argv or not all(isinstance(value, str) and value for value in argv)
        ):
            raise ValueError("ACP command must contain non-empty argv strings.")
        if not isinstance(name, str) or not name:
            raise ValueError("ACP engine name must be a non-empty string.")
        self._workspace = _resolve_workspace(workspace)
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
        """Run or resume one named ACP coding-agent turn."""
        error = validate_inputs(prompt, engine, session_id, cwd, timeout)
        if error:
            return envelope(
                engine if isinstance(engine, str) else "",
                session_id=session_id if isinstance(session_id, str) else "",
                error=error,
            )
        selected, command = self._resolve_engine(engine)
        if command is None:
            return envelope(
                selected,
                session_id=session_id,
                error=f"Unknown engine {selected!r}. Use one of {sorted(ENGINES)}.",
            )
        if self._command is None:
            spec = ENGINES[selected]
            supported = spec.supported_approval_modes
            if self._approval not in supported:
                return envelope(
                    selected,
                    session_id=session_id,
                    error=(
                        f"codex-acp@{ENGINES[selected].adapter_version} supports "
                        "only operator-selected 'auto'; its manual/deny modes do "
                        "not gate shell or network actions. Use the native codex "
                        "tool for approval-aware delegation."
                    ),
                )
            if session_id and not spec.supports_resume:
                return envelope(
                    selected,
                    session_id=session_id,
                    error=(
                        f"@google/gemini-cli@{spec.adapter_version} does not "
                        "persist ACP sessions across child processes; start a "
                        "new Gemini turn without session_id."
                    ),
                )

        try:
            workspace = self._workspace
            requested = Path(cwd).expanduser() if cwd else workspace
            if not requested.is_absolute():
                requested = workspace / requested
            working_directory = requested.resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as exc:
            return envelope(
                selected,
                session_id=session_id,
                error=f"Working directory is unavailable: {exc}",
            )
        if not working_directory.is_dir():
            return envelope(
                selected,
                session_id=session_id,
                error=f"Working directory is not a directory: {working_directory}",
            )
        if not working_directory.is_relative_to(workspace):
            return envelope(
                selected,
                session_id=session_id,
                error=f"Working directory must stay inside workspace: {workspace}",
            )
        if shutil.which(command[0]) is None:
            return envelope(
                selected,
                session_id=session_id,
                error=f"ACP launcher {command[0]!r} was not found on PATH.",
            )

        client = ToolClient(agent, self._approval)
        try:
            result = asyncio.run(run_agent(
                command,
                selected,
                prompt,
                session_id,
                working_directory,
                timeout,
                client,
                engine_environment(selected, self._approval),
            ))
        except Exception as exc:
            return envelope(
                selected,
                session_id=session_id,
                error=f"ACP {selected}: {exc}",
            )
        if self._command is None and not ENGINES[selected].supports_resume:
            result["session_id"] = ""
        return envelope(selected, **result)

    def _resolve_engine(self, engine: str) -> tuple[str, tuple[str, ...] | None]:
        if self._command is not None:
            if engine and engine != self._name:
                return engine, None
            return self._name, self._command
        selected = engine or "claude-code"
        spec = ENGINES.get(selected)
        return selected, spec.command if spec else None


def _resolve_workspace(workspace: str | Path | None) -> Path:
    if workspace is None:
        workspace = Path(os.getcwd())
    if not isinstance(workspace, (str, Path)):
        raise TypeError("ACP workspace must be a path string or Path.")
    try:
        root = Path(workspace).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"ACP workspace is unavailable: {exc}") from exc
    if not root.is_dir():
        raise ValueError(f"ACP workspace is not a directory: {root}")
    return root


def acp_agent(
    prompt: str,
    engine: str = "",
    session_id: str = "",
    cwd: str = "",
    timeout: int = 600,
    agent=None,
) -> str:
    """Run a named ACP engine with operator-approved permissions."""
    workspace = (
        getattr(agent, "_delegation_workspace", Path.cwd())
        if agent is not None
        else Path.cwd()
    )
    return ACPAgent(workspace=workspace).acp_agent(
        prompt=prompt,
        engine=engine,
        session_id=session_id,
        cwd=cwd,
        timeout=timeout,
        agent=agent,
    )
