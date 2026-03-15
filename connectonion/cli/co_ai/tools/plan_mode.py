"""
LLM-Note: Plan Mode tools - Planning before implementation workflow

Provides plan mode functionality for AI agents to design implementation approaches
before writing code. Enables user approval workflow for complex changes.

Key functions:
- enter_plan_mode(): Start planning phase with template
- write_plan(content): Update implementation plan
- exit_plan_and_implement(): Send plan for review via io.send/receive, then implement
- is_plan_mode_active(agent): Check current state

Workflow:
1. enter_plan_mode() - Sets up .co/PLAN.md template
2. Explore codebase (glob/grep/read_file)
3. write_plan() - Document implementation approach
4. exit_plan_and_implement() - Send plan_review via io, wait for response, then implement
5. Proceed with implementation after approval

Three modes:
- 'safe': Dangerous tools need approval (default)
- 'plan': Read-only tools only, exit_plan_and_implement sends plan for review
- 'accept_edits': No approvals, agent runs freely

Agent can enter plan mode via enter_plan_mode().
User can switch modes via WebSocket mode_change message.

State management:
- Mode stored in agent.current_session['mode']
- Plan path stored in agent.current_session['plan_path']
- Previous mode stored in agent.current_session['previous_mode']
- Plan file at .co/PLAN.md
"""

from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

# Note: The `agent` parameter in tool functions has no type hint.
#
# Why: tool_factory uses get_type_hints() to build parameter schemas.
# If we use `agent: 'Agent'` with TYPE_CHECKING import, get_type_hints()
# fails with NameError because Agent isn't defined at runtime.
#
# This is safe because:
# - tool_factory skips 'agent' parameter anyway (not sent to LLM)
# - tool_executor injects agent at runtime

console = Console()


def get_plan_file_path(session_id: str = None) -> Path:
    """Get the plan file path, scoped by session ID."""
    co_dir = Path.cwd() / ".co"
    co_dir.mkdir(exist_ok=True)
    if session_id:
        return co_dir / f"PLAN_{session_id}.md"
    return co_dir / "PLAN.md"


def is_plan_mode_active(agent) -> bool:
    """Check if plan mode is currently active."""
    return agent.current_session.get('mode') == 'plan'


def enter_plan_mode(agent=None) -> str:
    """
    Enter plan mode for designing implementation before coding.

    Use this when you need to:
    - Plan a complex feature implementation
    - Design architecture before writing code
    - Get user approval on approach before making changes

    In plan mode:
    - Explore the codebase with read-only tools (glob, grep, read)
    - Design the implementation approach
    - Write your plan with write_plan()
    - Exit plan mode when ready for user approval

    Returns:
        Confirmation message with instructions

    Example workflow:
        1. enter_plan_mode() - Start planning
        2. Use glob/grep/read to explore
        3. write_plan(content) - Document your plan
        4. exit_plan_and_implement() - Get user approval, then implement
    """
    # Check if already in plan mode
    if agent and agent.current_session.get('mode') == 'plan':
        return "Already in plan mode. Use exit_plan_and_implement() when ready for user approval."

    # Save previous mode and set plan path in session
    if agent:
        agent.current_session['previous_mode'] = agent.current_session.get('mode', 'safe')
        agent.current_session['mode'] = 'plan'
        if agent.io:
            agent.io.send({'type': 'mode_changed', 'mode': 'plan', 'triggered_by': 'agent'})

    session_id = agent.current_session.get('session_id') if agent else None
    plan_path = get_plan_file_path(session_id)

    if agent:
        agent.current_session['plan_path'] = str(plan_path)

    # Create initial plan file
    initial_content = """# Implementation Plan

## Summary
[One-sentence description of what will be implemented]

## Current Understanding
[What you learned from exploring the codebase]

## Files to Modify
- `path/to/file.py` - What changes needed

## Files to Create
- `path/to/new_file.py` - Purpose

## Implementation Steps
1. Step 1 - Details
2. Step 2 - Details
3. Step 3 - Details

## Considerations
- Any risks or trade-offs

---
*Plan created by agent. Waiting for user approval.*
"""

    plan_path.write_text(initial_content, encoding="utf-8")

    console.print(Panel(
        "[bold green]Entered Plan Mode[/]\n\n"
        "You are now in planning mode. In this mode:\n"
        "1. [cyan]Explore[/] - Use glob/grep/read to understand the codebase\n"
        "2. [cyan]Design[/] - Write your implementation plan\n"
        "3. [cyan]Document[/] - Use write_plan() to save your plan\n"
        "4. [cyan]Exit[/] - Call exit_plan_and_implement() for user approval\n\n"
        f"Plan file: [dim]{plan_path}[/]",
        title="📋 Plan Mode",
        border_style="green"
    ))

    return f"Entered plan mode. Write your plan with write_plan(), then call exit_plan_and_implement() when ready for user approval."


def exit_plan_and_implement(agent=None) -> str:
    """
    Exit plan mode, send plan for user review via io.send/receive, then implement.

    Call this after you have written your plan with write_plan().
    Sends {type: "plan_review", plan_content: "..."} via io.send(),
    blocks on io.receive() for user response, then restores previous mode.

    Returns:
        User's response message (raw from io.receive)
    """
    if agent and agent.current_session.get('mode') != 'plan':
        return "Not in plan mode. Use enter_plan_mode() first."

    plan_path = agent.current_session.get('plan_path') if agent else None
    if plan_path:
        plan_path = Path(plan_path)
    else:
        plan_path = get_plan_file_path()

    if not plan_path.exists():
        return f"Plan file not found at {plan_path}. Use write_plan() to write your plan first."

    plan_content = plan_path.read_text(encoding="utf-8")

    # Send plan for review via io, receive response
    if agent and agent.io:
        agent.io.send({"type": "plan_review", "plan_content": plan_content})
        response = agent.io.receive()  # {type: "plan_review", message: "..."}
    else:
        # CLI fallback — display plan and auto-approve
        console.print(Panel(
            Markdown(plan_content),
            title="📋 Implementation Plan - Review Required",
            border_style="yellow"
        ))
        response = {"message": f"Plan approved. Implement now. Do NOT re-enter plan mode.\n\n---\n\n{plan_content}"}

    # Restore previous mode
    if agent:
        previous_mode = agent.current_session.get('previous_mode', 'safe')
        agent.current_session['mode'] = previous_mode
        if agent.io:
            agent.io.send({'type': 'mode_changed', 'mode': previous_mode})

        # Clean up session state
        agent.current_session.pop('plan_path', None)
        agent.current_session.pop('previous_mode', None)

    return response.get("message", "")


def write_plan(content: str, agent=None) -> str:
    """
    Write or update the implementation plan.

    Use this to document your implementation plan while in plan mode.

    Args:
        content: The plan content in markdown format

    Returns:
        Confirmation message
    """
    plan_path = None
    if agent:
        path_str = agent.current_session.get('plan_path')
        if path_str:
            plan_path = Path(path_str)

    if not plan_path:
        plan_path = get_plan_file_path()

    plan_path.write_text(content, encoding="utf-8")
    return f"Plan updated: {plan_path}"
