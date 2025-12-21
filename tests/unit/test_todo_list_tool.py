"""Unit tests for connectonion/useful_tools/todo_list.py

Tests cover:
- TodoList.add: adding new todo items
- TodoList.start: marking todos as in_progress
- TodoList.complete: marking todos as completed
- TodoList.remove: removing todos
- TodoList.list: listing all todos
- TodoList.update: bulk update todos
- TodoList.clear: clearing all todos
- TodoList.progress: getting progress percentage
- TodoList.current_task: getting current in_progress task
"""

import pytest
from unittest.mock import Mock
from connectonion.useful_tools.todo_list import TodoList, TodoItem


class TestTodoListAdd:
    """Tests for TodoList.add method."""

    def test_add_new_todo(self):
        """Test adding a new todo item."""
        todo = TodoList(console=Mock())
        result = todo.add("Fix bug", "Fixing bug")

        assert "Added" in result
        assert len(todo._todos) == 1
        assert todo._todos[0].content == "Fix bug"
        assert todo._todos[0].status == "pending"

    def test_add_duplicate_todo(self):
        """Test adding a duplicate todo item."""
        todo = TodoList(console=Mock())
        todo.add("Fix bug", "Fixing bug")
        result = todo.add("Fix bug", "Fixing bug")

        assert "already exists" in result
        assert len(todo._todos) == 1

    def test_add_multiple_todos(self):
        """Test adding multiple todo items."""
        todo = TodoList(console=Mock())
        todo.add("Task 1", "Doing task 1")
        todo.add("Task 2", "Doing task 2")
        todo.add("Task 3", "Doing task 3")

        assert len(todo._todos) == 3


class TestTodoListStart:
    """Tests for TodoList.start method."""

    def test_start_pending_todo(self):
        """Test starting a pending todo."""
        todo = TodoList(console=Mock())
        todo.add("Fix bug", "Fixing bug")
        result = todo.start("Fix bug")

        assert "Started" in result
        assert todo._todos[0].status == "in_progress"

    def test_start_nonexistent_todo(self):
        """Test starting a todo that doesn't exist."""
        todo = TodoList(console=Mock())
        result = todo.start("Nonexistent")

        assert "not found" in result

    def test_start_completed_todo(self):
        """Test that completed todos cannot be started."""
        todo = TodoList(console=Mock())
        todo.add("Fix bug", "Fixing bug")
        todo.complete("Fix bug")
        result = todo.start("Fix bug")

        assert "Cannot start completed" in result

    def test_start_while_another_in_progress(self):
        """Test that only one task can be in_progress at a time."""
        todo = TodoList(console=Mock())
        todo.add("Task 1", "Doing task 1")
        todo.add("Task 2", "Doing task 2")
        todo.start("Task 1")
        result = todo.start("Task 2")

        assert "Another task is in progress" in result
        assert todo._todos[1].status == "pending"


class TestTodoListComplete:
    """Tests for TodoList.complete method."""

    def test_complete_todo(self):
        """Test completing a todo."""
        todo = TodoList(console=Mock())
        todo.add("Fix bug", "Fixing bug")
        result = todo.complete("Fix bug")

        assert "Completed" in result
        assert todo._todos[0].status == "completed"

    def test_complete_nonexistent_todo(self):
        """Test completing a todo that doesn't exist."""
        todo = TodoList(console=Mock())
        result = todo.complete("Nonexistent")

        assert "not found" in result

    def test_complete_in_progress_todo(self):
        """Test completing an in_progress todo."""
        todo = TodoList(console=Mock())
        todo.add("Fix bug", "Fixing bug")
        todo.start("Fix bug")
        result = todo.complete("Fix bug")

        assert "Completed" in result
        assert todo._todos[0].status == "completed"


class TestTodoListRemove:
    """Tests for TodoList.remove method."""

    def test_remove_todo(self):
        """Test removing a todo."""
        todo = TodoList(console=Mock())
        todo.add("Fix bug", "Fixing bug")
        result = todo.remove("Fix bug")

        assert "Removed" in result
        assert len(todo._todos) == 0

    def test_remove_nonexistent_todo(self):
        """Test removing a todo that doesn't exist."""
        todo = TodoList(console=Mock())
        result = todo.remove("Nonexistent")

        assert "not found" in result


class TestTodoListList:
    """Tests for TodoList.list method."""

    def test_list_empty(self):
        """Test listing with no todos."""
        todo = TodoList(console=Mock())
        result = todo.list()

        assert result == "No todos"

    def test_list_todos(self):
        """Test listing todos with different statuses."""
        todo = TodoList(console=Mock())
        todo.add("Pending task", "Doing pending task")
        todo.add("In progress task", "Doing in progress task")
        todo.add("Completed task", "Doing completed task")
        todo.start("In progress task")
        todo.complete("Completed task")

        result = todo.list()

        assert "Pending task" in result
        assert "In progress task" in result
        assert "Completed task" in result


