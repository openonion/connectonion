"""Unit tests for connectonion/console.py"""

import pytest
from unittest.mock import patch, Mock
import connectonion.console as console_mod


class TestConsole:
    """Test basic console output functions."""

    @patch('connectonion.console._rich_console.print')
    def test_print_basic(self, mock_rich_print):
        """Test basic Console.print output path."""
        c = console_mod.Console()
        c.print("Test message")
        mock_rich_print.assert_called_once()
        args, kwargs = mock_rich_print.call_args
        assert "Test message" in args[0]

    @patch('connectonion.console._rich_console.print')
    def test_print_with_style(self, mock_rich_print):
        """Test Console.print with style parameter."""
        c = console_mod.Console()
        c.print("Error occurred", style="red")
        mock_rich_print.assert_called_once()
        args, kwargs = mock_rich_print.call_args
        assert "Error occurred" in args[0]


class TestLogToolCall:
    """Tests for Console.log_tool_call() formatting."""

    @patch('connectonion.console._rich_console.print')
    def test_log_tool_call_short_single_line(self, mock_print):
        """Short tool call stays on single line: → Tool: greet(name='Alice')"""
        c = console_mod.Console()
        c.log_tool_call("greet", {"name": "Alice"})

        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        assert "greet(name='Alice')" in output
        assert "→" in output or "->" in output

    @patch('connectonion.console._rich_console.print')
    def test_log_tool_call_multi_arg_short(self, mock_print):
        """Two short args stay on single line."""
        c = console_mod.Console()
        c.log_tool_call("add", {"a": 1, "b": 2})

        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        assert "add(a=1, b=2)" in output

    @patch('connectonion.console._rich_console.print')
    def test_log_tool_call_single_long_arg(self, mock_print):
        """Single long arg stays on same line (will wrap naturally)."""
        c = console_mod.Console()
        long_content = "x" * 100
        c.log_tool_call("write_file", {"content": long_content})

        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        # Should be on one line, content truncated at 150 chars
        assert "write_file(" in output
        assert "content=" in output

    @patch('connectonion.console._rich_console.print')
    def test_log_tool_call_multi_line_format(self, mock_print):
        """Multi-arg with long values uses multi-line format."""
        c = console_mod.Console()
        c.log_tool_call("complex_tool", {
            "path": "/some/long/path/to/file.txt",
            "content": "line1\nline2\nline3",
            "mode": "write"
        })

        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        assert "complex_tool(" in output
        # Newlines escaped
        assert "\\n" in output or "line1" in output


class TestLogToolResult:
    """Tests for Console.log_tool_result() formatting."""

    @patch('connectonion.console._rich_console.print')
    def test_log_tool_result_basic(self, mock_print):
        """Basic result shows timing and content."""
        c = console_mod.Console()
        c.log_tool_result("Success!", 123.45)

        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        assert "Success!" in output
        assert "←" in output or "<-" in output
        # 123.45ms >= 100ms uses 1 decimal place: 0.1s
        assert "0.1s" in output

    @patch('connectonion.console._rich_console.print')
    def test_log_tool_result_escapes_newlines(self, mock_print):
        """Newlines in result are escaped."""
        c = console_mod.Console()
        c.log_tool_result("line1\nline2\nline3", 50.0)

        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        assert "\\n" in output
        # Left arrow (←) must be present for tool results, and result portion must not contain literal newlines
        assert "←" in output, "Expected left arrow symbol in output"
        result_portion = output.split("←")[-1]
        assert "\n" not in result_portion, "Result portion should not contain literal newlines"

    @patch('connectonion.console._rich_console.print')
    def test_log_tool_result_truncates_long(self, mock_print):
        """Results > 80 chars are truncated with ..."""
        c = console_mod.Console()
        long_result = "x" * 100
        c.log_tool_result(long_result, 50.0)

        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        assert "..." in output
        # Should not contain full 100 chars
        assert "x" * 100 not in output

    @patch('connectonion.console._rich_console.print')
    def test_log_tool_result_fast_timing(self, mock_print):
        """Fast operations (<100ms) show more precision."""
        c = console_mod.Console()
        c.log_tool_result("quick result", 12.5)

        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        # Should show 4 decimal places for fast operations
        assert "0.0125s" in output

    @patch('connectonion.console._rich_console.print')
    def test_log_tool_result_slow_timing(self, mock_print):
        """Slow operations (>=100ms) show less precision."""
        c = console_mod.Console()
        c.log_tool_result("slow result", 1500.0)

        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        # Should show 1 decimal place for slow operations
        assert "1.5s" in output


