"""Unit tests for connectonion/useful_tools/shell.py and bash.py

Tests cover:
- Shell class: cross-platform shell execution
- bash function: Unix/Mac specific bash execution
"""

import pytest
import tempfile
import platform
from pathlib import Path
from connectonion.useful_tools.shell import Shell
from connectonion.useful_tools.bash import bash


# =============================================================================
# Shell Class Tests (Cross-Platform)
# =============================================================================

class TestShellRun:
    """Tests for Shell.run method."""

    def test_run_simple_command(self):
        """Test running a simple command."""
        shell = Shell()
        result = shell.run("echo hello")
        assert "hello" in result

    def test_run_returns_stdout(self):
        """Test that stdout is captured."""
        shell = Shell()
        result = shell.run("echo 'test output'")
        assert "test output" in result

    def test_run_returns_stderr(self):
        """Test that stderr is captured."""
        shell = Shell()
        result = shell.run("ls /nonexistent_dir_12345")
        assert "STDERR:" in result or "No such file" in result

    def test_run_shows_exit_code_on_failure(self):
        """Test that non-zero exit codes are reported."""
        shell = Shell()
        result = shell.run("exit 1")
        assert "Exit code: 1" in result

    def test_run_no_output(self):
        """Test command with no output."""
        shell = Shell()
        result = shell.run("true")
        assert result == "(no output)"

    def test_run_with_cwd(self):
        """Test running command with custom working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            shell = Shell(cwd=tmpdir)
            result = shell.run("pwd")
            assert tmpdir in result

    def test_run_timeout(self):
        """Test that timeout returns error message."""
        shell = Shell()
        result = shell.run("sleep 5", timeout=1)
        assert "timed out" in result


class TestShellRunInDir:
    """Tests for Shell.run_in_dir method."""

    def test_run_in_dir_changes_directory(self):
        """Test that command runs in specified directory."""
        shell = Shell()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = shell.run_in_dir("pwd", tmpdir)
            assert tmpdir in result

    def test_run_in_dir_creates_file(self):
        """Test that file operations work in the specified directory."""
        shell = Shell()
        with tempfile.TemporaryDirectory() as tmpdir:
            shell.run_in_dir("touch test_file.txt", tmpdir)
            assert (Path(tmpdir) / "test_file.txt").exists()


class TestShellIntegration:
    """Integration tests for Shell tool."""

    def test_shell_can_be_used_as_agent_tool(self):
        """Test that Shell can be registered with agent."""
        from connectonion import Agent
        from connectonion.core.llm import LLMResponse
        from connectonion.core.usage import TokenUsage
        from unittest.mock import Mock

        mock_llm = Mock()
        mock_llm.model = "test-model"
        mock_llm.complete.return_value = LLMResponse(
            content="Test",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

        shell = Shell()
        agent = Agent(
            "test",
            llm=mock_llm,
            tools=[shell],
            log=False,
        )

        # Verify shell methods are accessible
        assert agent.tools.get("run") is not None
        assert agent.tools.get("run_in_dir") is not None


# =============================================================================
# Bash Function Tests (Unix/Mac Only)
# =============================================================================

@pytest.mark.skipif(platform.system() == "Windows", reason="bash is Unix/Mac only")
class TestBashBasic:
    """Tests for basic bash function usage."""

    def test_bash_simple_command(self):
        """Test running a simple command."""
        result = bash("echo hello", "Echo test")
        assert "hello" in result

    def test_bash_returns_stdout(self):
        """Test that stdout is captured."""
        result = bash("echo 'test output'", "Echo test output")
        assert "test output" in result

    def test_bash_returns_stderr(self):
        """Test that stderr is captured."""
        result = bash("ls /nonexistent_dir_12345", "List nonexistent dir")
        assert "STDERR:" in result or "No such file" in result

    def test_bash_shows_exit_code_on_failure(self):
        """Test that non-zero exit codes are reported."""
        result = bash("exit 1", "Exit with error")
        assert "Exit code: 1" in result

    def test_bash_no_output(self):
        """Test command with no output."""
        result = bash("true", "Run true command")
        assert result == "(no output)"

    def test_bash_truncates_long_output(self):
        """Test that long output is truncated."""
        result = bash("python3 -c \"print('A' * 15000)\"", "Print long string")
        assert "truncated" in result


@pytest.mark.skipif(platform.system() == "Windows", reason="bash is Unix/Mac only")
class TestBashWithCwd:
    """Tests for bash with custom working directory."""

    def test_bash_with_cwd(self):
        """Test running command with custom working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = bash("pwd", "Print working dir", cwd=tmpdir)
            assert tmpdir in result

    def test_bash_cwd_creates_file(self):
        """Test that file operations work in the specified directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bash("touch test_file.txt", "Create test file", cwd=tmpdir)
            assert (Path(tmpdir) / "test_file.txt").exists()


@pytest.mark.skipif(platform.system() == "Windows", reason="bash is Unix/Mac only")
class TestBashWithTimeout:
    """Tests for bash timeout handling."""

    def test_bash_timeout_returns_error(self):
        """Test that timeout returns error message."""
        result = bash("sleep 5", "Sleep command", timeout=1)
        assert "timed out" in result


@pytest.mark.skipif(platform.system() == "Windows", reason="bash is Unix/Mac only")
class TestBashIntegration:
    """Integration tests for bash tool with Agent."""

    def test_bash_can_be_used_as_agent_tool(self):
        """Test that bash can be registered with agent."""
        from connectonion import Agent
        from connectonion.core.llm import LLMResponse
        from connectonion.core.usage import TokenUsage
        from unittest.mock import Mock

        mock_llm = Mock()
        mock_llm.model = "test-model"
        mock_llm.complete.return_value = LLMResponse(
            content="Test",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

        agent = Agent(
            "test",
            llm=mock_llm,
            tools=[bash],
            log=False,
        )

        # Verify bash is accessible as a tool
        assert agent.tools.get("bash") is not None

    def test_bash_has_correct_schema(self):
        """Test that bash generates correct tool schema."""
        from connectonion.core.tool_factory import create_tool_from_function

        bash_tool = create_tool_from_function(bash)

        # Check schema
        assert bash_tool.name == "bash"
        schema = bash_tool.to_function_schema()
        assert "command" in schema["parameters"]["properties"]
        assert "cwd" in schema["parameters"]["properties"]
        assert "timeout" in schema["parameters"]["properties"]


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
class TestBashOnWindows:
    """Tests for bash behavior on Windows."""

    def test_bash_returns_error_on_windows(self):
        """Test that bash returns error on Windows."""
        result = bash("echo test", "Echo test")
        assert "Unix/Mac only" in result
