"""Simplified tests for CLI init command - focusing on core behavior."""

import os
import tempfile
import shutil
from pathlib import Path
from click.testing import CliRunner
import pytest


class TestCliInit:
    """Test the co init command."""
    
    def setup_method(self):
        """Setup test environment."""
        self.runner = CliRunner()
        
    def test_init_creates_working_agent(self):
        """Test that init creates a working agent setup."""
        with self.runner.isolated_filesystem():
            # Import here to avoid issues before installation
            from connectonion.cli.main import cli
            
            # Run init
            result = self.runner.invoke(cli, ['init'])
            assert result.exit_code == 0
            
            # Check core files exist
            assert os.path.exists('agent.py')
            assert os.path.exists('prompt.md')  # System prompt in markdown
            assert os.path.exists('.env.example')
            assert os.path.exists('.co/config.toml')
            assert os.path.exists('.co/docs/connectonion.md')  # Embedded documentation
            
            # Verify agent.py is valid Python
            with open('agent.py') as f:
                code = f.read()
                compile(code, 'agent.py', 'exec')
            
            # Check agent.py references prompt.md
            assert 'from connectonion import Agent' in code
            assert 'system_prompt="prompt.md"' in code
            
            # Check prompt.md has content
            with open('prompt.md') as f:
                prompt = f.read()
                assert '# Assistant' in prompt or '# ' in prompt
                assert len(prompt) > 50  # Should have meaningful content
            
            # Check ConnectOnion docs are embedded
            with open('.co/docs/connectonion.md') as f:
                docs = f.read()
                assert '# ConnectOnion' in docs
                assert 'from connectonion import Agent' in docs
                assert len(docs) > 500  # Should have substantial documentation
            
            # Check config.toml has correct structure
            import toml
            with open('.co/config.toml') as f:
                config = toml.load(f)
                assert 'project' in config
                assert 'cli' in config
                assert config['cli']['template'] in ['meta-agent', 'playwright']
    
    def test_init_templates(self):
        """Test that different templates create appropriate agents."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            
            # Test chat template
            result = self.runner.invoke(cli, ['init', '--template', 'invalid'])
            assert result.exit_code == 0
            
            with open('agent.py') as f:
                content = f.read()
            
            # Chat template should have conversation-related content
            assert 'chat' in content.lower() or 'conversation' in content.lower()
            
            # Check prompt.md has chat-specific content
            with open('prompt.md') as f:
                prompt = f.read()
                assert 'Chat Assistant' in prompt or 'conversation' in prompt.lower()
    
    def test_init_in_non_empty_directory(self):
        """Test that init asks for confirmation in non-empty directories."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            
            # Create existing file
            Path('existing.txt').write_text('existing content')
            
            # Should ask for confirmation and abort when user says no
            result = self.runner.invoke(cli, ['init'], input='n\n')
            assert result.exit_code == 0
            assert not os.path.exists('agent.py')
            
            # Should proceed when user confirms
            result = self.runner.invoke(cli, ['init'], input='y\n')
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
                assert f.read() == '# My custom agent'
    
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
        assert '0.0.1' in result.stdout