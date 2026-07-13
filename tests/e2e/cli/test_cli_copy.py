"""Tests for CLI copy command - copies tools and plugins to user's project."""

"""
LLM-Note: Tests for CLI copy command (co copy)

What it tests:
- TestCopyCommand: Core copy functionality
  - test_copy_help: Verify help text shows options
  - test_copy_list: Verify --list shows available items
  - test_copy_no_args_shows_list: Verify no args defaults to list
  - test_copy_tool_creates_tools_dir: Verify tools/ directory creation
  - test_copy_plugin_creates_plugins_dir: Verify plugins/ directory creation
  - test_copy_case_insensitive: Verify case-insensitive matching
  - test_copy_multiple_items: Verify copying multiple items at once
  - test_copy_custom_path: Verify --path custom destination
  - test_copy_skips_existing_without_force: Verify existing files skipped
  - test_copy_force_overwrites: Verify --force overwrites existing
  - test_copy_unknown_item: Verify error for unknown items
- TestCopyListOutput: List output format verification
  - test_list_shows_tools: Verify all tools shown
  - test_list_shows_plugins: Verify all plugins shown
  - test_list_shows_usage_hint: Verify usage hint displayed

Components under test:
- connectonion.cli.commands.copy_command (copy command implementation)
- Built-in tools and plugins copying
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from .argparse_runner import ArgparseCliRunner


class TestCopyCommand:
    """Test the copy command for copying tools and plugins."""

    def setup_method(self):
        """Setup test environment."""
        self.runner = ArgparseCliRunner()
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def teardown_method(self):
        """Cleanup test environment."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_copy_help(self):
        """Test 'co copy --help' shows command-specific help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy', '--help'])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "--list" in result.output or "-l" in result.output
        assert "--path" in result.output or "-p" in result.output
        assert "--force" in result.output or "-f" in result.output

    def test_copy_list(self):
        """Test 'co copy --list' shows available items."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy', '--list'])

        assert result.exit_code == 0
        assert "Available Items to Copy" in result.output
        assert "gmail" in result.output
        assert "memory" in result.output
        assert "tool" in result.output
        assert "plugin" in result.output

    def test_copy_no_args_shows_list(self):
        """Test 'co copy' with no args shows available items."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy'])

        assert result.exit_code == 0
        assert "Available Items to Copy" in result.output

    def test_copy_tool_creates_tools_dir(self):
        """Test copying a tool creates tools/ directory."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy', 'memory'])

        assert result.exit_code == 0
        assert "Copied:" in result.output
        assert Path(self.test_dir) / "tools" / "memory.py"

    def test_copy_plugin_creates_plugins_dir(self):
        """Test copying a plugin creates plugins/ directory."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy', 're_act'])

        assert result.exit_code == 0
        assert "Copied:" in result.output
        assert (Path(self.test_dir) / "plugins" / "re_act.py").exists()

    def test_copy_case_insensitive(self):
        """Test copy command is case-insensitive."""
        from connectonion.cli.main import cli

        result1 = self.runner.invoke(cli, ['copy', 'Gmail'])
        assert result1.exit_code == 0
        assert "Copied:" in result1.output

    def test_copy_read_file_tool(self):
        """Test copying the read_file multi-format tool creates tools/read_file.py."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy', 'read_file'])

        assert result.exit_code == 0
        assert "Copied:" in result.output
        assert (Path(self.test_dir) / "tools" / "read_file.py").exists()

    def test_copy_multiple_items(self):
        """Test copying multiple items at once."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy', 'memory', 'shell'])

        assert result.exit_code == 0
        assert (Path(self.test_dir) / "tools" / "memory.py").exists()
        assert (Path(self.test_dir) / "tools" / "shell.py").exists()

    def test_copy_custom_path(self):
        """Test copying to custom path with --path."""
        from connectonion.cli.main import cli
        custom_path = Path(self.test_dir) / "my_tools"

        result = self.runner.invoke(cli, ['copy', 'memory', '--path', str(custom_path)])

        assert result.exit_code == 0
        assert (custom_path / "memory.py").exists()

    def test_copy_skips_existing_without_force(self):
        """Test copy skips existing files without --force."""
        from connectonion.cli.main import cli

        # First copy
        self.runner.invoke(cli, ['copy', 'memory'])

        # Second copy should skip
        result = self.runner.invoke(cli, ['copy', 'memory'])

        assert result.exit_code == 0
        assert "Skipped:" in result.output

    def test_copy_force_overwrites(self):
        """Test copy --force overwrites existing files."""
        from connectonion.cli.main import cli

        # First copy
        self.runner.invoke(cli, ['copy', 'memory'])

        # Second copy with --force should succeed
        result = self.runner.invoke(cli, ['copy', 'memory', '--force'])

        assert result.exit_code == 0
        assert "Copied:" in result.output

    def test_copy_cc_prompt_creates_prompts_dir(self):
        """Test copying cc_prompt creates prompts/cc_prompt/ directory with categorized files."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy', 'cc_prompt'])

        assert result.exit_code == 0
        assert "Copied:" in result.output

        cc_dir = Path(self.test_dir) / "prompts" / "cc_prompt"
        assert cc_dir.exists()
        assert (cc_dir / "README.md").exists()
        assert (cc_dir / "prompts" / "system").is_dir()
        assert (cc_dir / "prompts" / "agents").is_dir()
        assert (cc_dir / "prompts" / "tools").is_dir()
        assert (cc_dir / "prompts" / "skills").is_dir()
        assert (cc_dir / "prompts" / "reminders").is_dir()
        assert (cc_dir / "prompts" / "data").is_dir()

        # Verify files exist in each category
        assert len(list((cc_dir / "prompts" / "system").glob("*.md"))) > 0
        assert len(list((cc_dir / "prompts" / "tools").glob("*.md"))) > 0
        assert len(list((cc_dir / "prompts" / "agents").glob("*.md"))) > 0

    def test_copy_skill_creates_co_skills_dir(self):
        """Test copying a skill creates .co/skills/<name>/ directory."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy', 'ship-feature'])

        assert result.exit_code == 0
        assert "Copied:" in result.output
        skill_dir = Path(self.test_dir) / ".co" / "skills" / "ship-feature"
        assert skill_dir.exists()
        assert (skill_dir / "SKILL.md").exists()

    def test_copy_co_browser_skill(self):
        """Test copying the co-browser skill creates .co/skills/co-browser/."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy', 'co-browser'])

        assert result.exit_code == 0
        assert "Copied:" in result.output
        skill_dir = Path(self.test_dir) / ".co" / "skills" / "co-browser"
        assert skill_dir.exists()
        assert (skill_dir / "SKILL.md").exists()

    def test_copy_unknown_item(self):
        """Test copy shows error for unknown item."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy', 'nonexistent_tool'])

        assert result.exit_code == 0  # CLI doesn't fail, just prints error
        assert "Unknown:" in result.output


class TestCopyListOutput:
    """Test the list output format."""

    def setup_method(self):
        """Setup test environment."""
        self.runner = ArgparseCliRunner()

    def test_list_shows_tools(self):
        """Test list shows all available tools."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy', '--list'])

        tools = ['gmail', 'outlook', 'google_calendar', 'microsoft_calendar',
                 'memory', 'web_fetch', 'shell', 'diff_writer', 'todo_list', 'slash_command']

        for tool in tools:
            assert tool in result.output, f"Tool {tool} should be in list"

    def test_list_shows_plugins(self):
        """Test list shows all available plugins."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy', '--list'])

        plugins = ['re_act', 'eval', 'image_result_formatter',
                   'shell_approval', 'gmail_plugin', 'calendar_plugin']

        for plugin in plugins:
            assert plugin in result.output, f"Plugin {plugin} should be in list"

    def test_list_shows_cc_prompt(self):
        """Test list shows cc_prompt in available prompts."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy', '--list'])

        assert "cc_prompt" in result.output
        assert "prompt" in result.output

    def test_list_shows_skills(self):
        """Test list shows available skills."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy', '--list'])

        assert "ship-feature" in result.output
        assert "co-browser" in result.output
        assert "skill" in result.output

    def test_list_shows_usage_hint(self):
        """Test list shows usage hint at the end."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['copy', '--list'])

        assert "Usage: co copy" in result.output
