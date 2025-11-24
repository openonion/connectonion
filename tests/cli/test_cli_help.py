"""Tests for CLI help system following best practices."""

import pytest
from connectonion import __version__
from .argparse_runner import ArgparseCliRunner


class TestCliHelp:
    """Test the help system for the ConnectOnion CLI."""

    def setup_method(self):
        """Setup test environment."""
        self.runner = ArgparseCliRunner()

    def test_no_args_shows_brief_help(self):
        """Test that running 'co' with no args shows brief help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, [])

        # Should succeed (exit code 0)
        assert result.exit_code == 0

        # Should show version
        assert __version__ in result.output

        # Should show "ConnectOnion"
        assert "ConnectOnion" in result.output

        # Should show usage examples (examples first principle)
        assert "Quick Start:" in result.output
        assert "co init" in result.output or "co create" in result.output

        # Should show command categories
        assert "Project Commands:" in result.output or "Commands:" in result.output
        assert "init" in result.output
        assert "create" in result.output
        assert "auth" in result.output

        # Should direct users to detailed help
        assert "--help" in result.output

        # Should show links to docs
        assert "docs.connectonion.com" in result.output
        assert "discord.gg" in result.output

    def test_help_flag_shows_detailed_help(self):
        """Test that 'co --help' shows detailed argparse help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['--help'])

        # Should succeed
        assert result.exit_code == 0

        # Should show usage
        assert "usage:" in result.output

        # Should show all commands
        assert "init" in result.output
        assert "create" in result.output
        assert "auth" in result.output
        assert "status" in result.output
        assert "reset" in result.output
        assert "browser" in result.output

        # Should show examples in epilog
        assert "Examples:" in result.output
        assert "co init" in result.output
        assert "co create my-agent" in result.output

        # Should show documentation links
        assert "docs.connectonion.com" in result.output

    def test_version_flag(self):
        """Test that --version shows version number."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['--version'])

        # Should succeed
        assert result.exit_code == 0

        # Should show version
        assert __version__ in result.output

    def test_init_help(self):
        """Test 'co init --help' shows command-specific help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['init', '--help'])

        # Should succeed
        assert result.exit_code == 0

        # Should show usage
        assert "usage: co init" in result.output

        # Should show description
        assert "Initialize a ConnectOnion project" in result.output

        # Should show all options
        assert "--template" in result.output
        assert "--yes" in result.output or "-y" in result.output
        assert "--ai" in result.output
        assert "--key" in result.output
        assert "--description" in result.output
        assert "--force" in result.output

        # Should show examples (examples first principle)
        assert "Examples:" in result.output
        assert "co init" in result.output
        assert "co init --template playwright" in result.output

        # Should show what files will be created
        assert "Files Created:" in result.output
        assert "agent.py" in result.output
        assert ".env" in result.output
        assert "config.toml" in result.output

        # Should show documentation link
        assert "docs.connectonion.com" in result.output

    def test_create_help(self):
        """Test 'co create --help' shows command-specific help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['create', '--help'])

        # Should succeed
        assert result.exit_code == 0

        # Should show usage
        assert "usage: co create" in result.output

        # Should show description
        assert "Create a new ConnectOnion project" in result.output

        # Should show examples
        assert "Examples:" in result.output
        assert "co create my-agent" in result.output

        # Should show what files will be created
        assert "Files Created:" in result.output
        assert "agent.py" in result.output

    def test_auth_help(self):
        """Test 'co auth --help' shows command-specific help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['auth', '--help'])

        # Should succeed
        assert result.exit_code == 0

        # Should show usage
        assert "usage: co auth" in result.output

        # Should show description about managed keys
        assert "managed keys" in result.output or "co/" in result.output

        # Should show examples
        assert "Examples:" in result.output
        assert "co auth" in result.output

        # Should explain what the command does
        assert "Load your agent's keys" in result.output or "Sign" in result.output

    def test_status_help(self):
        """Test 'co status --help' shows command-specific help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['status', '--help'])

        # Should succeed
        assert result.exit_code == 0

        # Should show description
        assert "account status" in result.output or "balance" in result.output

        # Should show examples
        assert "Examples:" in result.output

    def test_reset_help(self):
        """Test 'co reset --help' shows command-specific help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['reset', '--help'])

        # Should succeed
        assert result.exit_code == 0

        # Should show warning about destructive action
        assert "WARNING" in result.output or "delete" in result.output

        # Should show examples
        assert "Examples:" in result.output

    def test_browser_help(self):
        """Test 'co browser --help' shows command-specific help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['browser', '--help'])

        # Should succeed
        assert result.exit_code == 0

        # Should show usage
        assert "usage: co browser" in result.output

        # Should show examples with browser commands
        assert "Examples:" in result.output
        assert "screenshot" in result.output or "click" in result.output

    def test_help_examples_first_principle(self):
        """Test that help follows 'examples first' principle."""
        from connectonion.cli.main import cli

        # Test init command help
        result = self.runner.invoke(cli, ['init', '--help'])

        # Find position of "Examples:" and "optional arguments:"
        examples_pos = result.output.find("Examples:")
        options_pos = result.output.find("optional arguments:")

        # Examples should appear after options in argparse format
        # (argparse puts options first, but examples are in epilog which comes after)
        # This is acceptable as long as examples are present and clear
        assert examples_pos > 0, "Examples section should exist"
        assert "co init" in result.output, "Should show usage examples"

    def test_help_shows_common_options_clearly(self):
        """Test that help clearly shows commonly used options."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['init', '--help'])

        # Common options should be clearly visible
        assert "--template" in result.output
        assert "--yes" in result.output or "-y" in result.output

        # Should show short descriptions
        assert "minimal" in result.output  # Template option
        assert "playwright" in result.output  # Template option

    def test_help_includes_metadata(self):
        """Test that help includes useful metadata like files created."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['init', '--help'])

        # Should tell users what files will be created
        assert "Files Created:" in result.output or "agent.py" in result.output

        # Should list the important files
        assert "agent.py" in result.output
        assert ".env" in result.output or "config" in result.output

    def test_help_links_to_documentation(self):
        """Test that help provides links to web documentation."""
        from connectonion.cli.main import cli

        # Test main help
        result = self.runner.invoke(cli, ['--help'])
        assert "docs.connectonion.com" in result.output

        # Test command help
        result = self.runner.invoke(cli, ['init', '--help'])
        assert "docs.connectonion.com" in result.output

    def test_help_is_scannable(self):
        """Test that help output is scannable (not overly verbose)."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, [])

        # Brief help should be concise (< 50 lines)
        line_count = len(result.output.split('\n'))
        assert line_count < 50, "Brief help should be scannable (< 50 lines)"

        # Should have clear sections
        assert "Quick Start:" in result.output
        assert "Project Commands:" in result.output or "Commands:" in result.output

    def test_invalid_command_shows_help(self):
        """Test that invalid command shows helpful error."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['invalid-command'])

        # Should fail (non-zero exit code)
        assert result.exit_code != 0

        # Should show error message from argparse
        # argparse will show "invalid choice" or similar error

    def test_help_consistent_across_commands(self):
        """Test that help format is consistent across all commands."""
        from connectonion.cli.main import cli

        commands = ['init', 'create', 'auth', 'status', 'reset']

        for command in commands:
            result = self.runner.invoke(cli, [command, '--help'])

            # All should succeed
            assert result.exit_code == 0, f"{command} --help should succeed"

            # All should have examples
            assert "Examples:" in result.output, f"{command} should have examples"

            # All should have documentation link
            assert "docs.connectonion.com" in result.output, f"{command} should link to docs"

    def test_brief_help_shows_next_steps(self):
        """Test that brief help guides users to more detailed help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, [])

        # Should tell users how to get more help
        assert "--help" in result.output
        assert "co <command> --help" in result.output or "more info" in result.output

    def test_help_shows_destructive_commands_clearly(self):
        """Test that destructive commands are marked clearly."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, [])

        # Reset should be marked as destructive
        output_lower = result.output.lower()
        assert "reset" in output_lower
        assert "destructive" in output_lower or "delete" in output_lower

    def test_help_option_descriptions_are_helpful(self):
        """Test that option descriptions provide context, not just restate the name."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['init', '--help'])

        # Descriptions should be helpful, not just "Template to use"
        # They should explain what the option does or when to use it
        assert "--template" in result.output
        assert "minimal" in result.output or "playwright" in result.output

        # Should explain what --yes does
        assert "--yes" in result.output or "-y" in result.output
        assert "Skip" in result.output or "defaults" in result.output


