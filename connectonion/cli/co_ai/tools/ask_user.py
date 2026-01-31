"""
Purpose: Ask user a question during agent execution via connection
LLM-Note:
  Dependencies: imports from [typing] | imported by [useful_tools/__init__.py]
  Data flow: agent calls ask_user tool → sends ask_user event via connection → waits for response → returns answer
  State/Effects: blocks until user responds via connection
  Integration: requires agent.connection to be set | agent parameter injected by tool_executor
"""

from typing import List, Optional


def ask_user(
    agent,
    question: str,
    options: Optional[List[str]] = None,
    multi_select: bool = False
) -> str:
    """Ask the user a question and wait for their response.

    Args:
        question: The question to ask the user
        options: Optional list of choices for the user to select from
        multi_select: If True, user can select multiple options

    Returns:
        The user's answer (or comma-separated answers if multi_select)
    """
    agent.connection.send({
        "type": "ask_user",
        "question": question,
        "options": options,
        "multi_select": multi_select
    })
    return agent.connection.receive().get("answer", "")
