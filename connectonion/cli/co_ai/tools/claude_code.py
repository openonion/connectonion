"""Expose Claude Code to co ai without exposing its permission policy."""

from connectonion.useful_tools import claude_code as run_claude_code


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
    """
    session = getattr(agent, "current_session", {}) or {}
    permission_mode = {
        "safe": "default",
        "accept_edits": "acceptEdits",
        "ulw": "auto",
    }.get(session.get("mode"), "default")
    return run_claude_code(
        prompt=prompt,
        session_id=session_id,
        cwd=cwd,
        permission_mode=permission_mode,
        model=model,
        timeout=timeout,
        agent=agent,
    )
