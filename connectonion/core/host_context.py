"""Requester notices and operator context for hosted work without prompts."""
from pathlib import Path
import shlex

from .. import approvals
from .interrupt import InterruptibleIO

AUTO_NOTICE = (
    "You're not an admin of this Host. This is allowed, and it is recorded "
    "for the admin, who can revoke your access at any time."
)


def add_auto_notice_to_model(session: dict) -> None:
    """Keep the notice in system context without splitting a tool-call batch."""
    messages = session.setdefault("messages", [])
    if messages and messages[0].get("role") == "system":
        messages[0]["content"] += "\n\n" + AUTO_NOTICE
    else:
        messages.insert(0, {"role": "system", "content": AUTO_NOTICE})


def begin_auto_run(agent, tool: str, task_summary: str) -> dict | None:
    """Give context for hosted non-admin work allowed without asking."""
    from .mode import READ_ONLY, mode_of

    if agent is None:
        return None
    session = agent.current_session or {}
    requester = session.get("requester") or {}
    if not requester.get("address") or requester.get("level") == "admin" or mode_of(session) == READ_ONLY:
        return None
    turn = session.get("turn", 0)
    if session.get("_host_auto_run_turn") == turn:
        return None
    session["_host_auto_run_turn"] = turn
    directory = agent.record_dir or agent.logger.co_dir
    if directory is not None:
        Path(directory).mkdir(parents=True, exist_ok=True)
    context = {"path": "auto", "who": approvals.identity(requester["address"]),
               "tool": tool, "task_summary": approvals.short(task_summary), "mode": mode_of(session),
               "session": session.get("session_id"), "via": session.get("via")}
    if not session.get("_host_auto_notice_sent"):
        session["_host_auto_notice_sent"] = True
        context["notice"] = AUTO_NOTICE
        event = {"type": "host_notice", "code": "non_admin_auto", "message": AUTO_NOTICE}
        agent._record_trace(event)
        if isinstance(agent.io, InterruptibleIO):
            agent.io.send_live_trace(event)
        # Update system context in place: inserting a message in the middle of
        # an assistant's tool-call batch would break provider message ordering.
        add_auto_notice_to_model(session)
    return context


def finish_auto_run(agent, context: dict | None, outcome: str) -> None:
    """Record each run in the existing ledger, then tell the Host operator."""
    if context is None:
        return
    from rich.console import Console

    # These audit entries remain mandatory when ordinary session logs are off
    # (including NativeCodexHostAgent). Logger.co_dir already honours state_dir.
    directory = agent.record_dir or agent.logger.co_dir
    if directory is not None:
        Path(directory).mkdir(parents=True, exist_ok=True)
        approvals.append(directory, {key: value for key, value in context.items() if key != "notice"} |
               {"decision": "done", "outcome": outcome})
    address = (agent.current_session.get("requester") or {}).get("address")
    trust_dir = getattr(agent, "_host_trust_dir", None)
    target = f" --co-dir {shlex.quote(str(Path(trust_dir).resolve()))}" if trust_dir is not None else ""
    Console().print(
        f"Host Auto: {context['who']} ran {context['tool']} — {context['task_summary']} "
        f"(mode={context['mode']}, {outcome}). Review: co approvals --who {address}. "
        f"Revoke access on this Host: co trust block {address}{target}. "
        "Revocation takes effect on the requester's next message (frame); "
        "a running turn is stopped then.", markup=False, soft_wrap=True,
    )

