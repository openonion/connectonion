"""Expose the generic ACP child adapter without exposing its authority knobs."""

from pathlib import Path

from connectonion.core.approval_modes import (
    DANGER_FULL_ACCESS_PERMISSION_PROFILE,
    READ_ONLY_PERMISSION_PROFILE,
    has_valid_full_access_grant,
    legacy_permission_profile_id,
)
from connectonion.useful_tools._acp_agent_client import envelope
from connectonion.useful_tools.acp_agent import ACPAgent


def acp_agent(
    prompt: str,
    engine: str,
    cwd: str,
    session_id: str = "",
    timeout: int = 600,
    agent=None,
) -> str:
    """Delegate one turn to a named ACP engine and optionally resume it.

    The current co ai permission profile owns child approval. Custom commands,
    approval modes, and workspace roots are intentionally not model arguments.
    """
    session = getattr(agent, "current_session", {}) or {}
    requester = session.get("requester")
    if requester and requester.get("level") != "admin":
        return envelope(
            engine if isinstance(engine, str) else "",
            session_id=session_id if isinstance(session_id, str) else "",
            error=(
                "ACP child delegation is available only to the operator in a "
                "hosted session."
            ),
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

    workspace = (
        getattr(agent, "_delegation_workspace", Path.cwd())
        if agent is not None
        else Path.cwd()
    )
    tool = ACPAgent(
        approval=(
            "auto"
            if profile == DANGER_FULL_ACCESS_PERMISSION_PROFILE
            else "manual"
        ),
        workspace=workspace,
    )
    return tool.acp_agent(
        prompt=prompt,
        engine=engine,
        session_id=session_id,
        cwd=cwd,
        timeout=timeout,
        agent=agent,
    )
