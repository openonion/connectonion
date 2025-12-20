"""Tests for xray.py - XRay debugging tool."""

import builtins
import pytest
from unittest.mock import Mock, patch

from connectonion.debug.xray import (
    XrayDecorator,
    xray,
    inject_xray_context,
    clear_xray_context,
    is_xray_enabled,
)


class TestXrayDecoratorInit:
    """Test XrayDecorator initialization."""

    def test_global_xray_exists(self):
        """Global xray object exists in builtins."""
        assert hasattr(builtins, 'xray')
        assert isinstance(builtins.xray, XrayDecorator)

    def test_initial_context_is_empty(self):
        """Initial context values are empty/None."""
        decorator = XrayDecorator()
        assert decorator._agent is None
        assert decorator._user_prompt is None
        assert decorator._messages == []
        assert decorator._iteration is None
        assert decorator._previous_tools == []


class TestXrayDecoratorCall:
    """Test XrayDecorator as decorator."""

    def test_decorator_without_parentheses(self):
        """@xray decorator without parentheses."""
        @xray
        def my_func():
            pass

        assert hasattr(my_func, '__xray_enabled__')
        assert my_func.__xray_enabled__ is True
        assert my_func.__xray_rich__ is True

    def test_decorator_with_parentheses(self):
        """@xray() decorator with empty parentheses."""
        @xray()
        def my_func():
            pass

        assert my_func.__xray_enabled__ is True
        assert my_func.__xray_rich__ is True

    def test_decorator_with_trace_false(self):
        """@xray(trace=False) disables auto-tracing."""
        @xray(trace=False)
        def my_func():
            pass

        assert my_func.__xray_enabled__ is False

    def test_decorator_with_rich_false(self):
        """@xray(rich=False) disables Rich formatting."""
        @xray(rich=False)
        def my_func():
            pass

        assert my_func.__xray_rich__ is False

    def test_decorator_preserves_function(self):
        """Decorator returns the original function (no wrapper)."""
        def original():
            return "result"

        decorated = xray(original)

        assert decorated is original
        assert decorated() == "result"


class TestXrayProperties:
    """Test XrayDecorator properties."""

    def test_agent_property(self):
        """agent property returns _agent."""
        decorator = XrayDecorator()
        mock_agent = Mock()
        decorator._agent = mock_agent

        assert decorator.agent is mock_agent

    def test_task_property(self):
        """task property returns user_prompt."""
        decorator = XrayDecorator()
        decorator._user_prompt = "test prompt"

        assert decorator.task == "test prompt"

    def test_user_prompt_property(self):
        """user_prompt property returns _user_prompt."""
        decorator = XrayDecorator()
        decorator._user_prompt = "test prompt"

        assert decorator.user_prompt == "test prompt"

    def test_messages_property(self):
        """messages property returns _messages."""
        decorator = XrayDecorator()
        messages = [{"role": "user", "content": "hello"}]
        decorator._messages = messages

        assert decorator.messages is messages

    def test_iteration_property(self):
        """iteration property returns _iteration."""
        decorator = XrayDecorator()
        decorator._iteration = 3

        assert decorator.iteration == 3

    def test_previous_tools_property(self):
        """previous_tools property returns _previous_tools."""
        decorator = XrayDecorator()
        tools = ["search", "fetch"]
        decorator._previous_tools = tools

        assert decorator.previous_tools is tools


class TestXrayUpdate:
    """Test XrayDecorator _update method."""

    def test_update_sets_all_context(self):
        """_update sets all context values."""
        decorator = XrayDecorator()
        mock_agent = Mock()
        messages = [{"role": "user", "content": "hello"}]
        previous = ["tool1"]

        decorator._update(mock_agent, "prompt", messages, 5, previous)

        assert decorator._agent is mock_agent
        assert decorator._user_prompt == "prompt"
        assert decorator._messages is messages
        assert decorator._iteration == 5
        assert decorator._previous_tools is previous


class TestXrayClear:
    """Test XrayDecorator _clear method."""

    def test_clear_resets_all_context(self):
        """_clear resets all context values."""
        decorator = XrayDecorator()
        decorator._agent = Mock()
        decorator._user_prompt = "prompt"
        decorator._messages = [{"role": "user"}]
        decorator._iteration = 5
        decorator._previous_tools = ["tool1"]

        decorator._clear()

        assert decorator._agent is None
        assert decorator._user_prompt is None
        assert decorator._messages == []
        assert decorator._iteration is None
        assert decorator._previous_tools == []


