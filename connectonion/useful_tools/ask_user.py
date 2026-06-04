"""
Purpose: Ask user a question during agent execution via io
LLM-Note:
  Dependencies: imports from [typing] | imported by [useful_tools/__init__.py]
  Data flow: agent calls ask_user tool → sends ask_user event via io → waits for response → returns answer
  State/Effects: blocks until user responds via io
  Integration: requires agent.io to be set | agent parameter injected by tool_executor
"""

from typing import List


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
        # One-shot mode (co ai "prompt") runs without io — let the model decide.
        return "No interactive input available (one-shot mode); decide from the request context."

    event = {
        "type": "ask_user",
        "question": question,
        "options": options,
        "multi_select": multi_select,
    }
    if fields:
        event["fields"] = fields
    agent.io.send(event)
    return agent.io.receive().get("answer", "")
