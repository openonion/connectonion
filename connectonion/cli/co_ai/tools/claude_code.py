"""Expose Claude Code to co ai without exposing its permission policy."""

import json

from connectonion.core.approval_modes import (
    AUTO_APPROVE_MODE,
    DEFAULT_MODE,
    FULL_ACCESS_MODE,
)
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
    Hosted non-admin requesters cannot start the local coding subprocess.
    """
    session = getattr(agent, "current_session", {}) or {}
    requester = session.get("requester")
    if requester and requester.get("level") != "admin":
        return json.dumps(
            {
                "provider": "claude_code",
                "session_id": session_id,
                "resumed": bool(session_id),
                "status": "error",
                "result": "",
                "error": (
                    "Claude Code delegation is available only to the operator "
                    "in a hosted session."
                ),
                "exit_code": -1,
                "usage": {},
                "total_cost_usd": None,
            }
        )
    permission_mode = {
        DEFAULT_MODE: "default",
        AUTO_APPROVE_MODE: "acceptEdits",
        FULL_ACCESS_MODE: "auto",
    }.get(session.get("mode"), "default")
    return _run_claude_code(
        prompt=prompt,
        session_id=session_id,
        cwd=cwd,
        permission_mode=permission_mode,
        model=model,
        timeout=timeout,
        agent=agent,
    )
