"""
ReAct plugin - Reasoning and Acting pattern for AI agents.

Implements the ReAct (Reason + Act) pattern:
1. After user input: Plan what to do
2. After tool execution: Reflect on results and plan next step

For evaluation/debugging, use the separate `eval` plugin.

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import re_act

    agent = Agent("assistant", tools=[...], plugins=[re_act])

    # With evaluation for debugging:
    from connectonion.useful_plugins import re_act, eval
    agent = Agent("assistant", tools=[...], plugins=[re_act, eval])
"""

from pathlib import Path
from typing import TYPE_CHECKING
from ..events import after_user_input
from ..llm_do import llm_do
from ..useful_events_handlers.reflect import reflect

if TYPE_CHECKING:
    from ..agent import Agent

# Prompts
PLAN_PROMPT = Path(__file__).parent.parent / "prompt_files" / "react_plan.md"


@after_user_input
def plan_task(agent: 'Agent') -> None:
    """Plan the task after receiving user input."""
    user_prompt = agent.current_session.get('user_prompt', '')
    if not user_prompt:
        return

    tool_names = agent.tools.names() if agent.tools else []
    tools_str = ", ".join(tool_names) if tool_names else "no tools"

    prompt = f"""User request: {user_prompt}

Available tools: {tools_str}

Brief plan (1-2 sentences): what to do first?"""

    agent.logger.print("[dim]/planning...[/dim]")

    plan = llm_do(
        prompt,
        model="co/gemini-2.5-flash",
        temperature=0.2,
        system_prompt=PLAN_PROMPT
    )

    # Store plan as expected outcome (used by eval plugin if present)
    agent.current_session['expected'] = plan

    agent.current_session['messages'].append({
        'role': 'assistant',
        'content': f"💭 {plan}"
    })


# Bundle as plugin: plan (after_user_input) + reflect (after_tools)
re_act = [plan_task, reflect]
