"""
Purpose: Create AI agent to explain why tools were chosen during debugging with experimental investigation capabilities
LLM-Note:
  Dependencies: imports from [pathlib, explain_context.py, ../agent.py, inspect] | imported by [interactive_debugger.py] | no dedicated tests found
  Data flow: interactive_debugger calls explain_tool_choice(breakpoint_context, agent, model) → extracts tool info (name, args, result, source code), agent info (system_prompt, available_tools), conversation history → creates RuntimeContext with experimental tools → creates explainer Agent with RuntimeContext as tool + explainer_prompt.md → sends comprehensive context prompt → Agent investigates and returns explanation string
  State/Effects: reads explainer_prompt.md file | creates temporary explainer Agent instance | calls RuntimeContext methods (which make LLM requests) | log=False prevents logging | no persistent state
  Integration: exposes explain_tool_choice(breakpoint_context, agent_instance, model) function | used by interactive_debugger WHY action | explainer agent has max_iterations=5 for investigation | RuntimeContext provides experimental debugging methods
  Performance: one explainer agent per WHY request | extracts source via inspect.getsource() | may make multiple LLM calls if explainer uses investigation tools | synchronous blocking
  Errors: FileNotFoundError if explainer_prompt.md missing | source extraction failures caught (returns "unavailable") | Agent creation and LLM errors propagate
"""

from pathlib import Path
from .explain_context import RuntimeContext


def explain_tool_choice(
    breakpoint_context,
    agent_instance,
    model: str = "co/gpt-5"
) -> str:
    """Explain why the agent chose this specific tool.

    Provides all context information upfront so the explainer doesn't need
    to call investigation tools.

    Args:
        breakpoint_context: BreakpointContext from the debugger
        agent_instance: The Agent being debugged
        model: AI model to use (default: co/gpt-5 for consistent debugging)

    Returns:
        Explanation string from the AI agent
    """
    from ..agent import Agent
    import inspect

    # Get all the information we need
    tool_name = breakpoint_context.tool_name
    tool_args = breakpoint_context.tool_args
    user_prompt = breakpoint_context.user_prompt
    tool_result = breakpoint_context.trace_entry.get('result')
    tool_status = breakpoint_context.trace_entry.get('status')

    # Get tool source code
    tool = agent_instance.tool_map.get(tool_name)
    tool_source = "Source unavailable"
    if tool:
        func = tool.run if hasattr(tool, 'run') else tool
        while hasattr(func, '__wrapped__'):
            func = func.__wrapped__
        tool_source = inspect.getsource(func)

    # Get agent information
    agent_name = agent_instance.name
    agent_system_prompt = agent_instance.system_prompt or "No system prompt"
    available_tools = [t.name for t in agent_instance.tools] if agent_instance.tools else []
    previous_tools = breakpoint_context.previous_tools
    iteration = breakpoint_context.iteration

    # Get conversation history
    messages = agent_instance.current_session.get('messages', [])
    recent_messages = messages[-3:] if len(messages) > 3 else messages

    # Get next planned actions
    next_actions = breakpoint_context.next_actions or []

    # Create runtime context - its methods become investigation tools
    runtime_ctx = RuntimeContext(breakpoint_context, agent_instance)

    # Load system prompt from markdown file
    prompt_file = Path(__file__).parent / "explainer_prompt.md"

    # Create explainer agent with runtime context tools
    explainer = Agent(
        name="tool_choice_explainer",
        system_prompt=prompt_file,
        tools=[runtime_ctx],  # Experimental tools for deeper investigation
        model=model,
        max_iterations=5,  # Allow investigation steps if needed
        log=False  # Don't clutter user's logs with explainer agent activity
    )

    # Build the full context prompt
    context_prompt = f"""The agent was asked: "{user_prompt}"

It chose to call: {tool_name}({tool_args})

## Agent Information
- Agent name: {agent_name}
- System prompt: {agent_system_prompt}
- Iteration: {iteration}
- Available tools: {available_tools}
- Previous tools called: {previous_tools}

## Tool Information
- Status: {tool_status}
- Arguments: {tool_args}
- Result: {tool_result}

## Tool Source Code
```python
{tool_source}
```

## Recent Conversation (last 3 messages)
{chr(10).join([f"- {msg.get('role')}: {str(msg.get('content', ''))[:200]}" for msg in recent_messages])}

## What Agent Plans Next
{chr(10).join([f"- {action['name']}({action['args']})" for action in next_actions]) if next_actions else "No more tools planned"}

Please explain why this tool was called with these arguments based on the context above."""

    result = explainer.input(context_prompt)
    return result
