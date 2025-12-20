"""Unit tests for connectonion/debugger_ui.py

Tests cover:
- BreakpointAction enum
- BreakpointContext dataclass
- AutoDebugUI class methods:
  - show_welcome
  - get_user_prompt
  - show_executing
  - show_result
  - show_interrupted
  - show_breakpoint
  - edit_value
  - display_explanation
  - display_execution_analysis
- Private helper methods:
  - _format_value_for_repl
  - _format_string_value
  - _format_dict_value
  - _format_list_value
"""

import pytest
from unittest.mock import patch, Mock, MagicMock


class TestBreakpointAction:
    """Tests for BreakpointAction enum."""

    def test_breakpoint_action_values(self):
        """Test BreakpointAction has correct values."""
        from connectonion.debug.auto_debug_ui import BreakpointAction

        assert BreakpointAction.CONTINUE.value == "continue"
        assert BreakpointAction.EDIT.value == "edit"
        assert BreakpointAction.WHY.value == "why"
        assert BreakpointAction.QUIT.value == "quit"

    def test_breakpoint_action_is_enum(self):
        """Test BreakpointAction is an Enum."""
        from connectonion.debug.auto_debug_ui import BreakpointAction
        from enum import Enum

        assert issubclass(BreakpointAction, Enum)


class TestBreakpointContext:
    """Tests for BreakpointContext dataclass."""

    def test_breakpoint_context_creation(self):
        """Test creating BreakpointContext with required fields."""
        from connectonion.debug.auto_debug_ui import BreakpointContext

        context = BreakpointContext(
            tool_name="search",
            tool_args={"query": "test"},
            trace_entry={"result": "Found it", "status": "success"},
            user_prompt="Find something",
            iteration=1,
            max_iterations=10,
            previous_tools=["validate"]
        )

        assert context.tool_name == "search"
        assert context.tool_args == {"query": "test"}
        assert context.user_prompt == "Find something"
        assert context.iteration == 1
        assert context.max_iterations == 10
        assert context.previous_tools == ["validate"]

    def test_breakpoint_context_optional_fields(self):
        """Test BreakpointContext optional fields default to None."""
        from connectonion.debug.auto_debug_ui import BreakpointContext

        context = BreakpointContext(
            tool_name="search",
            tool_args={},
            trace_entry={},
            user_prompt="Find",
            iteration=1,
            max_iterations=10,
            previous_tools=[]
        )

        assert context.next_actions is None
        assert context.tool_function is None


class TestAutoDebugUIInit:
    """Tests for AutoDebugUI initialization."""

    def test_debugger_ui_init(self):
        """Test AutoDebugUI initializes with console and style."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        ui = AutoDebugUI()

        assert ui.console is not None
        assert ui.style is not None


class TestAutoDebugUIShowWelcome:
    """Tests for show_welcome method."""

    def test_show_welcome_displays_agent_name(self):
        """Test show_welcome displays agent name in panel."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI
        from rich.panel import Panel

        ui = AutoDebugUI()
        ui.console = Mock()

        ui.show_welcome("test-agent")

        ui.console.print.assert_called_once()
        call_args = ui.console.print.call_args[0][0]
        # Check that it's a Panel
        assert isinstance(call_args, Panel)


class TestAutoDebugUIGetUserPrompt:
    """Tests for get_user_prompt method."""

    @patch('builtins.input')
    def test_get_user_prompt_returns_input(self, mock_input):
        """Test get_user_prompt returns user input."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        mock_input.return_value = "Find something"
        ui = AutoDebugUI()

        result = ui.get_user_prompt()

        assert result == "Find something"

    @patch('builtins.input')
    def test_get_user_prompt_quit_returns_none(self, mock_input):
        """Test get_user_prompt returns None on quit."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        mock_input.return_value = "quit"
        ui = AutoDebugUI()
        ui.console = Mock()

        result = ui.get_user_prompt()

        assert result is None

    @patch('builtins.input')
    def test_get_user_prompt_exit_returns_none(self, mock_input):
        """Test get_user_prompt returns None on exit."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        mock_input.return_value = "exit"
        ui = AutoDebugUI()
        ui.console = Mock()

        result = ui.get_user_prompt()

        assert result is None


class TestAutoDebugUIShowExecuting:
    """Tests for show_executing method."""

    def test_show_executing_displays_prompt(self):
        """Test show_executing displays the prompt."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        ui = AutoDebugUI()
        ui.console = Mock()

        ui.show_executing("Find something")

        ui.console.print.assert_called_once()
        call_args = str(ui.console.print.call_args)
        assert "Find something" in call_args