class TestTodoListUpdate:
    """Tests for TodoList.update method."""

    def test_update_replaces_all_todos(self):
        """Test that update replaces entire todo list."""
        todo = TodoList(console=Mock())
        todo.add("Old task", "Doing old task")

        result = todo.update([
            {"content": "New task 1", "status": "pending", "active_form": "Doing new task 1"},
            {"content": "New task 2", "status": "completed", "active_form": "Doing new task 2"},
        ])

        assert "Updated 2 todos" in result
        assert len(todo._todos) == 2
        assert todo._todos[0].content == "New task 1"
        assert todo._todos[1].status == "completed"

    def test_update_with_missing_active_form(self):
        """Test update with missing active_form uses default."""
        todo = TodoList(console=Mock())

        todo.update([
            {"content": "Task without active_form", "status": "pending"},
        ])

        assert todo._todos[0].active_form == "Task without active_form..."


class TestTodoListClear:
    """Tests for TodoList.clear method."""

    def test_clear_all_todos(self):
        """Test clearing all todos."""
        todo = TodoList(console=Mock())
        todo.add("Task 1", "Doing task 1")
        todo.add("Task 2", "Doing task 2")

        result = todo.clear()

        assert "Cleared 2 todos" in result
        assert len(todo._todos) == 0


class TestTodoListProgress:
    """Tests for TodoList.progress property."""

    def test_progress_empty(self):
        """Test progress with no todos."""
        todo = TodoList(console=Mock())
        assert todo.progress == 1.0

    def test_progress_none_completed(self):
        """Test progress with no completed todos."""
        todo = TodoList(console=Mock())
        todo.add("Task 1", "Doing task 1")
        todo.add("Task 2", "Doing task 2")

        assert todo.progress == 0.0

    def test_progress_half_completed(self):
        """Test progress with half completed todos."""
        todo = TodoList(console=Mock())
        todo.add("Task 1", "Doing task 1")
        todo.add("Task 2", "Doing task 2")
        todo.complete("Task 1")

        assert todo.progress == 0.5

    def test_progress_all_completed(self):
        """Test progress with all completed todos."""
        todo = TodoList(console=Mock())
        todo.add("Task 1", "Doing task 1")
        todo.add("Task 2", "Doing task 2")
        todo.complete("Task 1")
        todo.complete("Task 2")

        assert todo.progress == 1.0


class TestTodoListCurrentTask:
    """Tests for TodoList.current_task property."""

    def test_current_task_none(self):
        """Test current_task with no in_progress task."""
        todo = TodoList(console=Mock())
        todo.add("Task 1", "Doing task 1")

        assert todo.current_task is None

    def test_current_task_returns_active_form(self):
        """Test current_task returns active_form of in_progress task."""
        todo = TodoList(console=Mock())
        todo.add("Fix bug", "Fixing the critical bug")
        todo.start("Fix bug")

        assert todo.current_task == "Fixing the critical bug"


class TestTodoListStatusHelpers:
    """Tests for status helper methods."""

    def test_status_icon(self):
        """Test _status_icon returns correct icons."""
        todo = TodoList(console=Mock())

        assert todo._status_icon("pending") == "○"
        assert todo._status_icon("in_progress") == "◐"
        assert todo._status_icon("completed") == "●"
        assert todo._status_icon("unknown") == "○"

    def test_status_style(self):
        """Test _status_style returns correct styles."""
        todo = TodoList(console=Mock())

        assert todo._status_style("pending") == "dim"
        assert todo._status_style("in_progress") == "cyan bold"
        assert todo._status_style("completed") == "green"
        assert todo._status_style("unknown") == ""


class TestTodoListIntegration:
    """Integration tests for TodoList."""

    def test_todo_list_can_be_used_as_agent_tool(self):
        """Test that TodoList can be registered with agent."""
        from connectonion import Agent
        from connectonion.core.llm import LLMResponse
        from connectonion.core.usage import TokenUsage

        mock_llm = Mock()
        mock_llm.model = "test-model"
        mock_llm.complete.return_value = LLMResponse(
            content="Test",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

        todo = TodoList(console=Mock())
        agent = Agent(
            "test",
            llm=mock_llm,
            tools=[todo],
            log=False,
        )

        # Verify todo methods are accessible
        assert agent.tools.get("add") is not None
        assert agent.tools.get("start") is not None
        assert agent.tools.get("complete") is not None
        assert agent.tools.get("remove") is not None
        assert agent.tools.get("list") is not None
        assert agent.tools.get("update") is not None
        assert agent.tools.get("clear") is not None
