"""
LLM-Note: /tasks command for background task management.

This module implements the /tasks command which lists and manages background
tasks running in the co-ai environment.

Key components:
- cmd_tasks(args): Lists all background tasks or kills specific task
- Displays task table with ID, status, command, and elapsed time
- Supports `/tasks kill <task_id>` to terminate running tasks

Architecture:
- Uses _tasks dict and TaskStatus enum from background.py for task management
- Rich Table for formatted task display with color-coded status
- Shows task_id, status (running/completed/failed), truncated command, and elapsed time
- Empty args shows all tasks, "kill <task_id>" terminates specified task
- Calculates elapsed time from start_time to end_time (or current time if running)
"""

from rich.console import Console
from rich.table import Table

from connectonion.cli.co_ai.tools.background import _tasks, TaskStatus

console = Console()


def cmd_tasks(args: str = "") -> str:
    """List background tasks.

    Usage:
        /tasks          - List all tasks
        /tasks kill bg_1 - Kill a specific task
    """
    parts = args.strip().split()

    if parts and parts[0] == "kill":
        if len(parts) < 2:
            console.print("[error]Usage: /tasks kill <task_id>[/]")
            return "Missing task ID"

        from connectonion.cli.co_ai.tools.background import kill_task
        result = kill_task(parts[1])
        console.print(result)
        return result

    # List all tasks
    if not _tasks:
        console.print("[dim]No background tasks.[/]")
        return "No background tasks"

    table = Table(title="Background Tasks")
    table.add_column("ID", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Command")
    table.add_column("Time", justify="right")

    import time
    for task in _tasks.values():
        elapsed = time.time() - task.start_time
        if task.end_time:
            elapsed = task.end_time - task.start_time

        status_style = {
            TaskStatus.RUNNING: "yellow",
            TaskStatus.COMPLETED: "green",
            TaskStatus.FAILED: "red",
        }[task.status]

        cmd_short = task.command[:50] + "..." if len(task.command) > 50 else task.command

        table.add_row(
            task.id,
            f"[{status_style}]{task.status.value}[/]",
            cmd_short,
            f"{elapsed:.1f}s",
        )

    console.print(table)
    return f"Listed {len(_tasks)} tasks"
