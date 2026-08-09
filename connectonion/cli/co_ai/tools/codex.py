"""Expose Codex to co ai without exposing a second permission policy."""

from pathlib import Path

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
    mode = getattr(agent, "current_session", {}).get("mode", "safe")
    sandbox, approval = {
        "safe": ("read-only", "manual"),
        "accept_edits": ("workspace-write", "manual"),
        "ulw": ("workspace-write", "deny"),
    }.get(mode, ("read-only", "manual"))
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
