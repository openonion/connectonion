"""
LLM-Note: Plan Mode tools - Planning before implementation workflow

Provides plan mode functionality for AI agents to design implementation approaches
before writing code. Enables user approval workflow for complex changes.

Key functions:
- enter_plan_mode(): Start planning phase with template
- write_plan(content): Update implementation plan
- exit_plan_and_implement(): Request user approval, then implement
- is_plan_mode_active(agent): Check current state

Workflow:
1. enter_plan_mode() - Sets up .co/PLAN.md template
2. Explore codebase (glob/grep/read_file)
3. write_plan() - Document implementation approach
4. exit_plan_and_implement() - Display plan, wait for user approval, then implement
5. Proceed with implementation after approval

Three modes:
- 'safe': Dangerous tools need approval (default)
- 'plan': Read-only tools only, exit_plan_and_implement shows plan for approval
- 'accept_edits': No approvals, agent runs freely

Agent can enter plan mode via enter_plan_mode().
User can switch modes via WebSocket mode_change message.

State management:
- Mode stored in agent.current_session['mode']
- Plan file at .co/PLAN.md
"""

from pathlib import Path
from typing import Optional
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

# Plan mode state (module-level for simplicity)
_plan_file_path: Optional[Path] = None
_previous_mode: Optional[str] = None  # Mode before entering plan mode


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
    global _plan_file_path, _previous_mode

    # Check if already in plan mode
    if agent and agent.current_session.get('mode') == 'plan':
        return "Already in plan mode. Use exit_plan_and_implement() when ready for user approval."

    # Save previous mode to restore after plan approval
    if agent:
        _previous_mode = agent.current_session.get('mode', 'safe')
        # Set mode to 'plan' and notify frontend
        agent.current_session['mode'] = 'plan'
        if agent.io:
            agent.io.send({'type': 'mode_changed', 'mode': 'plan', 'triggered_by': 'agent'})

    session_id = agent.current_session.get('session_id') if agent else None
    _plan_file_path = get_plan_file_path(session_id)

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

    _plan_file_path.write_text(initial_content, encoding="utf-8")

    console.print(Panel(
        "[bold green]Entered Plan Mode[/]\n\n"
        "You are now in planning mode. In this mode:\n"
        "1. [cyan]Explore[/] - Use glob/grep/read to understand the codebase\n"
        "2. [cyan]Design[/] - Write your implementation plan\n"
        "3. [cyan]Document[/] - Use write_plan() to save your plan\n"
        "4. [cyan]Exit[/] - Call exit_plan_and_implement() for user approval\n\n"
        f"Plan file: [dim]{_plan_file_path}[/]",
        title="📋 Plan Mode",
        border_style="green"
    ))

    return f"Entered plan mode. Write your plan with write_plan(), then call exit_plan_and_implement() when ready for user approval."


def exit_plan_and_implement(agent=None) -> str:
    """
    Exit plan mode, get user approval, then implement.

    Call this after you have written your plan with write_plan().
    The user will review and either approve or reject with feedback.

    Returns:
        - Approved: "Plan approved. Implement now. Do NOT re-enter plan mode. ..."
        - Rejected: "Plan rejected. User feedback: ... Revise with write_plan() and try again."
    """
    global _plan_file_path, _previous_mode

    if agent and agent.current_session.get('mode') != 'plan':
        return "Not in plan mode. Use enter_plan_mode() first."

    plan_file = _plan_file_path or get_plan_file_path()

    if not plan_file.exists():
        return f"Plan file not found at {plan_file}. Use write_plan() to write your plan first."

    plan_content = plan_file.read_text(encoding="utf-8")

    if agent:
        agent.current_session['pending_plan_content'] = plan_content
        agent.current_session['previous_mode'] = _previous_mode or 'safe'

    # Reset module state
    _plan_file_path = None
    _previous_mode = None

    # Display plan for CLI approval
    console.print(Panel(
        Markdown(plan_content),
        title="📋 Implementation Plan - Review Required",
        border_style="yellow"
    ))

    console.print()
    console.print("[bold yellow]Please review the plan above.[/]")
    console.print()

    return f"Plan approved. Implement now. Do NOT re-enter plan mode. Run the scaffold command first (e.g. bash('co create <name>')), then edit agent.py.\n\n---\n\n{plan_content}"


def write_plan(content: str) -> str:
    """
    Write or update the implementation plan.

    Use this to document your implementation plan while in plan mode.

    Args:
        content: The plan content in markdown format

    Returns:
        Confirmation message
    """
    plan_file = get_plan_file_path()
    plan_file.write_text(content, encoding="utf-8")
    return f"Plan updated: {plan_file}"