class TestAutoDebugUIShowResult:
    """Tests for show_result method."""

    def test_show_result_displays_result(self):
        """Test show_result displays the result."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        ui = AutoDebugUI()
        ui.console = Mock()

        ui.show_result("Found it!")

        ui.console.print.assert_called_once()
        call_args = str(ui.console.print.call_args)
        assert "Found it!" in call_args


class TestAutoDebugUIShowInterrupted:
    """Tests for show_interrupted method."""

    def test_show_interrupted_displays_message(self):
        """Test show_interrupted displays interrupted message."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        ui = AutoDebugUI()
        ui.console = Mock()

        ui.show_interrupted()

        ui.console.print.assert_called_once()
        call_args = str(ui.console.print.call_args)
        assert "interrupted" in call_args.lower()


class TestAutoDebugUIFormatValueForRepl:
    """Tests for _format_value_for_repl method."""

    def test_format_none_value(self):
        """Test formatting None value."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        ui = AutoDebugUI()
        result = ui._format_value_for_repl(None)

        assert "None" in result

    def test_format_bool_value(self):
        """Test formatting boolean value."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        ui = AutoDebugUI()
        result = ui._format_value_for_repl(True)

        assert "True" in result

    def test_format_int_value(self):
        """Test formatting integer value."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        ui = AutoDebugUI()
        result = ui._format_value_for_repl(42)

        assert "42" in result

    def test_format_short_string(self):
        """Test formatting short string."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        ui = AutoDebugUI()
        result = ui._format_value_for_repl("hello")

        assert "hello" in result

    def test_format_long_string_truncated(self):
        """Test formatting long string is truncated."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        ui = AutoDebugUI()
        long_string = "x" * 200
        result = ui._format_value_for_repl(long_string)

        assert "..." in result
        assert "chars" in result

    def test_format_empty_dict(self):
        """Test formatting empty dict."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        ui = AutoDebugUI()
        result = ui._format_value_for_repl({})

        assert "{}" in result or "dim" in result

    def test_format_small_dict(self):
        """Test formatting small dict."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        ui = AutoDebugUI()
        result = ui._format_value_for_repl({"a": 1})

        assert "a" in result or "1" in result

    def test_format_empty_list(self):
        """Test formatting empty list."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        ui = AutoDebugUI()
        result = ui._format_value_for_repl([])

        assert "[]" in result or "dim" in result

    def test_format_callable(self):
        """Test formatting callable shows function indicator."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        ui = AutoDebugUI()
        result = ui._format_value_for_repl(lambda x: x)

        assert "function" in result


class TestAutoDebugUIDisplayExplanation:
    """Tests for display_explanation method."""

    @patch('builtins.input')
    def test_display_explanation_shows_panel(self, mock_input):
        """Test display_explanation shows explanation in panel."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI, BreakpointContext

        mock_input.return_value = ""  # Press enter to continue
        ui = AutoDebugUI()
        ui.console = Mock()

        context = BreakpointContext(
            tool_name="search",
            tool_args={},
            trace_entry={},
            user_prompt="Find",
            iteration=1,
            max_iterations=10,
            previous_tools=[]
        )

        ui.display_explanation("Tool was chosen because...", context)

        # Should print the panel
        assert ui.console.print.called


class TestAutoDebugUIDisplayExecutionAnalysis:
    """Tests for display_execution_analysis method."""

    @patch('builtins.input')
    def test_display_execution_analysis_shows_analysis(self, mock_input):
        """Test display_execution_analysis shows analysis details."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        mock_input.return_value = ""  # Press enter to continue
        ui = AutoDebugUI()
        ui.console = Mock()

        # Create mock analysis object
        mock_analysis = Mock()
        mock_analysis.task_completed = True
        mock_analysis.completion_explanation = "Task completed successfully"
        mock_analysis.overall_quality = "good"
        mock_analysis.problems_identified = []
        mock_analysis.system_prompt_suggestions = []
        mock_analysis.key_insights = ["Efficient execution"]

        ui.display_execution_analysis(mock_analysis)

        # Should print multiple times for different sections
        assert ui.console.print.called


class TestAutoDebugUIEditValue:
    """Tests for edit_value method."""

    @patch('sys.stdin')
    def test_edit_value_no_stdin_returns_empty(self, mock_stdin):
        """Test edit_value returns empty dict when no stdin."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI, BreakpointContext

        mock_stdin.isatty.return_value = False
        ui = AutoDebugUI()
        ui.console = Mock()

        context = BreakpointContext(
            tool_name="search",
            tool_args={},
            trace_entry={"result": "Found"},
            user_prompt="Find",
            iteration=1,
            max_iterations=10,
            previous_tools=[]
        )

        result = ui.edit_value(context)

        assert result == {}


