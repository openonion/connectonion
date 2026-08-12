"""Expose Claude Code to co ai without exposing its permission policy."""

import json
from pathlib import Path

from connectonion.core.approval_modes import (
    DANGER_FULL_ACCESS_PERMISSION_PROFILE,
    READ_ONLY_PERMISSION_PROFILE,
    WORKSPACE_PERMISSION_PROFILE,
    has_valid_full_access_grant,
    legacy_permission_profile_id,
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
    try:
        profile = legacy_permission_profile_id(
            session.get("mode", READ_ONLY_PERMISSION_PROFILE)
        )
    except ValueError:
        profile = READ_ONLY_PERMISSION_PROFILE
    if (
        profile == DANGER_FULL_ACCESS_PERMISSION_PROFILE
        and not has_valid_full_access_grant(session)
    ):
        profile = READ_ONLY_PERMISSION_PROFILE
    permission_mode = {
        READ_ONLY_PERMISSION_PROFILE: "default",
        WORKSPACE_PERMISSION_PROFILE: "acceptEdits",
        DANGER_FULL_ACCESS_PERMISSION_PROFILE: "auto",
    }[profile]
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
