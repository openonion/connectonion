"""Tasks command - list and manage background tasks."""

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