class TestAutoDebugUIActionMenu:
    """Tests for _show_action_menu method."""

    @patch('builtins.input')
    def test_simple_input_fallback_continue(self, mock_input):
        """Test simple input fallback returns CONTINUE on 'c'."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI, BreakpointAction

        mock_input.return_value = "c"
        ui = AutoDebugUI()
        ui.console = Mock()

        result = ui._simple_input_fallback()

        assert result == BreakpointAction.CONTINUE

    @patch('builtins.input')
    def test_simple_input_fallback_edit(self, mock_input):
        """Test simple input fallback returns EDIT on 'e'."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI, BreakpointAction

        mock_input.return_value = "e"
        ui = AutoDebugUI()
        ui.console = Mock()

        result = ui._simple_input_fallback()

        assert result == BreakpointAction.EDIT

    @patch('builtins.input')
    def test_simple_input_fallback_why(self, mock_input):
        """Test simple input fallback returns WHY on 'w'."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI, BreakpointAction

        mock_input.return_value = "w"
        ui = AutoDebugUI()
        ui.console = Mock()

        result = ui._simple_input_fallback()

        assert result == BreakpointAction.WHY

    @patch('builtins.input')
    def test_simple_input_fallback_quit(self, mock_input):
        """Test simple input fallback returns QUIT on 'q'."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI, BreakpointAction

        mock_input.return_value = "q"
        ui = AutoDebugUI()
        ui.console = Mock()

        result = ui._simple_input_fallback()

        assert result == BreakpointAction.QUIT

    @patch('builtins.input')
    def test_simple_input_fallback_keyboard_interrupt(self, mock_input):
        """Test simple input fallback returns QUIT on KeyboardInterrupt."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI, BreakpointAction

        mock_input.side_effect = KeyboardInterrupt
        ui = AutoDebugUI()
        ui.console = Mock()

        result = ui._simple_input_fallback()

        assert result == BreakpointAction.QUIT


class TestAutoDebugUIGetToolSource:
    """Tests for _get_tool_source method."""

    def test_get_tool_source_no_function(self):
        """Test _get_tool_source returns None when no function."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI, BreakpointContext

        ui = AutoDebugUI()

        context = BreakpointContext(
            tool_name="search",
            tool_args={},
            trace_entry={},
            user_prompt="Find",
            iteration=1,
            max_iterations=10,
            previous_tools=[],
            tool_function=None
        )

        source, file_info, line = ui._get_tool_source(context)

        assert source is None
        assert "unavailable" in file_info

    def test_get_tool_source_with_function(self):
        """Test _get_tool_source returns source for valid function."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI, BreakpointContext

        ui = AutoDebugUI()

        def sample_tool():
            """A sample tool."""
            return "result"

        context = BreakpointContext(
            tool_name="sample",
            tool_args={},
            trace_entry={},
            user_prompt="Test",
            iteration=1,
            max_iterations=10,
            previous_tools=[],
            tool_function=sample_tool
        )

        source, file_info, line = ui._get_tool_source(context)

        assert source is not None
        assert "sample_tool" in source
        assert line > 0


class TestAutoDebugUIDisplayModifications:
    """Tests for _display_modifications method."""

    def test_display_modifications_shows_changes(self):
        """Test _display_modifications shows modified values."""
        from connectonion.debug.auto_debug_ui import AutoDebugUI

        ui = AutoDebugUI()
        ui.console = Mock()

        modifications = {
            'result': 'new result',
            'iteration': 5
        }

        ui._display_modifications(modifications)

        # Should print modifications
        assert ui.console.print.called
        # Check that result and iteration are mentioned
        call_str = str(ui.console.print.call_args_list)
        assert 'result' in call_str
        assert 'iteration' in call_str
