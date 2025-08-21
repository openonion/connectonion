"""Tests for the CLI init command."""

import os
import tempfile
import pytest
import shutil
import subprocess
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner


class TestCliInit:
    """Test cases for 'co init' command."""
    
    def setup_method(self):
        """Set up test environment before each test."""
        self.runner = CliRunner()
        self.temp_dir = None
        
    def teardown_method(self):
        """Clean up after each test."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def create_temp_dir(self, empty=True):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        if not empty:
            # Add some existing files
            with open(os.path.join(self.temp_dir, "existing_file.txt"), "w") as f:
                f.write("existing content")
        return self.temp_dir
    
    def test_init_empty_directory_creates_basic_files(self):
        """Test that init in empty directory creates required files."""
        temp_dir = self.create_temp_dir(empty=True)
        
        # This will fail until we implement the CLI
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'])
        
        # Should succeed
        assert result.exit_code == 0
        
        # Check required files were created
        assert os.path.exists(os.path.join(temp_dir, "agent.py"))
        assert os.path.exists(os.path.join(temp_dir, ".env.example"))
        assert os.path.exists(os.path.join(temp_dir, ".co"))
        assert os.path.isdir(os.path.join(temp_dir, ".co"))
    
    def test_init_creates_working_agent_file(self):
        """Test that agent.py is properly formed and executable."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'])
        
        assert result.exit_code == 0
        
        # Read agent.py content
        agent_file = os.path.join(temp_dir, "agent.py")
        with open(agent_file, "r") as f:
            content = f.read()
        
        # Check it contains key components
        assert "from connectonion import Agent" in content
        assert "def " in content  # Should have at least one tool function
        assert "agent = Agent(" in content
        assert 'if __name__ == "__main__":' in content
        
        # Verify it's syntactically valid Python
        compile(content, agent_file, 'exec')
    
    def test_init_creates_proper_env_example(self):
        """Test that .env.example has correct content."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'])
        
        assert result.exit_code == 0
        
        # Check .env.example content
        env_file = os.path.join(temp_dir, ".env.example")
        with open(env_file, "r") as f:
            content = f.read()
        
        assert "OPENAI_API_KEY=" in content
        assert "your-api-key-here" in content or "your_api_key_here" in content
    
    def test_init_non_empty_directory_prompts_user(self):
        """Test that init in non-empty directory asks for confirmation."""
        temp_dir = self.create_temp_dir(empty=False)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            
            # Simulate user declining
            result = self.runner.invoke(cli, ['init'], input='n\n')
        
        # Should exit without error but not create files
        assert result.exit_code == 0
        assert not os.path.exists(os.path.join(temp_dir, "agent.py"))
        assert "Directory not empty" in result.output or "not empty" in result.output
    
    def test_init_non_empty_directory_user_confirms(self):
        """Test that init proceeds when user confirms in non-empty directory."""
        temp_dir = self.create_temp_dir(empty=False)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            
            # Simulate user confirming
            result = self.runner.invoke(cli, ['init'], input='y\n')
        
        # Should create files
        assert result.exit_code == 0
        assert os.path.exists(os.path.join(temp_dir, "agent.py"))
        assert os.path.exists(os.path.join(temp_dir, ".env.example"))
        
        # Should preserve existing files
        assert os.path.exists(os.path.join(temp_dir, "existing_file.txt"))
    
    def test_init_never_overwrites_existing_files(self):
        """Test that init never overwrites existing agent.py."""
        temp_dir = self.create_temp_dir(empty=False)
        
        # Create existing agent.py
        existing_agent = os.path.join(temp_dir, "agent.py")
        with open(existing_agent, "w") as f:
            f.write("# Existing agent code")
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'], input='y\n')
        
        # Should not overwrite
        with open(existing_agent, "r") as f:
            content = f.read()
        assert "# Existing agent code" in content
        assert "Skipped agent.py (already exists)" in result.output or "exists" in result.output
    
    def test_init_warns_home_directory(self):
        """Test that init warns when run in home directory."""
        home_dir = os.path.expanduser("~")
        
        with patch('os.getcwd', return_value=home_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'], input='n\n')
        
        # Should show warning
        assert "home directory" in result.output.lower() or "warning" in result.output.lower()
    
    def test_init_warns_root_directory(self):
        """Test that init warns when run in root directory."""
        with patch('os.getcwd', return_value='/'):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'], input='n\n')
        
        # Should show warning and require confirmation
        assert result.exit_code == 0  # User declined
        assert "root" in result.output.lower() or "system" in result.output.lower()
    
    def test_init_with_examples_flag(self):
        """Test that --with-examples creates additional files."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init', '--with-examples'])
        
        assert result.exit_code == 0
        
        # Should create basic files
        assert os.path.exists(os.path.join(temp_dir, "agent.py"))
        
        # Should create additional example files
        examples_dir = os.path.join(temp_dir, "examples")
        assert os.path.exists(examples_dir) or os.path.exists(os.path.join(temp_dir, "tools.py"))
    
    def test_init_template_chat(self):
        """Test --template chat creates chat-specific agent."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init', '--template', 'chat'])
        
        assert result.exit_code == 0
        
        # Check agent.py has chat-specific content
        agent_file = os.path.join(temp_dir, "agent.py")
        with open(agent_file, "r") as f:
            content = f.read()
        
        # Should have conversational elements
        assert "chat" in content.lower() or "conversation" in content.lower()
    
    def test_init_template_data(self):
        """Test --template data creates data analysis agent."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init', '--template', 'data'])
        
        assert result.exit_code == 0
        
        # Check agent.py has data-specific content
        agent_file = os.path.join(temp_dir, "agent.py")
        with open(agent_file, "r") as f:
            content = f.read()
        
        # Should have data analysis tools
        assert "data" in content.lower() or "analyze" in content.lower()
    
    def test_init_in_git_repo_creates_gitignore(self):
        """Test that init in git repo creates .gitignore."""
        temp_dir = self.create_temp_dir(empty=True)
        
        # Create .git directory to simulate git repo
        git_dir = os.path.join(temp_dir, ".git")
        os.makedirs(git_dir)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'], input='y\n')
        
        assert result.exit_code == 0
        
        # Should create .gitignore
        gitignore_file = os.path.join(temp_dir, ".gitignore")
        assert os.path.exists(gitignore_file)
        
        # Check .gitignore content
        with open(gitignore_file, "r") as f:
            content = f.read()
        
        assert ".env" in content
        assert "__pycache__" in content
        assert "*.py[cod]" in content
    
    def test_init_gitignore_preserves_existing(self):
        """Test that init doesn't overwrite existing .gitignore."""
        temp_dir = self.create_temp_dir(empty=False)
        
        # Create existing .gitignore
        gitignore_file = os.path.join(temp_dir, ".gitignore")
        with open(gitignore_file, "w") as f:
            f.write("# Existing gitignore\nnode_modules/\n")
        
        # Create .git directory
        git_dir = os.path.join(temp_dir, ".git")
        os.makedirs(git_dir)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'], input='y\n')
        
        assert result.exit_code == 0
        
        # Should append to existing .gitignore
        with open(gitignore_file, "r") as f:
            content = f.read()
        
        assert "# Existing gitignore" in content
        assert "node_modules/" in content
        assert "# ConnectOnion" in content  # Should be added
    
    def test_co_directory_contains_metadata(self):
        """Test that .co directory contains proper metadata."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'])
        
        assert result.exit_code == 0
        
        # Check .co/config.yaml exists
        config_file = os.path.join(temp_dir, ".co", "config.yaml")
        assert os.path.exists(config_file)
        
        # Check config content
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
        
        assert "version" in config
        assert "created" in config
        assert config["version"] is not None
    
    def test_init_handles_permission_errors(self):
        """Test graceful handling of permission errors."""
        # This test might need to be skipped on some systems
        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            temp_dir = self.create_temp_dir(empty=True)
            
            with patch('os.getcwd', return_value=temp_dir):
                from connectonion.cli.main import cli
                result = self.runner.invoke(cli, ['init'])
            
            # Should handle error gracefully
            assert result.exit_code != 0
            assert "permission" in result.output.lower() or "error" in result.output.lower()
    
    def test_command_aliases(self):
        """Test that both 'co' and 'connectonion' commands work."""
        temp_dir = self.create_temp_dir(empty=True)
        
        # Test will need to be updated when we implement actual console scripts
        # For now, just test that the CLI module can be imported
        try:
            from connectonion.cli.main import cli
            assert cli is not None
        except ImportError:
            pytest.skip("CLI module not yet implemented")
    
    def test_init_output_messages(self):
        """Test that init provides clear feedback messages."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'])
        
        assert result.exit_code == 0
        
        # Should show what was created
        assert "Created" in result.output or "Initialized" in result.output
        assert "agent.py" in result.output
        assert ".env.example" in result.output


# Test fixtures and helpers would go in separate files
# This gives us comprehensive test coverage before implementing