"""Unit tests for connectonion/useful_tools/slash_command.py

Tests cover:
- SlashCommand initialization
- load: loading commands from file paths
- _parse_file: parsing YAML frontmatter
- filter_tools: filtering tools based on allowed list
- list_all: listing all available commands
- is_custom: checking if command is custom
"""

import pytest
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
import tempfile
import os

from connectonion.useful_tools.slash_command import SlashCommand


SAMPLE_COMMAND = """---
name: test-command
description: A test command
tools:
  - Gmail.search_emails
  - WebFetch
---
This is the prompt template.
"""

SAMPLE_COMMAND_NO_TOOLS = """---
name: simple
description: Simple command with all tools
---
Just a prompt, no tool restrictions.
"""

SAMPLE_COMMAND_MISSING_NAME = """---
description: No name field
---
Prompt here.
"""

SAMPLE_COMMAND_NO_FRONTMATTER = """This has no frontmatter"""

SAMPLE_COMMAND_MALFORMED = """---
name: broken
Only one delimiter"""


class TestSlashCommandInit:
    """Tests for SlashCommand initialization."""

    def test_init_with_all_params(self):
        """Test initialization with all parameters."""
        cmd = SlashCommand(
            name="test",
            description="Test command",
            prompt="Do something",
            tools=["tool1", "tool2"],
            is_custom=True
        )
        assert cmd.name == "test"
        assert cmd.description == "Test command"
        assert cmd.prompt == "Do something"
        assert cmd.tools == ["tool1", "tool2"]
        assert cmd.is_custom is True

    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        cmd = SlashCommand(
            name="test",
            description="Test",
            prompt="Prompt"
        )
        assert cmd.tools is None
        assert cmd.is_custom is False


class TestSlashCommandLoad:
    """Tests for SlashCommand.load method."""

    def test_load_custom_command(self):
        """Test loading a custom command from .co/commands/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .co/commands directory
            cmd_dir = Path(tmpdir) / ".co" / "commands"
            cmd_dir.mkdir(parents=True)

            # Create command file
            cmd_file = cmd_dir / "test.md"
            cmd_file.write_text(SAMPLE_COMMAND)

            # Change to temp directory
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                cmd = SlashCommand.load("test")
                assert cmd is not None
                assert cmd.name == "test-command"
                assert cmd.is_custom is True
            finally:
                os.chdir(original_cwd)

    def test_load_builtin_command(self):
        """Test loading a built-in command from commands/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create commands directory (no .co prefix)
            cmd_dir = Path(tmpdir) / "commands"
            cmd_dir.mkdir(parents=True)

            # Create command file
            cmd_file = cmd_dir / "builtin.md"
            cmd_file.write_text(SAMPLE_COMMAND)

            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                cmd = SlashCommand.load("builtin")
                assert cmd is not None
                assert cmd.is_custom is False
            finally:
                os.chdir(original_cwd)

    def test_load_custom_overrides_builtin(self):
        """Test that custom command overrides built-in with same name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create both directories
            custom_dir = Path(tmpdir) / ".co" / "commands"
            custom_dir.mkdir(parents=True)
            builtin_dir = Path(tmpdir) / "commands"
            builtin_dir.mkdir(parents=True)

            # Create both files with same name
            (custom_dir / "same.md").write_text(SAMPLE_COMMAND)
            (builtin_dir / "same.md").write_text(SAMPLE_COMMAND_NO_TOOLS)

            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                cmd = SlashCommand.load("same")
                assert cmd is not None
                assert cmd.is_custom is True  # Custom takes precedence
            finally:
                os.chdir(original_cwd)

    def test_load_nonexistent_command(self):
        """Test loading a command that doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                cmd = SlashCommand.load("nonexistent")
                assert cmd is None
            finally:
                os.chdir(original_cwd)


