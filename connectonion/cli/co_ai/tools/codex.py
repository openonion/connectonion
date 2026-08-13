"""Expose Codex to co ai without exposing a second permission policy."""

from pathlib import Path

from connectonion.core.approval_modes import (
    DANGER_FULL_ACCESS_PERMISSION_PROFILE,
    READ_ONLY_PERMISSION_PROFILE,
    WORKSPACE_PERMISSION_PROFILE,
    has_valid_full_access_grant,
    legacy_permission_profile_id,
)
from connectonion.useful_tools import codex as run_codex


def codex(
    prompt: str,
    cwd: str,
    session_id: str = "",
    model: str = "",
    timeout: int = 600,
    agent=None,
) -> str:
    """Delegate a coding task to Codex, optionally resuming its session.

    Pass the returned ``session_id`` back on a later call. The current co ai
    mode owns Codex's sandbox and approval policy; they are intentionally not
    model-selectable arguments.
    """
    session = getattr(agent, "current_session", {})
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
    sandbox, approval = {
        READ_ONLY_PERMISSION_PROFILE: ("read-only", "manual"),
        WORKSPACE_PERMISSION_PROFILE: ("workspace-write", "manual"),
        DANGER_FULL_ACCESS_PERMISSION_PROFILE: ("danger-full-access", "deny"),
    }[profile]
    requester = session.get("requester")
    if requester and requester.get("level") != "admin":
        # Contacts may use Codex for inspection, but cannot select a mode that
        # writes or answer an operator-owned nested approval prompt.
        sandbox, approval = "read-only", "deny"
    working_directory = str(Path(cwd).expanduser().resolve())
    return run_codex(
        prompt=prompt,
        session_id=session_id,
        cwd=working_directory,
        sandbox=sandbox,
        model=model,
        timeout=timeout,
        approval=approval,
        agent=agent,
    )
