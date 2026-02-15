"""
Purpose: Automatically compress conversation context when usage >= 90% to prevent overflow
LLM-Note:
  Dependencies: imports from [typing, core.events, llm_do, pathlib, uuid] | imported by [useful_plugins/__init__.py, cli/co_ai/agent.py] | tested via after_llm event firing
  Data flow: after_llm event fires → check_and_compact() checks context_percent → if >= 90% and len(messages) >= 8: _do_compact() → llm_do() with gemini-2.5-flash summarizes old messages → replaces old messages with summary → keeps system + summary + last 5 messages → returns "{old_count} → {new_count} messages"
  State/Effects: modifies agent.current_session['messages'] by replacing old messages with LLM-generated summary | sends compact events via agent.io if connected | logs to console via agent.logger | no file I/O except loading summarization.md prompt
  Integration: exposes auto_compact=[check_and_compact] plugin | fires on after_llm event | uses _do_compact(), _format_messages_for_summary() helper functions | COMPACT_THRESHOLD=90 constant | reads cli/co_ai/prompts/summarization.md for instructions
  Performance: only fires when context >= 90% | minimum 8 messages required | keeps last 5 messages (recent_count) + system + summary | llm_do() call to gemini-2.5-flash (fast/cheap) | summary prompt limited to 800 words
  Errors: catches all exceptions in _do_compact() and sends error event | prints red ✗ on failure | gracefully handles missing summarization.md (empty instructions)

Auto-compact plugin - Automatically compresses context when running low.

Monitors context window usage after each LLM call. When usage >= 90%,
automatically triggers compaction to free up context space.

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import auto_compact

    agent = Agent("assistant", plugins=[auto_compact])
"""

from typing import TYPE_CHECKING
from ..core.events import after_llm

if TYPE_CHECKING:
    from ..core.agent import Agent

# Threshold for auto-compaction (90% = 10% remaining)
COMPACT_THRESHOLD = 90


@after_llm
def check_and_compact(agent: 'Agent') -> None:
    """Check context usage and auto-compact if needed."""
    import uuid

    # Get current context usage
    context_percent = agent.context_percent
    if context_percent < COMPACT_THRESHOLD:
        return  # Still have room

    # Check if we have enough messages to compact
    messages = agent.current_session.get('messages', [])
    if len(messages) < 8:
        return  # Too short to compact

    # Generate ID for frontend events
    compact_id = str(uuid.uuid4())[:8]

    # Notify frontend: starting compaction
    if agent.io:
        agent.io.send({
            'type': 'compact',
            'id': compact_id,
            'status': 'compacting',
            'context_percent': context_percent,
        })

    # Log to terminal
    if agent.logger.console:
        agent.logger.console.print(f"[dim]▸ context at {context_percent:.0f}%, auto-compacting...[/dim]")

    # Perform compaction (reuse logic from compact command)
    try:
        result = _do_compact(agent)
        new_percent = agent.context_percent

        # Notify frontend: done
        if agent.io:
            agent.io.send({
                'type': 'compact',
                'id': compact_id,
                'status': 'done',
                'context_before': context_percent,
                'context_after': new_percent,
                'message': result,
            })

        if agent.logger.console:
            agent.logger.console.print(f"[dim]✓ compacted: {context_percent:.0f}% → {new_percent:.0f}%[/dim]")

    except Exception as e:
        # Notify frontend: error
        if agent.io:
            agent.io.send({
                'type': 'compact',
                'id': compact_id,
                'status': 'error',
                'error': str(e),
            })
        if agent.logger.console:
            agent.logger.console.print(f"[red]✗ auto-compact failed: {e}[/red]")


def _do_compact(agent: 'Agent') -> str:
    """Perform the actual compaction. Returns summary message."""
    from pathlib import Path
    from ..llm_do import llm_do

    messages = agent.current_session.get('messages', [])

    # Separate messages
    system_msg = messages[0] if messages and messages[0].get('role') == 'system' else None
    recent_count = 5
    recent_msgs = messages[-recent_count:]
    old_msgs = messages[1:-recent_count] if system_msg else messages[:-recent_count]

    if len(old_msgs) < 3:
        return "Nothing to compact"

    # Load summarization prompt
    prompt_path = Path(__file__).parent.parent / "cli" / "co_ai" / "prompts" / "summarization.md"
    summarization_instructions = ""
    if prompt_path.exists():
        summarization_instructions = prompt_path.read_text(encoding="utf-8")

    # Format messages for summarization
    conversation_text = _format_messages_for_summary(old_msgs)

    # Use LLM to create intelligent summary
    summary_prompt = f"""{summarization_instructions}

## Conversation to Summarize

{conversation_text}

---

Create a concise but complete summary. Focus on:
1. What the user wanted to accomplish
2. Key files and code that were discussed or modified
3. Any errors and how they were fixed
4. Important decisions made

Keep the summary under 800 words but preserve all critical technical details."""

    summary = llm_do(
        summary_prompt,
        model="co/gemini-2.5-flash",
        temperature=0,
    )

    # Create compacted messages
    summary_message = {
        'role': 'user',
        'content': f"""## Previous Conversation Summary

{summary}

---
*The conversation continues below. Use the summary above for context.*"""
    }

    new_messages = []
    if system_msg:
        new_messages.append(system_msg)
    new_messages.append(summary_message)
    new_messages.extend(recent_msgs)

    # Update agent session
    old_count = len(messages)
    agent.current_session['messages'] = new_messages
    new_count = len(new_messages)

    return f"{old_count} → {new_count} messages"


def _format_messages_for_summary(messages: list) -> str:
    """Format messages into a readable format for summarization."""
    formatted = []
    for msg in messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')

        if role == 'assistant' and 'tool_calls' in msg:
            tool_calls = msg.get('tool_calls', [])
            tools_str = ", ".join(tc.get('function', {}).get('name', 'unknown') for tc in tool_calls)
            formatted.append(f"[assistant] Called tools: {tools_str}")
            if content:
                formatted.append(f"[assistant] {content[:500]}...")
        elif role == 'tool':
            tool_name = msg.get('name', 'unknown')
            result = content[:200] + "..." if len(content) > 200 else content
            formatted.append(f"[tool:{tool_name}] {result}")
        elif role == 'system':
            formatted.append(f"[system] {content[:300]}...")
        else:
            formatted.append(f"[{role}] {content}")

    return "\n\n".join(formatted)


# Export plugin
auto_compact = [check_and_compact]
