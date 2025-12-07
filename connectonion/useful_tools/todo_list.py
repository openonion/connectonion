"""
Purpose: Task tracking tool for agents to manage multi-step task progress with visual display
LLM-Note:
  Dependencies: imports from [typing, dataclasses, rich.console, rich.table, rich.panel] | imported by [useful_tools/__init__.py] | tested by [tests/unit/test_todo_list_tool.py]
  Data flow: Agent calls TodoList methods → modifies internal _todos list → _display() renders Rich table with status indicators → returns confirmation string
  State/Effects: maintains in-memory list of TodoItem objects | displays Rich-formatted table in terminal | no file persistence | no network I/O
  Integration: exposes TodoList class with add(content, active_form), start(content), complete(content), remove(content), list_todos() | used as agent tool via Agent(tools=[TodoList()])
  Performance: O(n) list operations | Rich rendering per state change | no caching
  Errors: returns "Not found" if todo doesn't exist | no exceptions raised

TodoList - Task tracking for agents."""

from typing import List, Literal, Optional
from dataclasses import dataclass, field
from rich.console import Console
from rich.table import Table
from rich.panel import Panel


@dataclass
class TodoItem:
    """A single todo item."""
    content: str
    status: Literal["pending", "in_progress", "completed"]
    active_form: str


class TodoList:
    """Task tracking tool for agents.

    Helps agents track progress on complex, multi-step tasks.
    Shows visual progress to the user.

    Example:
        todo = TodoList()
        agent = Agent("worker", tools=[todo])

        # Agent can call:
        # todo.add("Fix authentication bug", "Fixing authentication bug")
        # todo.start("Fix authentication bug")
        # todo.complete("Fix authentication bug")
    """

    def __init__(self, console: Optional[Console] = None):
        self._todos: List[TodoItem] = []
        self._console = console or Console()

    def add(self, content: str, active_form: str) -> str:
        """Add a new todo item.

        Args:
            content: What needs to be done (imperative form, e.g., "Fix bug")
            active_form: Present continuous form (e.g., "Fixing bug")

        Returns:
            Confirmation message
        """
        if self._find(content):
            return f"Todo already exists: {content}"

        self._todos.append(TodoItem(
            content=content,
            status="pending",
            active_form=active_form
        ))
        self._display()
        return f"Added: {content}"

    def start(self, content: str) -> str:
        """Mark a todo as in_progress.

        Args:
            content: The todo content to start

        Returns:
            Confirmation or error message
        """
        item = self._find(content)
        if not item:
            return f"Todo not found: {content}"

        if item.status == "completed":
            return f"Cannot start completed todo: {content}"

        # Check if another task is in_progress
        in_progress = [t for t in self._todos if t.status == "in_progress"]
        if in_progress and in_progress[0].content != content:
            return f"Another task is in progress: {in_progress[0].content}. Complete it first."

        item.status = "in_progress"
        self._display()
        return f"Started: {item.active_form}"

    def complete(self, content: str) -> str:
        """Mark a todo as completed.

        Args:
            content: The todo content to complete

        Returns:
            Confirmation or error message
        """
        item = self._find(content)
        if not item:
            return f"Todo not found: {content}"

        item.status = "completed"
        self._display()
        return f"Completed: {content}"

    def remove(self, content: str) -> str:
        """Remove a todo from the list.

        Args:
            content: The todo content to remove

        Returns:
            Confirmation or error message
        """
        item = self._find(content)
        if not item:
            return f"Todo not found: {content}"

        self._todos.remove(item)
        self._display()
        return f"Removed: {content}"

    def list(self) -> str:
        """Get all todos as formatted text.

        Returns:
            Formatted list of all todos
        """
        if not self._todos:
            return "No todos"

        lines = []
        for item in self._todos:
            status_icon = self._status_icon(item.status)
            lines.append(f"{status_icon} {item.content}")

        return "\n".join(lines)

    def update(self, todos: List[dict]) -> str:
        """Replace entire todo list (for bulk updates).

        Args:
            todos: List of dicts with content, status, active_form keys

        Returns:
            Confirmation message
        """
        self._todos = []
        for t in todos:
            self._todos.append(TodoItem(
                content=t["content"],
                status=t["status"],
                active_form=t.get("active_form", t["content"] + "...")
            ))
        self._display()
        return f"Updated {len(self._todos)} todos"

    def clear(self) -> str:
        """Clear all todos.

        Returns:
            Confirmation message
        """
        count = len(self._todos)
        self._todos = []
        return f"Cleared {count} todos"

    def _find(self, content: str) -> Optional[TodoItem]:
        """Find todo by content."""
        for item in self._todos:
            if item.content == content:
                return item
        return None

    def _status_icon(self, status: str) -> str:
        """Get icon for status."""
        return {
            "pending": "○",
            "in_progress": "◐",
            "completed": "●"
        }.get(status, "○")

    def _status_style(self, status: str) -> str:
        """Get style for status."""
        return {
            "pending": "dim",
            "in_progress": "cyan bold",
            "completed": "green"
        }.get(status, "")

    def _display(self):
        """Display todos in a nice table."""
        if not self._todos:
            return

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Status", width=2)
        table.add_column("Task")

        for item in self._todos:
            icon = self._status_icon(item.status)
            style = self._status_style(item.status)

            if item.status == "in_progress":
                text = item.active_form
            else:
                text = item.content

            table.add_row(f"[{style}]{icon}[/]", f"[{style}]{text}[/]")

        # Count stats
        completed = sum(1 for t in self._todos if t.status == "completed")
        total = len(self._todos)

        self._console.print(Panel(
            table,
            title=f"[bold]Tasks[/] ({completed}/{total})",
            border_style="blue",
            padding=(0, 1)
        ))

    @property
    def progress(self) -> float:
        """Get progress as percentage (0.0 to 1.0)."""
        if not self._todos:
            return 1.0
        completed = sum(1 for t in self._todos if t.status == "completed")
        return completed / len(self._todos)

    @property
    def current_task(self) -> Optional[str]:
        """Get the currently in_progress task."""
        for item in self._todos:
            if item.status == "in_progress":
                return item.active_form
        return None