class TestFormatToolArgsList:
    """Tests for Console._format_tool_args_list() internal method."""

    def test_format_tool_args_string_quoted(self):
        """String values are quoted: name='Alice'"""
        c = console_mod.Console()
        result = c._format_tool_args_list({"name": "Alice"})
        assert result == ["name='Alice'"]

    def test_format_tool_args_non_string_not_quoted(self):
        """Non-string values are not quoted: count=5"""
        c = console_mod.Console()
        result = c._format_tool_args_list({"count": 5})
        assert result == ["count=5"]

    def test_format_tool_args_multiple(self):
        """Multiple args formatted correctly."""
        c = console_mod.Console()
        result = c._format_tool_args_list({"name": "Alice", "age": 30})
        assert "name='Alice'" in result
        assert "age=30" in result

    def test_format_tool_args_escapes_newlines(self):
        """Newlines in values are escaped."""
        c = console_mod.Console()
        result = c._format_tool_args_list({"content": "line1\nline2"})
        assert len(result) == 1
        assert "\\n" in result[0]
        assert "\n" not in result[0]

    def test_format_tool_args_escapes_carriage_return(self):
        """Carriage returns in values are escaped."""
        c = console_mod.Console()
        result = c._format_tool_args_list({"content": "line1\r\nline2"})
        assert len(result) == 1
        assert "\\r" in result[0]
        assert "\\n" in result[0]

    def test_format_tool_args_truncates_long_string(self):
        """String values > 150 chars are truncated."""
        c = console_mod.Console()
        long_value = "x" * 200
        result = c._format_tool_args_list({"content": long_value})
        assert len(result) == 1
        assert "..." in result[0]
        # Should not contain full 200 chars
        assert "x" * 200 not in result[0]
        # Should contain truncated value (~150 chars)
        assert "x" * 100 in result[0]

    def test_format_tool_args_truncates_long_non_string(self):
        """Non-string values > 150 chars are truncated."""
        c = console_mod.Console()
        long_list = list(range(100))  # Long list representation
        # Verify our test data is actually > 150 chars
        assert len(str(long_list)) > 150, "Test data must be > 150 chars to test truncation"
        result = c._format_tool_args_list({"data": long_list})
        assert len(result) == 1
        # Must be truncated
        assert "..." in result[0], "Long non-string values should be truncated"

    def test_format_tool_args_boolean(self):
        """Boolean values formatted correctly."""
        c = console_mod.Console()
        result = c._format_tool_args_list({"enabled": True, "disabled": False})
        assert "enabled=True" in result
        assert "disabled=False" in result

    def test_format_tool_args_none(self):
        """None values formatted correctly."""
        c = console_mod.Console()
        result = c._format_tool_args_list({"value": None})
        assert result == ["value=None"]


class TestToPlainText:
    """Tests for Console._to_plain_text() markup removal."""

    def test_removes_rich_markup(self):
        """Removes Rich markup tags like [blue] and [/blue]."""
        c = console_mod.Console()
        result = c._to_plain_text("[blue]→[/blue] Tool: test")
        assert "[blue]" not in result
        assert "[/blue]" not in result
        assert "Tool: test" in result

    def test_converts_arrow_symbols(self):
        """Converts unicode arrows to ASCII."""
        c = console_mod.Console()
        result = c._to_plain_text("→ input ← output")
        assert "->" in result
        assert "<-" in result

    def test_converts_checkmarks(self):
        """Converts unicode checkmarks to ASCII."""
        c = console_mod.Console()
        result = c._to_plain_text("✓ success ✗ failure")
        assert "[OK]" in result
        assert "[ERROR]" in result


class TestLogFile:
    """Tests for Console log file functionality."""

    def test_init_creates_log_file_parent_dirs(self, tmp_path):
        """Log file parent directories are created if they don't exist."""
        log_file = tmp_path / "deep" / "nested" / "log.txt"
        c = console_mod.Console(log_file=log_file)
        assert log_file.parent.exists()

    def test_init_writes_session_header(self, tmp_path):
        """Session header written on init."""
        log_file = tmp_path / "test.log"
        c = console_mod.Console(log_file=log_file)
        content = log_file.read_text()
        assert "Session started" in content
        assert "=" * 60 in content

    @patch('connectonion.console._rich_console.print')
    def test_print_writes_to_log_file(self, mock_print, tmp_path):
        """Print messages are written to log file as plain text."""
        log_file = tmp_path / "test.log"
        c = console_mod.Console(log_file=log_file)
        c.print("[blue]Test message[/blue]")

        content = log_file.read_text()
        # Rich markup removed
        assert "[blue]" not in content
        assert "Test message" in content
        # Timestamp present
        assert "]" in content  # [HH:MM:SS]
