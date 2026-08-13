"""
Purpose: Evaluation plugin for testing and debugging agent prompts and tools
LLM-Note:
  Dependencies: imports from [pathlib, typing, events.on_complete, llm_do] | imported by [useful_plugins/__init__.py] | uses prompt files [prompt_files/eval_expected.md, prompt_files/react_evaluate.md] | tested by [tests/unit/test_eval_plugin.py]
  Data flow: on_complete → _generate_expected() creates expected outcome → evaluate_completion() compares actual vs expected using llm_do() → stores in agent.current_session['expected'] and ['evaluation']
  State/Effects: modifies agent.current_session['expected'] and ['evaluation'] | makes LLM calls for expectation generation and evaluation | no file I/O | no network besides LLM
  Integration: exposes eval plugin list with [evaluate_completion] handler | used via Agent(plugins=[eval]) | combines with re_act for full debugging
  Performance: 2 LLM calls per task (generate + evaluate) AFTER task completes | no blocking delay
  Errors: no explicit error handling | LLM failures propagate | skips if expected already set by re_act

Eval plugin - Debug and test AI agent prompts and tools.

Generates expected outcomes and evaluates if tasks completed correctly.
Evaluation happens AFTER the main task completes (no blocking delay).

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
from typing import TYPE_CHECKING, Dict, List

from pydantic import BaseModel

from ..core.approval_modes import (
    DANGER_FULL_ACCESS_PERMISSION_PROFILE,
    legacy_permission_profile_id,
)
from ..core.events import after_user_input, on_complete
from ..core.trace import current_turn_trace
from ..llm_do import llm_do

if TYPE_CHECKING:
    from ..core.agent import Agent


class EvalResult(BaseModel):
    """Structured evaluation result."""
    passed: bool  # True if task completed successfully
    summary: str  # Brief explanation (1-2 sentences)


# Prompts
EXPECTED_PROMPT = Path(__file__).parent.parent / "prompt_files" / "eval_expected.md"

# Simpler prompt for structured eval - focus on intent, not exact matching
EVALUATE_PROMPT_TEXT = """You are evaluating if an AI agent completed its task.

Focus on the USER'S INTENT, not exact text matching:
- If the user asked to "list files" and the agent showed files, that's PASSED
- If the tool output was truncated but the agent showed the full result, that's PASSED
- Only mark as FAILED if the agent clearly didn't accomplish what was asked

