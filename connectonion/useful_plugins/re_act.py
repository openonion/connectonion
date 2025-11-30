"""
ReAct plugin - Reasoning and Acting pattern for AI agents.

Implements the ReAct (Reason + Act) pattern:
1. After user input: Plan what to do
2. After tool execution: Reflect on results and plan next step
3. On complete: Evaluate if task is truly done or needs more work

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import re_act

    agent = Agent("assistant", tools=[...], plugins=[re_act])
"""

from pathlib import Path
from typing import TYPE_CHECKING, List, Dict
from ..events import after_user_input, on_complete
from ..llm_do import llm_do
from ..useful_events_handlers.reflect import reflect

if TYPE_CHECKING:
    from ..agent import Agent

# Prompts
PLAN_PROMPT = Path(__file__).parent.parent / "prompts" / "react_plan.md"
EVALUATE_PROMPT = Path(__file__).parent.parent / "prompts" / "react_evaluate.md"


@after_user_input
def plan_task(agent: 'Agent') -> None:
    """Plan the task after receiving user input."""
    user_prompt = agent.current_session.get('user_prompt', '')
    if not user_prompt:
        return

    # Get available tools for context
    tool_names = agent.tools.names() if agent.tools else []
    tools_str = ", ".join(tool_names) if tool_names else "no tools"

    prompt = f"""User request: {user_prompt}

Available tools: {tools_str}

Brief plan (1-2 sentences): what to do first?"""

    agent.console.print("[dim]/planning...[/dim]")

    plan = llm_do(
        prompt,
        model="co/gemini-2.5-flash",
        temperature=0.2,
        system_prompt=PLAN_PROMPT
    )

    agent.current_session['messages'].append({
        'role': 'assistant',
        'content': f"💭 {plan}"
    })


def _summarize_trace(trace: List[Dict]) -> str:
    """Summarize what actions were taken."""
    actions = []
    for entry in trace:
        if entry['type'] == 'tool_execution':
            status = entry['status']
            tool = entry['tool_name']
            if status == 'success':
                result = str(entry.get('result', ''))[:100]
                actions.append(f"- {tool}: {result}")
            else:
                actions.append(f"- {tool}: failed ({entry.get('error', 'unknown')})")
    return "\n".join(actions) if actions else "No tools were used."


@on_complete
def evaluate_completion(agent: 'Agent') -> None:
    """Evaluate if the task is truly complete or needs more work."""
    user_prompt = agent.current_session.get('user_prompt', '')
    if not user_prompt:
        return

    trace = agent.current_session.get('trace', [])
    actions_summary = _summarize_trace(trace)

    prompt = f"""User's original request: {user_prompt}

Actions taken:
{actions_summary}

Is this task truly complete? What was achieved or what's missing?"""

    agent.console.print("[dim]/evaluating...[/dim]")

    evaluation = llm_do(
        prompt,
        model="co/gemini-2.5-flash",
        temperature=0.2,
        system_prompt=EVALUATE_PROMPT
    )

    agent.console.print(f"[dim]✓ {evaluation}[/dim]")


# Bundle as plugin: plan (after_user_input) + reflect (after_tool) + evaluate (on_complete)
re_act = [
    plan_task,
    reflect,
    evaluate_completion,
]
