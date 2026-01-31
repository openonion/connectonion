"""Background task execution for long-running operations."""

import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from enum import Enum


class TaskStatus(Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BackgroundTask:
    """A background task with its process and output."""
    id: str
    command: str
    process: subprocess.Popen
    output: list = field(default_factory=list)
    status: TaskStatus = TaskStatus.RUNNING
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None


# Global task registry
_tasks: Dict[str, BackgroundTask] = {}
_task_counter = 0
_lock = threading.Lock()


def _reset_for_testing():
    """Reset state for testing. Not for production use."""
    global _tasks, _task_counter
    with _lock:
        for task in _tasks.values():
            if task.status == TaskStatus.RUNNING:
                task.process.terminate()
        _tasks.clear()
        _task_counter = 0


def _read_output(task: BackgroundTask):
    """Read output from process in background thread."""
    for line in iter(task.process.stdout.readline, ""):
        if not line:
            break
        task.output.append(line.rstrip())

    task.process.wait()
    task.end_time = time.time()
    task.status = TaskStatus.COMPLETED if task.process.returncode == 0 else TaskStatus.FAILED


def run_background(command: str, description: str = "") -> str:
    """
    Run a shell command in the background.

    Use this for long-running operations like builds, tests, or servers.
    Returns immediately with a task ID. Use task_output() to check results.

    Args:
        command: Shell command to run (e.g., "npm run build", "pytest")
        description: Optional description for the task

    Returns:
        Task ID and confirmation message

    Example:
        run_background("npm run build")  # Returns: "Task bg_1 started: npm run build"
        task_output("bg_1")  # Check output later
    """
    global _task_counter

    with _lock:
        _task_counter += 1
        task_id = f"bg_{_task_counter}"

    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    task = BackgroundTask(
        id=task_id,
        command=command,
        process=process,
    )

    with _lock:
        _tasks[task_id] = task

    # Start output reader thread
    thread = threading.Thread(target=_read_output, args=(task,), daemon=True)
    thread.start()

    desc = f" ({description})" if description else ""
    return f"Task {task_id} started{desc}: {command}"


def task_output(task_id: str, tail: int = 50) -> str:
    """
    Get output from a background task.

    Args:
        task_id: The task ID (e.g., "bg_1")
        tail: Number of recent lines to show (default: 50)

    Returns:
        Task status and output

    Example:
        task_output("bg_1")  # Get output from task bg_1
        task_output("bg_1", tail=100)  # Get last 100 lines
    """
    with _lock:
        task = _tasks.get(task_id)

    if not task:
        available = list(_tasks.keys())
        if available:
            return f"Task '{task_id}' not found. Available: {', '.join(available)}"
        return f"Task '{task_id}' not found. No background tasks running."

    elapsed = time.time() - task.start_time
    if task.end_time:
        elapsed = task.end_time - task.start_time

    status_line = f"Task {task_id}: {task.status.value} ({elapsed:.1f}s)"
    status_line += f"\nCommand: {task.command}"

    if task.status == TaskStatus.FAILED:
        status_line += f"\nExit code: {task.process.returncode}"

    output_lines = task.output[-tail:] if task.output else []
    if output_lines:
        output_text = "\n".join(output_lines)
        if len(task.output) > tail:
            output_text = f"... ({len(task.output) - tail} lines omitted)\n{output_text}"
        return f"{status_line}\n\nOutput:\n{output_text}"

    return f"{status_line}\n\n(no output yet)"


def kill_task(task_id: str) -> str:
    """
    Kill a running background task.

    Args:
        task_id: The task ID to kill (e.g., "bg_1")

    Returns:
        Confirmation message
    """
    with _lock:
        task = _tasks.get(task_id)

    if not task:
        return f"Task '{task_id}' not found."

    if task.status != TaskStatus.RUNNING:
        return f"Task '{task_id}' is not running (status: {task.status.value})"

    task.process.terminate()
    task.status = TaskStatus.FAILED
    task.end_time = time.time()

    return f"Task '{task_id}' terminated."


def list_tasks() -> str:
    """
    List all background tasks.

    Returns:
        Table of all tasks with their status
    """
    with _lock:
        tasks = list(_tasks.values())

    if not tasks:
        return "No background tasks."

    lines = ["Background Tasks:", ""]
    for t in tasks:
        elapsed = time.time() - t.start_time
        if t.end_time:
            elapsed = t.end_time - t.start_time

        status_icon = {"running": "⏳", "completed": "✓", "failed": "✗"}[t.status.value]
        cmd_short = t.command[:40] + "..." if len(t.command) > 40 else t.command
        lines.append(f"  {status_icon} {t.id}: {cmd_short} ({elapsed:.1f}s)")

    return "\n".join(lines)