Be lenient - if the core task was done, mark it passed."""


DEFAULT_SCORING_MODEL = "co/gemini-3.6-flash"


def _scoring_model(agent: 'Agent') -> str:
    """Score with the model the agent was built with.

    This used to be the literal below. An agent explicitly created with
    `model="gemini-2.5-pro"` still sent these calls to `co/`, which is not a
    detail when the reason for the override was that the co/ account was empty
    (#543). Configuring a provider is rarely cosmetic — it is billing, data
    residency, or simply the key that works.
    """
    return getattr(agent, "model", None) or DEFAULT_SCORING_MODEL


def _generate_expected(agent: 'Agent') -> str:
    """Generate expected outcome for the task (called internally before evaluation)."""
    user_prompt = agent.current_session.get('user_prompt', '')
    if not user_prompt:
        return ''

    tool_names = agent.tools.names() if agent.tools else []
    tools_str = ", ".join(tool_names) if tool_names else "no tools"

    prompt = f"""User request: {user_prompt}

Available tools: {tools_str}

What should happen to complete this task? (1-2 sentences)"""

    return llm_do(
        prompt,
        model=_scoring_model(agent),
        temperature=0.2,
        system_prompt=EXPECTED_PROMPT
    )


@after_user_input
def generate_expected(agent: 'Agent') -> None:
    """Generate and store expected outcome early in the session.

    Skips if already set or no user prompt.
    """
    _prepare_turn_state(agent)

    user_prompt = agent.current_session.get('user_prompt', '')
    if not user_prompt:
        return

    if agent.current_session.get('expected'):
        return

    # Scoring is not the work. This handler runs before the first tool, so an
    # unreachable or unaffordable model here used to take the whole turn with
    # it — a deployed agent failed every fifteen minutes for an hour on a
    # $0.0025 call describing work it never got to do (#543).
    #
    # Losing the expectation costs the score and nothing else, which is why
    # this one call earns a catch that most do not.
    try:
        expected = _generate_expected(agent)
        agent.current_session['expected'] = expected
        agent.current_session['_eval_expected'] = expected
    except Exception as exc:
        agent.logger.print(f"[dim]/expected unavailable ({exc})[/dim]")


def _summarize_trace(trace: List[Dict]) -> str:
    """Summarize what actions were taken."""
    actions = []
    for entry in trace:
        if entry['type'] == 'tool_result':
            status = entry['status']
            tool = entry['name']
            if status == 'success':
                # Keep concise context (100 chars) for tests and readability
                result = str(entry.get('result', ''))[:100]
                actions.append(f"- {tool}: {result}")
            else:
                actions.append(f"- {tool}: failed ({entry.get('error', 'unknown')})")
    return "\n".join(actions) if actions else "No tools were used."


def _prepare_turn_state(agent: 'Agent') -> None:
    """Keep transient eval values scoped to the current Agent turn.

    Sessions are cumulative, so ``expected`` and ``evaluation`` otherwise
    survive into the next user input.  Preserve a value another plugin wrote
    for this turn, but discard the value last produced by this plugin.
    """
    session = agent.current_session
    turn = session.get('turn')
    if session.get('_eval_turn') == turn:
        return

    previous_expected = session.get('expected')
    if previous_expected == session.get('_eval_expected'):
        session.pop('expected', None)
    session.pop('evaluation', None)
    session['_eval_turn'] = turn


@on_complete
def evaluate_completion(agent: 'Agent') -> None:
    """Evaluate if the task completed correctly.

    Generates expected outcome (if not set) and evaluates AFTER task completes.
    This avoids blocking the main workflow.

    Skips evaluation in Full access mode since the agent is still working autonomously.
    """
    import uuid

    # Skip eval in Full access mode - agent is still working, not done yet
    try:
        profile = legacy_permission_profile_id(agent.current_session.get('mode'))
    except ValueError:
        profile = None
    if profile == DANGER_FULL_ACCESS_PERMISSION_PROFILE:
        return

    _prepare_turn_state(agent)

    user_prompt = agent.current_session.get('user_prompt', '')
    if not user_prompt:
        return

    trace = current_turn_trace(
        agent.current_session.get('trace', []),
        agent.current_session.get('turn'),
    )
    actions_summary = _summarize_trace(trace)
    result = agent.current_session.get('result', 'No response generated.')

    # Generate expected now (after task done) if not already set by another plugin
    expected = agent.current_session.get('expected', '')
    if not expected:
        expected = _generate_expected(agent)
        agent.current_session['expected'] = expected
    agent.current_session['_eval_expected'] = expected

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

    # Generate ID for correlation
    eval_id = str(uuid.uuid4())[:8]

    # Get eval file path from logger
    eval_path = agent.logger.get_eval_path() if hasattr(agent.logger, 'get_eval_path') else None

    io = getattr(agent, 'io', None)

    # Send evaluating state to frontend
    if io:
        agent.io.send({
            'type': 'eval',
            'id': eval_id,
            'status': 'evaluating',
            'expected': expected,
            'eval_path': eval_path,
        })

    agent.logger.print("[dim]/evaluating...[/dim]")

    # Use structured output for clear pass/fail
    #
    # Less dangerous than the expectation call — the work is already done — but
    # an exception here still turns a run that succeeded into a run that
    # reports failure, which is the same lie in the other direction (#543).
    try:
        eval_result = llm_do(
            prompt,
            output=EvalResult,
            model=_scoring_model(agent),
            temperature=0,
            system_prompt=EVALUATE_PROMPT_TEXT
        )
    except Exception as exc:
        agent.logger.print(f"[dim]/evaluation unavailable ({exc})[/dim]")
        return

    # Support tests that patch llm_do to return a raw string
    if isinstance(eval_result, EvalResult):
        agent.current_session['evaluation'] = eval_result.model_dump()
        passed = eval_result.passed
        summary = eval_result.summary
    else:
        agent.current_session['evaluation'] = eval_result
        passed = None
        summary = str(eval_result)

    # Send evaluation result to frontend
    if io:
        io.send({
            'type': 'eval',
            'id': eval_id,
            'status': 'done',
            'passed': passed,
            'summary': summary,
            'expected': expected,
            'eval_path': eval_path,
        })

    # Persist to trace so reconnect/replay can rebuild the UI item.
    agent._record_trace({
        'type': 'eval',
        'id': eval_id,
        'passed': passed,
        'summary': summary,
        'expected': expected,
        'eval_path': eval_path,
    })

    # Terminal output with pass/fail indicator
    if passed is not None:
        icon = "✓" if passed else "✗"
        agent.logger.print(f"[dim]{icon} {summary}[/dim]")
    else:
        agent.logger.print(f"[dim]{summary}[/dim]")

    # Show eval file path
    if eval_path:
        agent.logger.print(f"[dim]  {eval_path}[/dim]")


# Bundle as plugin (generate expected after user input, then evaluate on complete)
eval = [generate_expected, evaluate_completion]
