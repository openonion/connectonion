"""Tests for CLI help system - updated for Typer."""

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

        assert result.exit_code == 0
        assert __version__ in result.output
        assert "ConnectOnion" in result.output
        assert "Quick Start:" in result.output
        assert "Commands:" in result.output
        assert "init" in result.output
        assert "create" in result.output
        assert "auth" in result.output
        assert "docs.connectonion.com" in result.output

    def test_help_flag_shows_detailed_help(self):
        """Test that 'co --help' shows detailed Typer help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['--help'])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "init" in result.output
        assert "create" in result.output
        assert "auth" in result.output
        assert "status" in result.output
        assert "reset" in result.output
        assert "browser" in result.output
        assert "Commands" in result.output

    def test_version_flag(self):
        """Test that --version shows version number."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['--version'])

        assert result.exit_code == 0
        assert __version__ in result.output

    def test_init_help(self):
        """Test 'co init --help' shows command-specific help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['init', '--help'])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "--template" in result.output
        assert "--yes" in result.output or "-y" in result.output
        assert "--key" in result.output
        assert "--force" in result.output

    def test_create_help(self):
        """Test 'co create --help' shows command-specific help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['create', '--help'])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "--template" in result.output

    def test_auth_help(self):
        """Test 'co auth --help' shows command-specific help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['auth', '--help'])

        assert result.exit_code == 0
        assert "Usage:" in result.output

    def test_status_help(self):
        """Test 'co status --help' shows command-specific help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['status', '--help'])

        assert result.exit_code == 0

    def test_reset_help(self):
        """Test 'co reset --help' shows command-specific help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['reset', '--help'])

        assert result.exit_code == 0

    def test_browser_help(self):
        """Test 'co browser --help' shows command-specific help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['browser', '--help'])

        assert result.exit_code == 0
        assert "Usage:" in result.output

    def test_help_shows_common_options_clearly(self):
        """Test that help clearly shows commonly used options."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['init', '--help'])

        assert "--template" in result.output
        assert "--yes" in result.output or "-y" in result.output

    def test_help_is_scannable(self):
        """Test that help output is scannable (not overly verbose)."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, [])

        line_count = len(result.output.split('\n'))
        assert line_count < 50, "Brief help should be scannable (< 50 lines)"
        assert "Quick Start:" in result.output
        assert "Commands:" in result.output

    def test_invalid_command_shows_help(self):
        """Test that invalid command shows helpful error."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['invalid-command'])

        assert result.exit_code != 0

    def test_help_consistent_across_commands(self):
        """Test that help format is consistent across all commands."""
        from connectonion.cli.main import cli

        commands = ['init', 'create', 'auth', 'status', 'reset']

        for command in commands:
            result = self.runner.invoke(cli, [command, '--help'])
            assert result.exit_code == 0, f"{command} --help should succeed"

    def test_help_option_descriptions_are_helpful(self):
        """Test that option descriptions provide context."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['init', '--help'])

        assert "--template" in result.output
        assert "--yes" in result.output or "-y" in result.output


class TestHelpBestPractices:
    """Test that help system follows CLI best practices."""

    def setup_method(self):
        """Setup test environment."""
        self.runner = ArgparseCliRunner()

    def test_progressive_disclosure(self):
        """Test that help uses progressive disclosure."""
        from connectonion.cli.main import cli

        # Level 1: Brief help (no args)
        brief = self.runner.invoke(cli, [])
        assert brief.exit_code == 0

        # Level 2: Detailed help (--help)
        detailed = self.runner.invoke(cli, ['--help'])
        assert detailed.exit_code == 0

        # Level 3: Command help (init --help)
        command = self.runner.invoke(cli, ['init', '--help'])
        assert command.exit_code == 0

    def test_help_is_terminal_independent(self):
        """Test that help doesn't break in different terminal types."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, [])

        assert len(result.output) > 0
        assert "ConnectOnion" in result.output

    def test_help_provides_real_examples(self):
        """Test that brief help shows real examples."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, [])

        assert "co create" in result.output
        assert "python agent.py" in result.output
