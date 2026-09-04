"""Expose Claude Code to co ai without exposing its permission policy."""

from pathlib import Path

from connectonion.core.mode import AUTO, FULL_ACCESS, READ_ONLY, mode_of
from connectonion.useful_tools.claude_code import _run_claude_code


def claude_code(
    prompt: str,
    cwd: str,
    session_id: str = "",
    model: str = "",
    timeout: int = 600,
    agent=None,
) -> str:
    """Delegate a coding task to Claude Code and optionally resume it.

    Pass the returned ``session_id`` back on a later call. The current co ai
    mode owns Claude Code's permission mode; it is not model-selectable.
    Provider-private permission values are translated only at this boundary.
    """
    session = getattr(agent, "current_session", {}) or {}
    current = mode_of(session)
    permission_mode = {
        READ_ONLY: "default",
        AUTO: "acceptEdits",
        FULL_ACCESS: "auto",
    }[current]
    return _run_claude_code(
        prompt=prompt,
        session_id=session_id,
        cwd=cwd,
        permission_mode=permission_mode,
        model=model,
        timeout=timeout,
        agent=agent,
        workspace=(
            getattr(agent, "_delegation_workspace", Path.cwd())
            if agent is not None
            else None
        ),
    )
