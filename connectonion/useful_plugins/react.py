"""
ReAct plugin - Adds reasoning and action planning after each tool execution.

After each tool execution (success or error), generates ReAct-style reasoning about:
- What we learned from this action
- What we should do next

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import react

    agent = Agent("assistant", tools=[search], plugins=[react])
"""

from typing import TYPE_CHECKING, List, Dict
from ..events import after_tool
from ..llm_do import llm_do

if TYPE_CHECKING:
    from ..agent import Agent


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


def _add_react_step(agent: 'Agent') -> None:
    """
    ReAct-style reasoning after tool execution.

    After each tool execution (success or error), generates reasoning about:
    - What we learned from this action
    - What we should do next
    """
    trace = agent.current_session['trace'][-1]

    if trace['type'] == 'tool_execution':
        # Extract current tool execution
        user_prompt = agent.current_session.get('user_prompt', '')
        tool_name = trace['tool_name']
        tool_args = trace['arguments']
        status = trace['status']

        # Compress conversation messages
        conversation = _compress_messages(agent.current_session['messages'])

        if status == 'success':
            tool_result = trace['result']
            prompt = f"""CONVERSATION:
{conversation}

CURRENT EXECUTION:
User asked: {user_prompt}
Action: {tool_name}({tool_args})
Observation: {tool_result}

Thought (in 2-3 sentences):
1. What did we learn from this action?
2. What should we do next?"""
        else:
            error = trace.get('error', 'Unknown error')
            prompt = f"""CONVERSATION:
{conversation}

CURRENT EXECUTION:
User asked: {user_prompt}
Action: {tool_name}({tool_args})
Error: {error}

Thought (in 2-3 sentences):
1. Why did this action fail?
2. What should we try instead?"""

        reasoning = llm_do(
            prompt,
            model="co/gpt-4o",
            temperature=0.2,
            system_prompt="You use ReAct-style reasoning to analyze actions and plan next steps. Think through what was learned and what to do next in a clear, structured way."
        )

        # Add reasoning as assistant message
        agent.current_session['messages'].append({
            'role': 'assistant',
            'content': f"🤔 {reasoning}"
        })

        agent.console.print(f"[cyan]🤔 {reasoning}[/cyan]")


# Plugin is an event list
react = [after_tool(_add_react_step)]