class TestSlashCommandParseFile:
    """Tests for SlashCommand._parse_file method."""

    def test_parse_file_with_tools(self):
        """Test parsing file with tool restrictions."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(SAMPLE_COMMAND)
            f.flush()

            try:
                cmd = SlashCommand._parse_file(Path(f.name))
                assert cmd.name == "test-command"
                assert cmd.description == "A test command"
                assert cmd.prompt == "This is the prompt template."
                assert cmd.tools == ["Gmail.search_emails", "WebFetch"]
            finally:
                os.unlink(f.name)

    def test_parse_file_without_tools(self):
        """Test parsing file without tool restrictions."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(SAMPLE_COMMAND_NO_TOOLS)
            f.flush()

            try:
                cmd = SlashCommand._parse_file(Path(f.name))
                assert cmd.name == "simple"
                assert cmd.tools is None  # No restrictions
            finally:
                os.unlink(f.name)

    def test_parse_file_missing_frontmatter(self):
        """Test parsing file without YAML frontmatter."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(SAMPLE_COMMAND_NO_FRONTMATTER)
            f.flush()

            try:
                with pytest.raises(ValueError) as exc_info:
                    SlashCommand._parse_file(Path(f.name))
                assert "missing YAML frontmatter" in str(exc_info.value)
            finally:
                os.unlink(f.name)

    def test_parse_file_missing_name(self):
        """Test parsing file missing required name field."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(SAMPLE_COMMAND_MISSING_NAME)
            f.flush()

            try:
                with pytest.raises(ValueError) as exc_info:
                    SlashCommand._parse_file(Path(f.name))
                assert "missing 'name' field" in str(exc_info.value)
            finally:
                os.unlink(f.name)

    def test_parse_file_malformed_frontmatter(self):
        """Test parsing file with malformed frontmatter."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(SAMPLE_COMMAND_MALFORMED)
            f.flush()

            try:
                with pytest.raises(ValueError) as exc_info:
                    SlashCommand._parse_file(Path(f.name))
                assert "malformed frontmatter" in str(exc_info.value)
            finally:
                os.unlink(f.name)


class TestFilterTools:
    """Tests for SlashCommand.filter_tools method."""

    def test_filter_tools_none_allows_all(self):
        """Test that None tools list allows all tools."""
        cmd = SlashCommand(
            name="test",
            description="Test",
            prompt="Prompt",
            tools=None
        )
        tools = ["tool1", "tool2", "tool3"]
        filtered = cmd.filter_tools(tools)
        assert filtered == tools

    def test_filter_tools_function_match(self):
        """Test filtering function-based tools by name."""
        cmd = SlashCommand(
            name="test",
            description="Test",
            prompt="Prompt",
            tools=["my_function"]
        )

        def my_function():
            pass

        def other_function():
            pass

        tools = [my_function, other_function]
        filtered = cmd.filter_tools(tools)
        assert len(filtered) == 1
        assert filtered[0] == my_function

    def test_filter_tools_class_method_match(self):
        """Test filtering class methods by Class.method format."""
        cmd = SlashCommand(
            name="test",
            description="Test",
            prompt="Prompt",
            tools=["Gmail.search_emails"]
        )

        class Gmail:
            def search_emails(self):
                pass
            def send(self):
                pass

        gmail = Gmail()
        tools = [gmail.search_emails, gmail.send]
        filtered = cmd.filter_tools(tools)
        assert len(filtered) == 1
        assert filtered[0] == gmail.search_emails

    def test_filter_tools_whole_class_match(self):
        """Test filtering allows all methods when class name is in list."""
        cmd = SlashCommand(
            name="test",
            description="Test",
            prompt="Prompt",
            tools=["Gmail"]  # Allow whole class
        )

        class Gmail:
            def search_emails(self):
                pass
            def send(self):
                pass

        gmail = Gmail()
        tools = [gmail.search_emails, gmail.send]
        filtered = cmd.filter_tools(tools)
        assert len(filtered) == 2  # Both methods allowed

    def test_filter_tools_empty_result(self):
        """Test filtering returns empty list when no matches."""
        cmd = SlashCommand(
            name="test",
            description="Test",
            prompt="Prompt",
            tools=["nonexistent"]
        )

        def my_function():
            pass

        filtered = cmd.filter_tools([my_function])
        assert filtered == []


class TestListAll:
    """Tests for SlashCommand.list_all method."""

    def test_list_all_empty(self):
        """Test list_all with no commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                commands = SlashCommand.list_all()
                assert commands == {}
            finally:
                os.chdir(original_cwd)

    def test_list_all_builtin_only(self):
        """Test list_all with built-in commands only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builtin_dir = Path(tmpdir) / "commands"
            builtin_dir.mkdir()
            (builtin_dir / "cmd1.md").write_text(SAMPLE_COMMAND)

            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                commands = SlashCommand.list_all()
                assert len(commands) == 1
                assert "test-command" in commands
            finally:
                os.chdir(original_cwd)

    def test_list_all_custom_overrides_builtin(self):
        """Test that custom commands override built-ins in list_all."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create builtin
            builtin_dir = Path(tmpdir) / "commands"
            builtin_dir.mkdir()
            (builtin_dir / "same.md").write_text(SAMPLE_COMMAND)

            # Create custom with same name
            custom_dir = Path(tmpdir) / ".co" / "commands"
            custom_dir.mkdir(parents=True)
            (custom_dir / "same.md").write_text(SAMPLE_COMMAND_NO_TOOLS)

            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                commands = SlashCommand.list_all()
                # Should have the custom version (which has name "simple")
                assert "simple" in commands
                assert commands["simple"].is_custom is True
            finally:
                os.chdir(original_cwd)


class TestIsCustom:
    """Tests for SlashCommand.is_custom static method."""

    def test_is_custom_true(self):
        """Test is_custom returns True for custom commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_dir = Path(tmpdir) / ".co" / "commands"
            custom_dir.mkdir(parents=True)
            (custom_dir / "mycmd.md").write_text(SAMPLE_COMMAND)

            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                assert SlashCommand.is_custom("mycmd") is True
            finally:
                os.chdir(original_cwd)

    def test_is_custom_false(self):
        """Test is_custom returns False for non-custom commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                assert SlashCommand.is_custom("nonexistent") is False
            finally:
                os.chdir(original_cwd)
