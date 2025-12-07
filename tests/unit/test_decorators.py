"""Pytest unit tests for ConnectOnion debugging decorators."""

from unittest.mock import Mock, patch, call
import threading
import time

# Add parent directory to path for imports
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectonion.decorators import (replay, xray_replay, _is_replay_enabled)
from connectonion.xray import (
    xray,
    inject_xray_context as _inject_context_for_tool,
    clear_xray_context as _clear_context_after_tool,
    is_xray_enabled as _is_xray_enabled,
)
import pytest


@pytest.fixture(autouse=True)
def _clear_context_between_tests():
    _clear_context_after_tool()
    yield
    _clear_context_after_tool()


def test_xray_decorator_marks_function():
    """Test that @xray marks functions as xray-enabled."""
    @xray
    def test_func():
        return "test"

    assert _is_xray_enabled(test_func)
    assert test_func() == "test"


def test_xray_context_without_agent():
    """Test xray context when no agent context is set."""
    @xray
    def test_func():
        # Access context attributes
        assert xray.agent is None
        assert xray.user_prompt is None
        assert xray.messages == []
        assert xray.iteration is None
        assert xray.previous_tools == []
        return "success"

    result = test_func()
    assert result == "success"


def test_xray_context_with_agent():
    """Test xray context when agent context is injected."""
    mock_agent = Mock()
    mock_agent.name = "test_agent"

    _inject_context_for_tool(
        agent=mock_agent,
        user_prompt="Test task",
        messages=[{"role": "user", "content": "Hello"}],
        iteration=1,
        previous_tools=["tool1"],
    )

    @xray
    def test_func():
        assert xray.agent.name == "test_agent"
        assert xray.user_prompt == "Test task"
        assert len(xray.messages) == 1
        assert xray.iteration == 1
        assert xray.previous_tools == ["tool1"]
        return "success"

    result = test_func()
    assert result == "success"

    _clear_context_after_tool()
    assert xray.agent is None


def test_xray_repr():
    """Test xray context representation."""
    repr_str = repr(xray)
    assert "no active context" in repr_str

    mock_agent = Mock()
    mock_agent.name = "test_bot"

    _inject_context_for_tool(
        agent=mock_agent,
        user_prompt="Very long task description that should be truncated in the representation",
        messages=[{"role": "user", "content": "msg1"}, {"role": "assistant", "content": "msg2"}],
        iteration=2,
        previous_tools=["tool1", "tool2"],
    )

    @xray
    def test_func():
        repr_str = repr(xray)
        assert "<xray active>" in repr_str
        assert "test_bot" in repr_str
        assert "..." in repr_str
        assert "2 items" in repr_str
        assert "previous_tools" in repr_str
        return repr_str

    test_func()


def test_xray_function_preserves_metadata():
    """Test that @xray preserves function metadata."""
    @xray
    def test_func(x: int, y: str = "default") -> str:
        """Test function docstring."""
        return f"{x}-{y}"

    assert test_func.__name__ == "test_func"
    assert test_func.__doc__ == "Test function docstring."
    assert test_func(1, "test") == "1-test"


def test_replay_decorator_marks_function():
    """Test that @replay marks functions as replay-enabled."""
    @replay
    def test_func():
        return "test"

    assert _is_replay_enabled(test_func)
    assert test_func() == "test"


def test_replay_function_basic():
    """Test basic replay functionality."""
    call_count = 0

    @replay
    def test_func(x: int, y: int = 10) -> int:
        nonlocal call_count
        call_count += 1
        return x + y

    result = test_func(5)
    assert result == 15
    assert call_count == 1

    result2 = test_func(5, y=20)
    assert result2 == 25
    assert call_count == 2


def test_replay_with_mock_debugging():
    """Test replay during simulated debugging."""
    results = []

    @replay
    def test_func(text: str, multiplier: int = 2) -> str:
        result = text * multiplier
        results.append(result)
        return result

    result1 = test_func("a", 3)
    assert result1 == "aaa"
    assert len(results) == 1


def test_replay_preserves_metadata():
    """Test that @replay preserves function metadata."""
    @replay
    def test_func(x: int) -> int:
        """Test function with replay."""
        return x * 2

    assert test_func.__name__ == "test_func"
    assert test_func.__doc__ == "Test function with replay."


def test_xray_replay_combination():
    """Test using both decorators together."""
    @xray
    @replay
    def test_func(value: int) -> int:
        return value * 2

    assert _is_xray_enabled(test_func)
    assert _is_replay_enabled(test_func)
    result = test_func(5)
    assert result == 10


def test_xray_replay_convenience_decorator():
    """Test the xray_replay convenience decorator."""
    @xray_replay
    def test_func(value: str) -> str:
        return value.upper()

    assert _is_xray_enabled(test_func)
    assert _is_replay_enabled(test_func)
    result = test_func("hello")
    assert result == "HELLO"


def test_thread_local_context_isolation():
    """Test that contexts are isolated between threads."""
    results = {}

    @xray
    def test_func(thread_id: int):
        results[thread_id] = {
            'agent': xray.agent.name if xray.agent else None,
            'task': xray.user_prompt,
        }

    def thread_work(thread_id: int):
        mock_agent = Mock()
        mock_agent.name = f"agent_{thread_id}"

        _inject_context_for_tool(
            agent=mock_agent,
            user_prompt=f"Task {thread_id}",
            messages=[],
            iteration=thread_id,
            previous_tools=[],
        )

        test_func(thread_id)

    threads = []
    for i in range(3):
        t = threading.Thread(target=thread_work, args=(i,))
        threads.append(t)
        t.start()

    # Join with timeout to prevent CI hangs
    for t in threads:
        t.join(timeout=5.0)
        assert not t.is_alive(), f"Thread timed out - possible deadlock"

    assert len(results) == 3
    for i in range(3):
        assert results[i]['agent'] == f"agent_{i}"
        assert results[i]['task'] == f"Task {i}"


def test_xray_on_class_method():
    """Test @xray on class methods."""
    class TestClass:
        @xray
        def method(self, value: str) -> str:
            return f"Method: {value}"

    obj = TestClass()
    result = obj.method("test")
    assert result == "Method: test"
    assert _is_xray_enabled(obj.method)


def test_xray_on_static_method():
    """Test @xray on static methods."""
    class TestClass:
        @staticmethod
        @xray
        def static_method(value: str) -> str:
            return f"Static: {value}"

    result = TestClass.static_method("test")
    assert result == "Static: test"


def test_empty_context_handling():
    """Test handling of empty or None context values."""
    _inject_context_for_tool(
        agent=None,
        user_prompt=None,
        messages=None,
        iteration=None,
        previous_tools=None,
    )

    @xray
    def test_func():
        assert xray.agent is None
        assert xray.user_prompt is None
        assert xray.messages is None
        assert xray.iteration is None
        assert xray.previous_tools is None
        return "handled"

    result = test_func()
    assert result == "handled"


def test_xray_context_access_properties():
    """Test accessing xray context via properties."""
    mock_agent = Mock()
    mock_agent.name = "test"

    _inject_context_for_tool(
        agent=mock_agent,
        user_prompt="Test",
        messages=[{"role": "user", "content": "Hi"}],
        iteration=1,
        previous_tools=[],
    )

    @xray
    def test_func():
        assert xray.agent.name == "test"
        assert xray.user_prompt == "Test"
        assert len(xray.messages) == 1
        assert xray.iteration == 1
        assert xray.previous_tools == []
        return "success"

    test_func()
