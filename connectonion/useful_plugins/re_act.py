"""
Purpose: ReAct (Reasoning + Acting) plugin that adds intent recognition and reflection to agent execution
LLM-Note:
  Dependencies: imports from [pathlib, typing, events.after_user_input, llm_do, useful_events_handlers.reflect] | imported by [useful_plugins/__init__.py] | uses prompt file [prompt_files/react_acknowledge.md] | tested by [tests/unit/test_re_act_plugin.py]
  Data flow: after_user_input → acknowledge_request() → after_tools → reflect()
  State/Effects: modifies agent.current_session['intent'] | makes LLM calls for intent, reflection | no file I/O
  Integration: exposes re_act plugin list with [acknowledge_request, reflect] event handlers | used via Agent(plugins=[re_act])
  Performance: 2 LLM calls per turn (intent + reflect) | adds latency but improves agent reasoning
  Errors: no explicit error handling | LLM failures propagate | silent skip if no user_prompt

ReAct plugin - Reasoning and Acting pattern for AI agents.

Implements a simplified ReAct pattern:
1. After user input: Acknowledge request (show we understood)
2. After tool execution: Reflect on results

Planning is left to the main agent - this plugin just adds intent recognition and reflection.

Trace kinds for frontend rendering:
- kind='intent' → Show as "Understanding..." card
- kind='reflect' → Show as "Reflecting..." card

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
from ..core.events import after_user_input
from ..llm_do import llm_do
from ..useful_events_handlers.reflect import reflect

if TYPE_CHECKING:
    from ..core.agent import Agent

# Prompts
ACKNOWLEDGE_PROMPT = Path(__file__).parent.parent / "prompt_files" / "react_acknowledge.md"


def _format_conversation(
    messages: list,
    max_tokens: int = 4000,
    max_messages: int = 50,
) -> str:
    """Format conversation history with smart truncation.

    Only truncates when context exceeds budget. Priorities:
    1. User messages: always kept full (important context)
    2. Recent assistant messages: kept longer
    3. Older assistant messages: truncated first

    Args:
        messages: List of message dicts with 'role' and 'content'
        max_tokens: Approximate token budget (~4 chars per token)
        max_messages: Max number of messages to consider
    """
    max_chars = max_tokens * 4  # ~4 chars per token approximation

    recent = messages[-max_messages:] if len(messages) > max_messages else messages
    if not recent:
        return ""

    # First pass: calculate total size with full messages
    total_chars = sum(len(m.get('content', '')) for m in recent)

    # If under budget, return everything full
    if total_chars <= max_chars:
        lines = []
        for msg in recent:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    # Over budget: smart truncation
    # User messages kept full, truncate assistant messages
    user_chars = sum(len(m.get('content', '')) for m in recent if m.get('role') == 'user')
    available_for_assistant = max_chars - user_chars

    assistant_msgs = [m for m in recent if m.get('role') == 'assistant' and m.get('content')]
    if not assistant_msgs:
        return "\n".join(f"user: {m.get('content', '')}" for m in recent if m.get('role') == 'user')

    # Distribute chars to assistant messages (more to recent ones)
    n = len(assistant_msgs)
    weights = [1 + (i / n) for i in range(n)]  # older=1.0, recent=~2.0
    total_weight = sum(weights)
    char_budgets = [int(available_for_assistant * w / total_weight) for w in weights]

    # Build output
    lines = []
    assistant_idx = 0
    for msg in recent:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        if not content:
            continue

        if role == 'user':
            lines.append(f"user: {content}")
        elif role == 'assistant':
            budget = char_budgets[assistant_idx] if assistant_idx < len(char_budgets) else 200
            assistant_idx += 1
            if len(content) > budget:
                content = content[:budget] + "..."
            lines.append(f"assistant: {content}")

    return "\n".join(lines)


@after_user_input
def acknowledge_request(agent: 'Agent') -> None:
    """Immediately acknowledge the user's request to show we understood."""
    user_prompt = agent.current_session.get('user_prompt', '')
    if not user_prompt:
        return

    # Include conversation history for context
    messages = agent.current_session.get('messages', [])
    conversation = _format_conversation(messages)

    prompt = f"""Conversation so far:
{conversation}

Current user input: {user_prompt}

Acknowledge this request (1-2 sentences):"""

    model = "co/gemini-2.5-flash"
    agent.logger.print(f"[dim]/understanding ({model})...[/dim]")

    ack = llm_do(
        prompt,
        model=model,
        temperature=0.3,
        system_prompt=ACKNOWLEDGE_PROMPT
    )

    agent.current_session['intent'] = ack

    agent._record_trace({
        'type': 'thinking',
        'kind': 'intent',
        'content': ack,
    })

    # Add to messages so LLM sees the understanding
    agent.current_session['messages'].append({
        'role': 'assistant',
        'content': ack
    })


# Bundle as plugin: acknowledge (after_user_input) + reflect (after_tools)
# Planning is handled by the main agent
re_act = [acknowledge_request, reflect]
