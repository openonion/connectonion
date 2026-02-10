"""
Purpose: Web-friendly todo tracking tool
LLM-Note:
  Dependencies: imports from [typing, dataclasses] | imported by [co_ai.tools.__init__]
  Data flow: Agent calls TodoList methods -> updates internal list -> returns status string
  State/Effects: maintains in-memory list of TodoItem objects | no console output
  Integration: exposes TodoList class with add(content, active_form), start(content), complete(content), etc.
"""

from typing import List, Literal, Optional
from dataclasses import dataclass


@dataclass
class TodoItem:
    """A single todo item."""
    content: str
    status: Literal["pending", "in_progress", "completed"]
    active_form: str


class TodoList:
    """Task tracking tool for agents (web-first)."""

    def __init__(self):
        self._todos: List[TodoItem] = []

    def add(self, content: str, active_form: str) -> str:
        """Add a new todo item."""
        if self._find(content):
            return f"Todo already exists: {content}"

        self._todos.append(TodoItem(
            content=content,
            status="pending",
            active_form=active_form
        ))
        return f"Added: {content}"

    def start(self, content: str) -> str:
        """Mark a todo as in_progress."""
        item = self._find(content)
        if not item:
            return f"Todo not found: {content}"

        if item.status == "completed":
            return f"Cannot start completed todo: {content}"

        in_progress = [t for t in self._todos if t.status == "in_progress"]
        if in_progress and in_progress[0].content != content:
            return f"Another task is in progress: {in_progress[0].content}. Complete it first."

        item.status = "in_progress"
        return f"Started: {item.active_form}"

    def complete(self, content: str) -> str:
        """Mark a todo as completed."""
        item = self._find(content)
        if not item:
            return f"Todo not found: {content}"

        item.status = "completed"
        return f"Completed: {content}"

    def remove(self, content: str) -> str:
        """Remove a todo from the list."""
        item = self._find(content)
        if not item:
            return f"Todo not found: {content}"

        self._todos.remove(item)
        return f"Removed: {content}"

    def list(self) -> str:
        """Get all todos as formatted text."""
        if not self._todos:
            return "No todos"

        lines = []
        for item in self._todos:
            status_icon = self._status_icon(item.status)
            lines.append(f"{status_icon} {item.content}")

        return "\n".join(lines)

    def update(self, todos: List[dict]) -> str:
        """Replace entire todo list (for bulk updates)."""
        self._todos = []
        for t in todos:
            self._todos.append(TodoItem(
                content=t["content"],
                status=t["status"],
                active_form=t.get("active_form", t["content"] + "...")
            ))
        return f"Updated {len(self._todos)} todos"

    def clear(self) -> str:
        """Clear all todos."""
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
        """Get icon for status (ASCII)."""
        return {
            "pending": "[ ]",
            "in_progress": "[>]",
            "completed": "[x]"
        }.get(status, "[ ]")

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
