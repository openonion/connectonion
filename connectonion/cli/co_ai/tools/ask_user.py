"""
Purpose: Ask user a question during agent execution via agent.io
LLM-Note:
  Dependencies: imports from [typing] | imported by [co_ai/tools/__init__.py]
  Data flow: agent calls ask_user tool → sends ask_user event via agent.io → waits for response → returns answer
  State/Effects: blocks until user responds via io
  Integration: requires agent.io to be set | agent parameter injected by tool_executor
    (tool_executor detects 'agent' in function signature and injects it automatically)
"""

from typing import List


def ask_user(
    agent,
    question: str,
    options: List[str],
    multi_select: bool = False
) -> str:
    """Ask the user a question and wait for their response.

    Args:
        question: The question to ask the user
        options: List of choices for the user to select from
        multi_select: If True, user can select multiple options

    Returns:
        The user's answer (or comma-separated answers if multi_select)
    """
    if not agent.io:
        # One-shot mode: no interactive IO available
        options_str = ', '.join(f'"{opt}"' for opt in options)
        return f"""[One-shot mode - No interactive user input available]

You asked: "{question}"
Available options: {options_str}

Since this is running in one-shot CLI mode without interactive input, you cannot ask the user directly. Instead, you must make this decision yourself based on:

1. The original user request and their intent
2. Best practices and first principles
3. The simplest approach that achieves the goal
4. What a reasonable user would most likely choose

Analyze the context and proceed with the most appropriate option. If uncertain, choose the safest/simplest option that still accomplishes the task."""

    agent.io.send({
        "type": "ask_user",
        "question": question,
        "options": options,
        "multi_select": multi_select
    })
    return agent.io.receive().get("answer", "")