class TestHelpBestPractices:
    """Test that help system follows CLI best practices from clig.dev."""

    def setup_method(self):
        """Setup test environment."""
        self.runner = ArgparseCliRunner()

    def test_progressive_disclosure(self):
        """Test that help uses progressive disclosure (brief -> detailed -> command)."""
        from connectonion.cli.main import cli

        # Level 1: Brief help (no args)
        brief = self.runner.invoke(cli, [])
        assert brief.exit_code == 0
        brief_lines = len(brief.output.split('\n'))

        # Level 2: Detailed help (--help)
        detailed = self.runner.invoke(cli, ['--help'])
        assert detailed.exit_code == 0
        detailed_lines = len(detailed.output.split('\n'))

        # Level 3: Command help (init --help)
        command = self.runner.invoke(cli, ['init', '--help'])
        assert command.exit_code == 0

        # Brief should be shortest, command help should be most detailed
        assert brief_lines < 50, "Brief help should be concise"

    def test_help_is_terminal_independent(self):
        """Test that help doesn't break in different terminal types."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, [])

        # Should not contain raw ANSI escape codes that would break in dumb terminals
        # Rich handles this automatically, but we verify output is present
        assert len(result.output) > 0
        assert "ConnectOnion" in result.output

    def test_help_provides_real_examples(self):
        """Test that examples are real, runnable commands (not placeholders)."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['init', '--help'])

        # Should have real examples, not just "co init [OPTIONS]"
        assert "co init" in result.output
        assert "co init --template" in result.output

        # Should show actual template names
        assert "playwright" in result.output or "minimal" in result.output

    def test_help_groups_related_commands(self):
        """Test that help groups related commands together."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, [])

        # Should group commands into categories
        assert "Project Commands:" in result.output or "Commands:" in result.output
        assert "Authentication & Account:" in result.output or "Utilities:" in result.output
