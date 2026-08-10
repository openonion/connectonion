"""
Purpose: Ask user a question during agent execution via io
LLM-Note:
  Dependencies: imports from [typing] | imported by [useful_tools/__init__.py]
  Data flow: agent calls ask_user tool → sends ask_user event via io → waits for response → returns answer
  State/Effects: blocks until user responds via io
  Integration: requires agent.io to be set | agent parameter injected by tool_executor
"""

from typing import List

from ..core.interrupt import UserInterrupt


def ask_user(
    agent,
    question: str,
    options: List[str],
    multi_select: bool = False,
    fields: List[dict] = None
) -> str:
    """Ask the user a question and wait for their response.

    Args:
        question: The question to ask the user
        options: List of choices for the user to select from
        multi_select: If True, user can select multiple options
        fields: Optional structured inputs to collect, e.g.
            [{"name": "username", "label": "Username", "type": "text"},
             {"name": "password", "label": "Password", "type": "password"}]

    Returns:
        The user's answer (or comma-separated answers if multi_select)
    """
    if not agent.io:
        # One-shot mode (co ai "prompt", and every deployed agent) has nobody to
        # answer. This used to say "decide from the request context", which read
        # as approval: an agent that correctly stopped to confirm an irreversible
        # or outward-facing action was told to go ahead anyway. Unanswered is not
        # yes — proceed with reversible work, report back on the rest.
        return (
            "NOT ANSWERED — nobody is available to reply. This is not approval. "
            "Do not send, post, publish, delete, overwrite, deploy, or spend "
            "anything that this question was gating. Continue with any part of "
            "the task that does not depend on the answer, then end your turn by "
            "stating the question and what you would have done, so the user can "
            "decide."
        )

    event = {
        "type": "ask_user",
        "question": question,
        "options": options,
        "multi_select": multi_select,
    }
    if fields:
        event["fields"] = fields
    agent.io.send(event)
    response = agent.io.receive()
    if response.get("type") == "INTERRUPT":
        agent.current_session["stop_signal"] = "Interrupted by user"
        raise UserInterrupt()
    return response.get("answer", "")
