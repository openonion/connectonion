"""
Reflect event handler - Adds reflection after each tool execution.

After each tool execution (success or error), generates reasoning about:
- What we learned from this action
- What we should do next

Usage:
    from connectonion import Agent
    from connectonion.useful_events_handlers import reflect

    agent = Agent("assistant", tools=[search], on_events=[reflect])
"""

from pathlib import Path
from typing import TYPE_CHECKING, List, Dict
from ..events import after_tool
from ..llm_do import llm_do

if TYPE_CHECKING:
    from ..agent import Agent

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


@after_tool
def reflect(agent: 'Agent') -> None:
    """
    Reflection after tool execution.

    After each tool execution (success or error), generates reasoning about:
    - What we learned from this action
    - What we should do next
    """
    trace = agent.current_session['trace'][-1]

    if trace['type'] != 'tool_execution':
        return

    user_prompt = agent.current_session.get('user_prompt', '')
    tool_name = trace['tool_name']
    tool_args = trace['arguments']
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

    agent.current_session['messages'].append({
        'role': 'assistant',
        'content': f"🤔 {reasoning}"
    })
