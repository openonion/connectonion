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