class TestXrayRepr:
    """Test XrayDecorator __repr__ method."""

    def test_repr_no_active_context(self):
        """repr when no context is active."""
        decorator = XrayDecorator()
        decorator._clear()

        result = repr(decorator)

        assert "no active context" in result

    def test_repr_with_active_context(self):
        """repr when context is active."""
        decorator = XrayDecorator()
        mock_agent = Mock()
        mock_agent.name = "test_agent"
        decorator._agent = mock_agent
        decorator._user_prompt = "test prompt"
        decorator._iteration = 2
        decorator._messages = [{"role": "user"}]

        result = repr(decorator)

        assert "xray active" in result
        assert "test_agent" in result
        assert "test prompt" in result

    def test_repr_truncates_long_prompt(self):
        """repr truncates long prompts."""
        decorator = XrayDecorator()
        mock_agent = Mock()
        mock_agent.name = "agent"
        decorator._agent = mock_agent
        decorator._user_prompt = "A" * 100
        decorator._iteration = 1
        decorator._messages = []

        result = repr(decorator)

        assert "..." in result


class TestHelperFunctions:
    """Test helper functions."""

    def test_inject_xray_context(self):
        """inject_xray_context updates global xray."""
        mock_agent = Mock()
        messages = [{"role": "user"}]
        previous = ["tool1"]

        inject_xray_context(mock_agent, "prompt", messages, 3, previous)

        assert xray._agent is mock_agent
        assert xray._user_prompt == "prompt"
        assert xray._messages is messages
        assert xray._iteration == 3
        assert xray._previous_tools is previous

        # Cleanup
        clear_xray_context()

    def test_clear_xray_context(self):
        """clear_xray_context resets global xray."""
        xray._agent = Mock()
        xray._user_prompt = "prompt"
        xray._messages = [{}]
        xray._iteration = 5
        xray._previous_tools = ["tool"]

        clear_xray_context()

        assert xray._agent is None
        assert xray._user_prompt is None
        assert xray._messages == []
        assert xray._iteration is None
        assert xray._previous_tools == []

    def test_is_xray_enabled_true(self):
        """is_xray_enabled returns True for decorated functions."""
        @xray
        def my_func():
            pass

        assert is_xray_enabled(my_func) is True

    def test_is_xray_enabled_false_for_plain(self):
        """is_xray_enabled returns False for plain functions."""
        def my_func():
            pass

        assert is_xray_enabled(my_func) is False

    def test_is_xray_enabled_false_when_disabled(self):
        """is_xray_enabled returns False when trace=False."""
        @xray(trace=False)
        def my_func():
            pass

        assert is_xray_enabled(my_func) is False


class TestXrayFormatValuePreview:
    """Test _format_value_preview method."""

    def test_none(self):
        """Format None value."""
        assert xray._format_value_preview(None) == "None"

    def test_short_string(self):
        """Format short string."""
        result = xray._format_value_preview("hello")
        assert result == "'hello'"

    def test_long_string_truncated(self):
        """Format long string is truncated."""
        long_str = "A" * 100
        result = xray._format_value_preview(long_str)
        assert "..." in result
        assert len(result) < 60

    def test_integer(self):
        """Format integer."""
        assert xray._format_value_preview(42) == "42"

    def test_float(self):
        """Format float."""
        assert xray._format_value_preview(3.14) == "3.14"

    def test_bool(self):
        """Format boolean."""
        assert xray._format_value_preview(True) == "True"
        assert xray._format_value_preview(False) == "False"

    def test_dict(self):
        """Format dict as placeholder."""
        assert xray._format_value_preview({"key": "value"}) == "{...}"

    def test_list(self):
        """Format list as placeholder."""
        assert xray._format_value_preview([1, 2, 3]) == "[...]"


class TestXrayFormatValueFull:
    """Test _format_value_full method."""

    def test_none(self):
        """Format None value."""
        assert xray._format_value_full(None) == "None"

    def test_short_string(self):
        """Format short string."""
        result = xray._format_value_full("hello")
        assert result == "'hello'"

    def test_long_string_with_length(self):
        """Format long string shows length."""
        long_str = "A" * 500
        result = xray._format_value_full(long_str)
        assert "500" in result
        assert "chars" in result
        assert "..." in result

    def test_integer(self):
        """Format integer."""
        assert xray._format_value_full(42) == "42"

    def test_float(self):
        """Format float."""
        assert xray._format_value_full(3.14) == "3.14"

    def test_bool(self):
        """Format boolean."""
        assert xray._format_value_full(True) == "True"

    def test_small_dict(self):
        """Format small dict shows contents."""
        result = xray._format_value_full({"a": 1})
        assert "a" in result

    def test_large_dict_truncated(self):
        """Format large dict is truncated."""
        large = {f"key{i}": i for i in range(10)}
        result = xray._format_value_full(large)
        assert "more" in result

    def test_empty_list(self):
        """Format empty list."""
        assert xray._format_value_full([]) == "[]"

    def test_small_list(self):
        """Format small list shows contents."""
        result = xray._format_value_full([1, 2])
        assert result == "[1, 2]"

    def test_large_list_shows_count(self):
        """Format large list shows item count."""
        result = xray._format_value_full(list(range(100)))
        assert "100 items" in result
