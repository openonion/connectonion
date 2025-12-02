"""Unit tests for connectonion/useful_tools/shell.py

Tests cover:
- Shell.run: basic command execution
- Shell.run_in_dir: execution in specific directory
- Output truncation
- Error handling
"""

import pytest
import tempfile
import os
from pathlib import Path
from connectonion.useful_tools.shell import Shell


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

    def test_run_truncates_long_output(self):
        """Test that long output is truncated."""
        shell = Shell()
        # Generate output longer than 1000 chars
        result = shell.run("python3 -c \"print('A' * 2000)\"")
        assert "truncated" in result
        assert "2000" in result or "2,000" in result

    def test_run_with_cwd(self):
        """Test running command with custom working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            shell = Shell(cwd=tmpdir)
            result = shell.run("pwd")
            assert tmpdir in result


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

    def test_run_in_dir_returns_stderr(self):
        """Test that stderr is captured in run_in_dir."""
        shell = Shell()
        result = shell.run_in_dir("ls /nonexistent_dir_12345", "/tmp")
        assert "STDERR:" in result or "No such file" in result

    def test_run_in_dir_shows_exit_code_on_failure(self):
        """Test that non-zero exit codes are reported."""
        shell = Shell()
        result = shell.run_in_dir("exit 42", "/tmp")
        assert "Exit code: 42" in result

    def test_run_in_dir_no_output(self):
        """Test command with no output in specific directory."""
        shell = Shell()
        result = shell.run_in_dir("true", "/tmp")
        assert result == "(no output)"

    def test_run_in_dir_truncates_long_output(self):
        """Test that long output is truncated in run_in_dir."""
        shell = Shell()
        result = shell.run_in_dir("python3 -c \"print('B' * 2000)\"", "/tmp")
        assert "truncated" in result


class TestShellIntegration:
    """Integration tests for Shell tool."""

    def test_shell_can_be_used_as_agent_tool(self):
        """Test that Shell can be registered with agent."""
        from connectonion import Agent
        from connectonion.llm import LLMResponse
        from connectonion.usage import TokenUsage
        from unittest.mock import Mock

        mock_llm = Mock()
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

    def test_shell_methods_have_correct_schema(self):
        """Test that shell methods generate correct tool schemas."""
        from connectonion.tool_factory import create_tool_from_function

        shell = Shell()
        run_tool = create_tool_from_function(shell.run)
        run_in_dir_tool = create_tool_from_function(shell.run_in_dir)

        # Check run schema
        assert run_tool.name == "run"
        run_schema = run_tool.to_function_schema()
        assert "command" in run_schema["parameters"]["properties"]

        # Check run_in_dir schema
        assert run_in_dir_tool.name == "run_in_dir"
        run_in_dir_schema = run_in_dir_tool.to_function_schema()
        assert "command" in run_in_dir_schema["parameters"]["properties"]
        assert "directory" in run_in_dir_schema["parameters"]["properties"]
