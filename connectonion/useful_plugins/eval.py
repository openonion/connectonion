"""
Eval plugin - Debug and test AI agent prompts and tools.

Generates expected outcomes and evaluates if tasks completed correctly.
Use this during development to test if your prompts and tools work as intended.

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import eval

    # For debugging/testing
    agent = Agent("assistant", tools=[...], plugins=[eval])

    # Combined with re_act for full debugging
    from connectonion.useful_plugins import re_act, eval
    agent = Agent("assistant", tools=[...], plugins=[re_act, eval])
"""

from pathlib import Path
from typing import TYPE_CHECKING, List, Dict
from ..events import after_user_input, on_complete
from ..llm_do import llm_do

if TYPE_CHECKING:
    from ..agent import Agent

# Prompts
EXPECTED_PROMPT = Path(__file__).parent.parent / "prompt_files" / "eval_expected.md"
EVALUATE_PROMPT = Path(__file__).parent.parent / "prompt_files" / "react_evaluate.md"


@after_user_input
def generate_expected(agent: 'Agent') -> None:
    """Generate expected outcome for the task.

    Only generates if not already set (e.g., by re_act's plan_task).
    """
    # Skip if expected already set by another plugin (e.g., re_act)
    if agent.current_session.get('expected'):
        return

    user_prompt = agent.current_session.get('user_prompt', '')
    if not user_prompt:
        return

    tool_names = agent.tools.names() if agent.tools else []
    tools_str = ", ".join(tool_names) if tool_names else "no tools"

    prompt = f"""User request: {user_prompt}

Available tools: {tools_str}

What should happen to complete this task? (1-2 sentences)"""

    expected = llm_do(
        prompt,
        model="co/gemini-2.5-flash",
        temperature=0.2,
        system_prompt=EXPECTED_PROMPT
    )

    agent.current_session['expected'] = expected


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
    """Evaluate if the task completed correctly."""
    user_prompt = agent.current_session.get('user_prompt', '')
    if not user_prompt:
        return

    trace = agent.current_session.get('trace', [])
    actions_summary = _summarize_trace(trace)
    result = agent.current_session.get('result', 'No response generated.')
    expected = agent.current_session.get('expected', '')

    # Build prompt based on whether expected is available
    if expected:
        prompt = f"""User's original request: {user_prompt}

Expected: {expected}

Actions taken:
{actions_summary}

Agent's response:
{result}

Is this task truly complete? What was achieved or what's missing?"""
    else:
        prompt = f"""User's original request: {user_prompt}

Actions taken:
{actions_summary}

Agent's response:
{result}

Is this task truly complete? What was achieved or what's missing?"""

    agent.logger.print("[dim]/evaluating...[/dim]")

    evaluation = llm_do(
        prompt,
        model="co/gemini-2.5-flash",
        temperature=0.2,
        system_prompt=EVALUATE_PROMPT
    )

    agent.current_session['evaluation'] = evaluation
    agent.logger.print(f"[dim]✓ {evaluation}[/dim]")


# Bundle as plugin
eval = [generate_expected, evaluate_completion]
