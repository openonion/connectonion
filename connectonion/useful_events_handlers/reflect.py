"""
Purpose: Reflection event handler for generating reasoning after tool execution
LLM-Note:
  Dependencies: imports from [core/events.py after_tools, llm_do.py, pathlib, typing] | imported by [useful_events_handlers/__init__.py, user code] | tested by [tests/events/test_reflect.py]
  Data flow: fires after_tools event → _compress_messages() truncates tool results to 150 chars → llm_do generates reflection using reflect.md prompt → adds reflection as user message to session → LLM sees reflection in next iteration
  State/Effects: modifies agent.current_session['messages'] by appending user reflection message | calls llm_do (costs tokens) | no persistent state
  Integration: exposes reflect event handler (use via on_events=[reflect]) | uses after_tools (not after_each_tool) to fire ONCE after ALL tools | loads prompt from prompt_files/reflect.md | compresses messages to reduce context size
  Performance: one LLM call per tool batch (not per tool) | message compression limits token usage | truncates tool results to 150 chars
  Errors: none (fails silently if llm_do errors to avoid breaking agent execution)
Reflect event handler - Adds reflection after tool execution.

Fires ONCE after ALL tools in a batch complete (when LLM returns multiple tool_calls).
Generates reasoning about what we learned and what to do next.

This uses `after_tools` (not `after_each_tool`) intentionally because:
1. Adding messages after EACH tool breaks Anthropic Claude's message ordering
2. Reflecting once after all tools provides better context for next steps
3. Fewer LLM calls = faster execution

Usage:
    from connectonion import Agent
    from connectonion.useful_events_handlers import reflect

    agent = Agent("assistant", tools=[search], on_events=[reflect])
"""

import time
from pathlib import Path
from typing import TYPE_CHECKING, List, Dict
from ..core.events import after_tools
from ..llm_do import llm_do

if TYPE_CHECKING:
    from ..core.agent import Agent

# Path to reflect prompt (inside connectonion package for proper packaging)
REFLECT_PROMPT = Path(__file__).parent.parent / "prompt_files" / "reflect.md"


def _compress_messages(messages: List[Dict], tool_result_limit: int = 150) -> str:
    """
    Compress conversation messages with structure:
    - USER messages → Keep FULL
    - ASSISTANT tool_calls → Keep parameters FULL
    - ASSISTANT text → Keep FULL
    - TOOL results → Truncate to tool_result_limit chars
    """
    lines = []

    for msg in messages:
        role = msg['role']

        if role == 'user':
            lines.append(f"USER: {msg['content']}")

        elif role == 'assistant':
            if 'tool_calls' in msg:
                tools = [f"{tc['function']['name']}({tc['function']['arguments']})"
                         for tc in msg['tool_calls']]
                lines.append(f"ASSISTANT: {', '.join(tools)}")
            else:
                lines.append(f"ASSISTANT: {msg['content']}")

        elif role == 'tool':
            result = msg['content']
            if len(result) > tool_result_limit:
                result = result[:tool_result_limit] + '...'
            lines.append(f"TOOL: {result}")

    return "\n".join(lines)


@after_tools
def reflect(agent: 'Agent') -> None:
    """
    Reflection after tool execution.

    Fires ONCE after ALL tools in a batch complete. Generates reasoning about:
    - What we learned from the most recent action
    - What we should do next
    """
    trace = agent.current_session['trace'][-1]

    if trace['type'] != 'tool_result':
        return

    user_prompt = agent.current_session.get('user_prompt', '')
    tool_name = trace['name']
    tool_args = trace['args']
    status = trace['status']

    conversation = _compress_messages(agent.current_session['messages'])

    if status == 'success':
        tool_result = trace['result']
        prompt = f"""Context:
{conversation}

Current:
User asked: {user_prompt}
Action: {tool_name}({tool_args})
Result: {str(tool_result)[:300]}"""
    else:
        error = trace.get('error', 'Unknown error')
        prompt = f"""Context:
{conversation}

Current:
User asked: {user_prompt}
Action: {tool_name}({tool_args})
Error: {error}"""

    reasoning = llm_do(
        prompt,
        model="co/gemini-2.5-flash",
        temperature=0.2,
        system_prompt=REFLECT_PROMPT
    )

    agent.logger.print("[dim]/reflecting...[/dim]")

    agent._record_trace({
        'type': 'thinking',
        'kind': 'reflect',
        'content': reasoning,
    })

    agent.current_session['messages'].append({
        'role': 'assistant',
        'content': reasoning
    })
