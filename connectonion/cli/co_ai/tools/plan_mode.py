"""Plan Mode tools for planning before implementation."""

from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

console = Console()

# Plan mode state (module-level for simplicity)
_plan_mode_active = False
_plan_file_path: Optional[Path] = None


def get_plan_file_path() -> Path:
    """Get the default plan file path."""
    co_dir = Path.cwd() / ".co"
    co_dir.mkdir(exist_ok=True)
    return co_dir / "PLAN.md"


def is_plan_mode_active() -> bool:
    """Check if plan mode is currently active."""
    return _plan_mode_active


def enter_plan_mode() -> str:
    """
    Enter plan mode for designing implementation before coding.

    Use this when you need to:
    - Plan a complex feature implementation
    - Design architecture before writing code
    - Get user approval on approach before making changes

    In plan mode:
    - Explore the codebase to understand structure
    - Design the implementation approach
    - Write your plan to .co/PLAN.md
    - Exit plan mode when ready for user approval

    Returns:
        Confirmation message with instructions

    Example workflow:
        1. enter_plan_mode() - Start planning
        2. Use glob/grep/read_file to explore
        3. Write plan to .co/PLAN.md
        4. exit_plan_mode() - Get user approval
        5. Implement after approval
    """
    global _plan_mode_active, _plan_file_path

    if _plan_mode_active:
        return "Already in plan mode. Use exit_plan_mode() when ready for user approval."

    _plan_mode_active = True
    _plan_file_path = get_plan_file_path()

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
*Plan created by OO. Waiting for user approval.*
"""

    _plan_file_path.write_text(initial_content, encoding="utf-8")

    console.print(Panel(
        "[bold green]Entered Plan Mode[/]\n\n"
        "You are now in planning mode. In this mode:\n"
        "1. [cyan]Explore[/] - Use glob/grep/read_file to understand the codebase\n"
        "2. [cyan]Design[/] - Write your implementation plan\n"
        "3. [cyan]Document[/] - Update .co/PLAN.md with your plan\n"
        "4. [cyan]Exit[/] - Call exit_plan_mode() for user approval\n\n"
        f"Plan file: [dim]{_plan_file_path}[/]",
        title="Plan Mode",
        border_style="green"
    ))

    return f"Entered plan mode. Write your plan to {_plan_file_path}, then call exit_plan_mode() when ready for user approval."


def exit_plan_mode() -> str:
    """
    Exit plan mode and request user approval for the plan.

    Call this after you have:
    1. Explored the codebase
    2. Written your implementation plan to .co/PLAN.md

    The user will review the plan and either:
    - Approve: You can proceed with implementation
    - Request changes: Update the plan and try again
    - Reject: Abandon the plan

    Returns:
        The plan content for user review
    """
    global _plan_mode_active, _plan_file_path

    if not _plan_mode_active:
        return "Not in plan mode. Use enter_plan_mode() first."

    plan_file = _plan_file_path or get_plan_file_path()

    if not plan_file.exists():
        return f"Plan file not found at {plan_file}. Write your plan first."

    plan_content = plan_file.read_text(encoding="utf-8")

    # Reset state
    _plan_mode_active = False
    _plan_file_path = None

    # Display plan for user approval
    console.print(Panel(
        Markdown(plan_content),
        title="📋 Implementation Plan - Review Required",
        border_style="yellow"
    ))

    console.print()
    console.print("[bold yellow]Please review the plan above.[/]")
    console.print("Reply with:")
    console.print("  [green]'approve'[/] or [green]'yes'[/] - Proceed with implementation")
    console.print("  [yellow]'modify: <feedback>'[/] - Request changes to the plan")
    console.print("  [red]'reject'[/] or [red]'no'[/] - Abandon this plan")
    console.print()

    return f"Exited plan mode. Plan saved to {plan_file}. Waiting for user approval.\n\n---\n\n{plan_content}"


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
