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


class TestLogToolResult:
    """Tests for Console tool logging (log_tool_call + log_tool_result).

    New design: log_tool_call stores info, log_tool_result prints full line.
    Output format: [co]   ▸ greet(name="Alice")             ✓ 0.8s
    """

    @patch('connectonion.console._rich_console.print')
    def test_log_tool_result_basic(self, mock_print):
        """Tool result shows triangle, tool call, checkmark, and timing."""
        c = console_mod.Console()
        c.log_tool_call("greet", {"name": "Alice"})
        c.log_tool_result("Hello!", 123.45)

        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        # Triangle symbol for tool action
        assert "▸" in output
        # Tool name and args
        assert "greet" in output
        assert "Alice" in output
        # Success checkmark
        assert "✓" in output
        # Timing (123.45ms >= 100ms shows 0.1s)
        assert "0.1s" in output

    @patch('connectonion.console._rich_console.print')
    def test_log_tool_result_fast_timing(self, mock_print):
        """Fast operations (<100ms) show more precision."""
        c = console_mod.Console()
        c.log_tool_call("quick", {})
        c.log_tool_result("done", 12.5)

        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        # Fast timing shows 2 decimal places
        assert "0.01s" in output

    @patch('connectonion.console._rich_console.print')
    def test_log_tool_result_slow_timing(self, mock_print):
        """Slow operations (>=100ms) show less precision."""
        c = console_mod.Console()
        c.log_tool_call("slow", {})
        c.log_tool_result("done", 1500.0)

        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        # Slow timing shows 1 decimal place
        assert "1.5s" in output

    @patch('connectonion.console._rich_console.print')
    def test_log_tool_result_error(self, mock_print):
        """Failed tool shows error symbol instead of checkmark."""
        c = console_mod.Console()
        c.log_tool_call("fail", {})
        c.log_tool_result("error", 50.0, success=False)

        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        # Error symbol
        assert "✗" in output


class TestFormatToolDisplay:
    """Tests for Console._format_tool_display() smart truncation."""

    def test_format_tool_display_no_args(self):
        """Tool with no args: tool()"""
        c = console_mod.Console()
        result = c._format_tool_display("search", {})
        assert result == "search()"

    def test_format_tool_display_short_args(self):
        """Short args show full values."""
        c = console_mod.Console()
        result = c._format_tool_display("greet", {"name": "Alice"})
        assert result == 'greet(name="Alice")'

    def test_format_tool_display_multi_args(self):
        """Multiple short args show all."""
        c = console_mod.Console()
        result = c._format_tool_display("add", {"a": 1, "b": 2})
        assert "a=1" in result
        assert "b=2" in result

    def test_format_tool_display_truncates_long_value(self):
        """Long values get truncated."""
        c = console_mod.Console()
        long_val = "x" * 100
        result = c._format_tool_display("write", {"content": long_val})
        assert "write(" in result
        assert "content=" in result
        assert "..." in result
        # Should not contain full 100 chars
        assert "x" * 100 not in result


class TestToPlainText:
    """Tests for Console._to_plain_text() markup removal."""

    def test_removes_rich_markup(self):
        """Removes Rich markup tags like [blue] and [/blue]."""
        c = console_mod.Console()
        result = c._to_plain_text("[blue]▸[/blue] Tool: test")
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


def _collect_print_output(mock_print):
    """Collect all printed output, handling empty print() calls."""
    parts = []
    for call in mock_print.call_args_list:
        if call[0]:  # Has positional args
            parts.append(str(call[0][0]))
    return "".join(parts)


class TestPrintBanner:
    """Tests for Console.print_banner() banner output."""

    @patch('connectonion.console._rich_console.print')
    def test_print_banner_shows_agent_name(self, mock_print):
        """Banner shows agent name."""
        c = console_mod.Console()
        c.print_banner(agent_name="test-agent", model="gpt-4", tools=3)

        output = _collect_print_output(mock_print)
        assert "test-agent" in output

    @patch('connectonion.console._rich_console.print')
    def test_print_banner_shows_onion_circles(self, mock_print):
        """Banner shows onion layer circles."""
        c = console_mod.Console()
        c.print_banner(agent_name="test", model="gpt-4", tools=1)

        output = _collect_print_output(mock_print)
        # Onion circles
        assert "○" in output
        assert "◎" in output
        assert "●" in output

    @patch('connectonion.console._rich_console.print')
    def test_print_banner_shows_tools_count(self, mock_print):
        """Banner shows correct tools count with proper pluralization."""
        c = console_mod.Console()
        c.print_banner(agent_name="test", model="gpt-4", tools=5)

        output = _collect_print_output(mock_print)
        assert "5 tools" in output

    @patch('connectonion.console._rich_console.print')
    def test_print_banner_singular_tool(self, mock_print):
        """Banner shows '1 tool' not '1 tools'."""
        c = console_mod.Console()
        c.print_banner(agent_name="test", model="gpt-4", tools=1)

        output = _collect_print_output(mock_print)
        assert "1 tool" in output
        assert "1 tools" not in output

    @patch('connectonion.console._rich_console.print')
    def test_print_banner_shows_log_dir(self, mock_print):
        """Banner shows log directory paths when provided."""
        c = console_mod.Console()
        c.print_banner(agent_name="test", model="gpt-4", tools=1, log_dir=".co/")

        output = _collect_print_output(mock_print)
        assert ".co/logs/" in output
        assert ".co/sessions/" in output

    @patch('connectonion.console._rich_console.print')
    def test_print_banner_shows_separator(self, mock_print):
        """Banner shows separator lines."""
        c = console_mod.Console()
        c.print_banner(agent_name="test", model="gpt-4", tools=1)

        output = _collect_print_output(mock_print)
        # Separator uses box drawing character
        assert "─" in output


class TestLLMLogging:
    """Tests for LLM request/response logging."""

    @patch('connectonion.console._rich_console.print')
    def test_log_llm_request_shows_circle(self, mock_print):
        """LLM request shows empty circle (AI thinking)."""
        c = console_mod.Console()
        session = {'messages': [], 'iteration': 1}
        c.print_llm_request("gpt-4", session, max_iterations=10)

        output = mock_print.call_args[0][0]
        # Empty circle for request
        assert "○" in output
        assert "gpt-4" in output

    @patch('connectonion.console._rich_console.print')
    def test_log_llm_response_shows_flash(self, mock_print):
        """LLM response shows flash symbol (thinking complete)."""
        c = console_mod.Console()
        # Create mock usage object
        usage = Mock()
        usage.input_tokens = 100
        usage.output_tokens = 50
        usage.cost = 0.001

        c.log_llm_response("gpt-4", duration_ms=1000.0, tool_count=0, usage=usage)

        output = mock_print.call_args[0][0]
        # Flash symbol for LLM completion
        assert "⚡" in output
        # Model name
        assert "gpt-4" in output
