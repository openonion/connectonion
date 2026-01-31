"""Compact command for compressing conversation context using LLM summarization."""

from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from connectonion import llm_do

console = Console()

# Module-level storage for agent reference
_current_agent = None

# Summarization prompt
SUMMARIZATION_PROMPT = Path(__file__).parent.parent / "prompts" / "summarization.md"


def set_agent(agent):
    """Set the current agent for compact operation."""
    global _current_agent
    _current_agent = agent


def _format_messages_for_summary(messages: list) -> str:
    """Format messages into a readable format for summarization."""
    formatted = []
    for msg in messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')

        # Handle tool_calls in assistant messages
        if role == 'assistant' and 'tool_calls' in msg:
            tool_calls = msg.get('tool_calls', [])
            tools_str = ", ".join(tc.get('function', {}).get('name', 'unknown') for tc in tool_calls)
            formatted.append(f"[assistant] Called tools: {tools_str}")
            if content:
                formatted.append(f"[assistant] {content[:500]}...")
        elif role == 'tool':
            # Truncate long tool results
            tool_name = msg.get('name', 'unknown')
            result = content[:200] + "..." if len(content) > 200 else content
            formatted.append(f"[tool:{tool_name}] {result}")
        elif role == 'system':
            # Keep system messages brief
            formatted.append(f"[system] {content[:300]}...")
        else:
            formatted.append(f"[{role}] {content}")

    return "\n\n".join(formatted)


def _create_summary_message(summary: str) -> dict:
    """Create a summary message to replace old context."""
    return {
        'role': 'user',
        'content': f"""## Previous Conversation Summary

{summary}

---
*The conversation continues below. Use the summary above for context.*"""
    }


def cmd_compact(args: str = "") -> str:
    """
    Compress conversation history using LLM summarization.

    This creates an intelligent summary of older messages while preserving:
    - User's explicit requests and intents
    - Key technical decisions and code patterns
    - File names and important code snippets
    - Errors encountered and how they were fixed
    - Recent messages (last 5)

    Use when context usage is high (>70%).
    """
    if _current_agent is None:
        console.print("[yellow]No agent session active.[/]")
        return "No session"

    agent = _current_agent

    # Check if we have a session
    if not hasattr(agent, 'current_session') or not agent.current_session:
        console.print("[yellow]No conversation history to compact.[/]")
        return "No history"

    messages = agent.current_session.get('messages', [])
    if len(messages) < 8:
        console.print("[yellow]Conversation too short to compact (< 8 messages).[/]")
        return "Too short"

    # Get context usage before
    context_before = getattr(agent, 'context_percent', 0)

    # Separate messages
    system_msg = messages[0] if messages and messages[0].get('role') == 'system' else None
    recent_count = 5
    recent_msgs = messages[-recent_count:]
    old_msgs = messages[1:-recent_count] if system_msg else messages[:-recent_count]

    if len(old_msgs) < 3:
        console.print("[yellow]Not enough old messages to compact.[/]")
        return "Nothing to compact"

    console.print("[cyan]Summarizing conversation...[/]")

    # Load summarization prompt
    summarization_instructions = ""
    if SUMMARIZATION_PROMPT.exists():
        summarization_instructions = SUMMARIZATION_PROMPT.read_text(encoding="utf-8")

    # Format messages for summarization
    conversation_text = _format_messages_for_summary(old_msgs)

    # Use LLM to create intelligent summary
    summary_prompt = f"""{summarization_instructions}

## Conversation to Summarize

{conversation_text}

---

Create a concise but complete summary following the structure above. Focus on:
1. What the user wanted to accomplish
2. Key files and code that were discussed or modified
3. Any errors and how they were fixed
4. Important decisions made

Keep the summary under 1000 words but preserve all critical technical details."""

    summary = llm_do(
        summary_prompt,
        model="co/gemini-2.5-flash",  # Fast model for summarization
    )

    # Create compacted messages
    summary_message = _create_summary_message(summary)

    new_messages = []
    if system_msg:
        new_messages.append(system_msg)
    new_messages.append(summary_message)
    new_messages.extend(recent_msgs)

    # Update agent session
    agent.current_session['messages'] = new_messages

    # Calculate savings
    old_count = len(messages)
    new_count = len(new_messages)
    saved = old_count - new_count

    # Display result
    console.print(Panel(
        f"[green]✓ Conversation compacted[/]\n\n"
        f"Messages: {old_count} → {new_count} ([green]-{saved}[/])\n"
        f"Context before: {context_before:.0f}%\n\n"
        f"[dim]Preserved:[/]\n"
        f"  • System prompt\n"
        f"  • AI-generated summary of older context\n"
        f"  • Recent {recent_count} messages\n\n"
        f"[dim]Summary includes:[/]\n"
        f"  • User requests and intents\n"
        f"  • Key files and code patterns\n"
        f"  • Errors and fixes\n"
        f"  • Technical decisions",
        title="📦 Compact",
        border_style="green"
    ))

    return f"Compacted: {old_count} → {new_count} messages"
