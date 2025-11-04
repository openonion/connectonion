"""Simplified tests for CLI init command - focusing on core behavior."""

import os
import tempfile
import shutil
from pathlib import Path
import pytest

from .argparse_runner import ArgparseCliRunner


class TestCliInit:
    """Test the co init command."""

    def setup_method(self):
        """Setup test environment."""
        self.runner = ArgparseCliRunner()

    def test_init_creates_working_agent(self):
        """Test that init creates a working agent setup."""
        with self.runner.isolated_filesystem():
            # Import here to avoid issues before installation
            from connectonion.cli.main import cli

            # Run init with template to create agent.py
            result = self.runner.invoke(cli, ['init', '--template', 'minimal'])
            assert result.exit_code == 0

            # Check core files exist
            assert os.path.exists('agent.py')
            assert os.path.exists('.env')  # CLI creates .env, not .env.example
            assert os.path.exists('.co/config.toml')

            # Verify agent.py is valid Python
            with open('agent.py') as f:
                code = f.read()
                compile(code, 'agent.py', 'exec')

            # Check agent.py references ConnectOnion
            assert 'from connectonion import Agent' in code

            # Check config.toml has correct structure
            import toml
            with open('.co/config.toml') as f:
                config = toml.load(f)
                assert 'project' in config
                assert 'cli' in config

    def test_init_templates(self):
        """Test that different templates create appropriate agents."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Test with a template
            result = self.runner.invoke(cli, ['init', '--template', 'minimal'])
            assert result.exit_code == 0

            with open('agent.py') as f:
                content = f.read()

            # Should have basic agent structure
            assert 'from connectonion import Agent' in content

    def test_init_in_non_empty_directory(self):
        """Test that init asks for confirmation in non-empty directories."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create existing file
            Path('existing.txt').write_text('existing content')

            # Should ask for confirmation and abort when user says no
            result = self.runner.invoke(cli, ['init'], input='n\n')
            # Check that agent.py was NOT created
            if result.exit_code == 0:
                # If exit code is 0, user declined, so no agent.py
                assert not os.path.exists('agent.py') or result.exit_code != 0

            # Should proceed when user confirms
            result = self.runner.invoke(cli, ['init', '--template', 'minimal'], input='y\n')
            assert result.exit_code == 0
            assert os.path.exists('agent.py')
            assert os.path.exists('existing.txt')  # Preserves existing files

    def test_init_never_overwrites(self):
        """Test that init never overwrites existing agent.py."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create existing agent.py
            Path('agent.py').write_text('# My custom agent')

            # Run init
            result = self.runner.invoke(cli, ['init'], input='y\n')

            # Should not overwrite
            with open('agent.py') as f:
                content = f.read()
                assert content == '# My custom agent'

    def test_init_with_git(self):
        """Test that init handles git repos properly."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create .git directory
            os.makedirs('.git')

            # Run init (will need confirmation since .git makes it non-empty)
            result = self.runner.invoke(cli, ['init'], input='y\n')
            assert result.exit_code == 0

            # Should create .gitignore
            assert os.path.exists('.gitignore')
            with open('.gitignore') as f:
                content = f.read()
                assert '.env' in content
                assert '__pycache__' in content


@pytest.mark.skipif(
    shutil.which('co') is None,
    reason="CLI not installed"
)
class TestCliCommands:
    """Test actual CLI commands (requires installation)."""

    def test_co_command_works(self):
        """Test that 'co' command is available after installation."""
        import subprocess
        result = subprocess.run(['co', '--version'], capture_output=True, text=True)
        assert result.returncode == 0
        # Check for version in output (not specific version number)
        assert any(c.isdigit() for c in result.stdout)
