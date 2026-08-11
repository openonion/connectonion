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
"""
LLM-Note: Tests for todo list tool

What it tests:
- Todo List Tool functionality

Components under test:
- Module: todo_list_tool
"""


import threading

import pytest
from unittest.mock import Mock
from connectonion.useful_tools.todo_list import TodoList, TodoItem
from connectonion.network.io import WebSocketIO


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
        assert todo._todos[0].priority == "medium"

    def test_add_accepts_explicit_acp_priority(self):
        todo = TodoList(console=Mock())

        todo.add("Fix bug", "Fixing bug", priority="high")

        assert todo._todos[0].priority == "high"

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

        add_schema = agent.tools.get("add").to_function_schema()["parameters"]
        assert "priority" in add_schema["properties"]
        assert "agent" not in add_schema["properties"]

    def test_successful_mutations_publish_one_complete_plan_each(self):
        publish = Mock()
        agent = Mock(_record_plan=publish)
        todo = TodoList(console=Mock())

        todo.add("First", "Doing first", priority="high", agent=agent)
        todo.start("First", agent=agent)
        todo.complete("First", agent=agent)
        todo.add("Second", "Doing second", agent=agent)
        todo.remove("Second", agent=agent)
        todo.update([{
            "content": "Third",
            "status": "pending",
            "active_form": "Doing third",
            "priority": "low",
        }], agent=agent)
        todo.clear(agent=agent)

        assert publish.call_count == 7
        assert publish.call_args_list[0].args[0] == [{
            "content": "First",
            "priority": "high",
            "status": "pending",
        }]
        assert publish.call_args_list[-1].args[0] == []

    def test_rejected_and_noop_operations_publish_nothing(self):
        publish = Mock()
        agent = Mock(_record_plan=publish)
        todo = TodoList(console=Mock())

        todo.add("First", "Doing first", agent=agent)
        publish.reset_mock()
        todo.add("First", "Doing first", agent=agent)
        todo.start("Missing", agent=agent)
        todo.complete("Missing", agent=agent)
        todo.remove("Missing", agent=agent)
        todo.update(todo._dump_state(), agent=agent)
        todo.clear()
        todo.clear(agent=agent)

        publish.assert_not_called()

    @pytest.mark.parametrize("priority", ["urgent", "", None, 1])
    def test_invalid_priority_does_not_mutate_or_publish(self, priority):
        publish = Mock()
        agent = Mock(_record_plan=publish)
        todo = TodoList(console=Mock())

        with pytest.raises(ValueError, match="priority"):
            todo.add("First", "Doing first", priority=priority, agent=agent)

        assert todo._todos == []
        publish.assert_not_called()

    def test_agent_execution_persists_plan_with_internal_provenance(self):
        from connectonion import Agent
        from tests.utils.mock_helpers import MockLLM

        todo = TodoList(console=Mock())
        agent = Agent("worker", llm=MockLLM(), tools=[todo], log=False)
        io = WebSocketIO()
        agent.io = io

        result = agent.execute_tool("add", {
            "content": "Ship plan",
            "active_form": "Shipping plan",
            "priority": "high",
        })

        assert result["status"] == "success"
        assert todo._dump_state() == [{
            "content": "Ship plan",
            "status": "pending",
            "active_form": "Shipping plan",
            "priority": "high",
        }]
        assert agent.current_session["plan"] == [{
            "content": "Ship plan",
            "priority": "high",
            "status": "pending",
        }]
        plan_event = next(
            event for event in io._msgs_from_agent
            if event.get("type") == "plan"
        )
        assert io.is_persisted_trace_event(plan_event)
        assert plan_event["entries"] == agent.current_session["plan"]
        sync = next(
            event for event in io._msgs_from_agent
            if event.get("type") == "session_sync"
            and event["session"].get("plan")
        )
        assert sync["session"]["plan"] == agent.current_session["plan"]

    def test_interrupted_plan_mutation_is_never_committed_or_streamed(self):
        from connectonion import Agent
        from connectonion.cli.co_ai.one_shot_sessions import capture_tool_state
        from tests.utils.mock_helpers import MockLLM

        class BlockingTodoList(TodoList):
            def __init__(self):
                super().__init__(console=Mock())
                self.published = threading.Event()
                self.release = threading.Event()
                self.finished = threading.Event()

            def _publish(self, agent) -> None:
                super()._publish(agent)
                self.published.set()
                self.release.wait(timeout=2)
                self.finished.set()

        todo = BlockingTodoList()
        agent = Agent("worker", llm=MockLLM(), tools=[todo], log=False)
        agent.tools.add_instance("todolist", todo)
        io = WebSocketIO()
        agent.io = io

        def interrupt_after_provisional_plan() -> None:
            assert todo.published.wait(timeout=1)
            io.send_to_agent({"type": "INTERRUPT"})

        threading.Thread(
            target=interrupt_after_provisional_plan,
            daemon=True,
        ).start()
        result = agent.execute_tool("add", {
            "content": "Must roll back",
            "active_form": "Rolling back",
        })
        todo.release.set()

        assert result["status"] == "interrupted"
        assert todo.finished.wait(timeout=1)
        assert todo._dump_state() == []
        assert capture_tool_state(agent) == {"todolist": []}
        assert "plan" not in agent.current_session
        assert not any(event.get("type") == "plan" for event in io._msgs_from_agent)
        assert not any(
            event.get("type") == "session_sync"
            and "plan" in event.get("session", {})
            for event in io._msgs_from_agent
        )

    def test_failed_plan_mutation_is_never_committed_or_streamed(self):
        from connectonion import Agent
        from tests.utils.mock_helpers import MockLLM

        class FailingTodoList(TodoList):
            def _publish(self, agent) -> None:
                super()._publish(agent)
                raise RuntimeError("after provisional plan")

        todo = FailingTodoList(console=Mock())
        agent = Agent("worker", llm=MockLLM(), tools=[todo], log=False)
        io = WebSocketIO()
        agent.io = io

        result = agent.execute_tool("add", {
            "content": "Must fail",
            "active_form": "Failing",
        })

        assert result["status"] == "error"
        assert todo._dump_state() == []
        assert "plan" not in agent.current_session
        assert not any(event.get("type") == "plan" for event in io._msgs_from_agent)
