"""
Reflection plugin - Adds AI-powered reflection after each tool execution.

After each successful tool execution, generates a brief reflection about
what was learned and adds it to the conversation.

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import reflection

    agent = Agent("assistant", tools=[search], plugins=[reflection])
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


def _add_reflection(agent: 'Agent') -> None:
    """
    Reflect on tool execution result.

    After each successful tool execution, generates a brief reflection
    using llm_do with compressed conversation context.
    """
    trace = agent.current_session['trace'][-1]

    if trace['type'] == 'tool_execution' and trace['status'] == 'success':
        # Extract current tool execution
        user_prompt = agent.current_session.get('user_prompt', '')
        tool_name = trace['tool_name']
        tool_args = trace['arguments']
        tool_result = trace['result']

        # Compress conversation messages
        conversation = _compress_messages(agent.current_session['messages'])

        # Build prompt with conversation context + current execution
        prompt = f"""CONVERSATION:
{conversation}

CURRENT EXECUTION:
User asked: {user_prompt}
Tool: {tool_name}({tool_args})
Result: {tool_result}

Reflect in 1-2 sentences on what we learned:"""

        reflection_text = llm_do(
            prompt,
            model="co/gpt-4o",
            temperature=0.3,
            system_prompt="You reflect on tool execution results to generate insights about what was learned and why it's useful for answering the user's question."
        )

        # Add reflection as assistant message
        agent.current_session['messages'].append({
            'role': 'assistant',
            'content': f"💭 {reflection_text}"
        })

        agent.console.print(f"[dim]💭 {reflection_text}[/dim]")


# Plugin is an event list
reflection = [after_tool(_add_reflection)]

