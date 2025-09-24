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
        assert os.path.exists(os.path.join(temp_dir, ".env"))
        assert os.path.exists(os.path.join(temp_dir, ".co"))
        assert os.path.isdir(os.path.join(temp_dir, ".co"))
        
        # Config and docs directory
        assert os.path.exists(os.path.join(temp_dir, ".co", "config.toml"))
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
        """Test that .env has correct content."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'])
        
        assert result.exit_code == 0
        
        # Check .env content
        env_file = os.path.join(temp_dir, ".env")
        with open(env_file, "r") as f:
            content = f.read()
        
        # Should include commented API key placeholders, not fake values
        assert "# OPENAI_API_KEY=" in content
        assert "# Optional: Override default model" in content
    
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
        assert os.path.exists(os.path.join(temp_dir, ".env"))
        
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
    
    def test_init_invalid_template_fails(self):
        """Test that invalid template name fails gracefully."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init', '--template', 'invalid'])
        
        # Should fail with an error
        assert result.exit_code != 0
    
    def test_init_template_playwright(self):
        """Test --template playwright creates browser automation agent."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init', '--template', 'playwright'])
        
        assert result.exit_code == 0
        
        # Check agent.py has playwright content
        agent_file = os.path.join(temp_dir, "agent.py")
        with open(agent_file, "r") as f:
            content = f.read()
        
        # Should have browser automation elements
        assert "playwright" in content.lower() or "browser" in content.lower()
        # Playwright template has single prompt.md file
        assert os.path.exists(os.path.join(temp_dir, "prompt.md"))
        assert not os.path.exists(os.path.join(temp_dir, "prompts"))
    
    @pytest.mark.skip(reason="meta-agent template is not exposed by current CLI")
    def test_init_template_meta_agent(self):
        pass
    
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
        
        # Check .co/config.yaml exists (note: might be config.toml now)
        config_file = os.path.join(temp_dir, ".co", "config.yaml")
        if not os.path.exists(config_file):
            config_file = os.path.join(temp_dir, ".co", "config.toml")
        assert os.path.exists(config_file)
        
        # Check config content
        if config_file.endswith('.yaml'):
            with open(config_file, "r") as f:
                config = yaml.safe_load(f)
        else:
            import toml
            with open(config_file, "r") as f:
                config = toml.load(f)
        
        assert "version" in config or "project" in config
        assert config.get("version") is not None or config.get("project", {}).get("framework_version") is not None
    
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
        assert ".env" in result.output
    
    def test_init_shows_address_but_not_private_material(self):
        """Init shows address/email but not private key material."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'])
        
        assert result.exit_code == 0
        
        # Shows agent address (full) and next steps
        assert "Agent address:" in result.output
        assert result.output.count("0x") >= 1
        assert "recovery" not in result.output.lower()
        assert "seed" not in result.output.lower()
        assert "phrase" not in result.output.lower()
        
        # Should only show simple success message
        assert "✅" in result.output or "Initialized" in result.output
        assert "Next steps:" in result.output
    
    def test_keys_saved_in_co_directory(self):
        """Test that keys are saved in .co/keys/ directory."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'])
        
        assert result.exit_code == 0
        
        # Check .co/keys directory exists
        co_keys_dir = os.path.join(temp_dir, ".co", "keys")
        assert os.path.exists(co_keys_dir)
        assert os.path.isdir(co_keys_dir)
        
        # Check key files exist
        assert os.path.exists(os.path.join(co_keys_dir, "agent.key"))
        assert os.path.exists(os.path.join(co_keys_dir, "recovery.txt"))
    
    def test_address_saved_in_config_toml(self):
        """Test that agent address is saved in config.toml."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'])
        
        assert result.exit_code == 0
        
        # Load config.toml
        config_file = os.path.join(temp_dir, ".co", "config.toml")
        assert os.path.exists(config_file)
        
        import toml
        with open(config_file, "r") as f:
            config = toml.load(f)
        
        # Check agent section exists
        assert "agent" in config
        assert "address" in config["agent"]
        
        # Check address format (0x + 64 hex chars)
        address = config["agent"]["address"]
        assert address.startswith("0x")
        assert len(address) == 66
        
        # Check it's valid hex
        hex_part = address[2:]
        assert all(c in '0123456789abcdef' for c in hex_part.lower())
    
    def test_short_address_in_config(self):
        """Test that short address (0x3d40...660c format) is saved."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'])
        
        assert result.exit_code == 0
        
        # Load config.toml
        config_file = os.path.join(temp_dir, ".co", "config.toml")
        import toml
        with open(config_file, "r") as f:
            config = toml.load(f)
        
        # Check short_address exists
        assert "short_address" in config["agent"]
        
        short = config["agent"]["short_address"]
        # Should be format: 0x1234...5678
        assert short.startswith("0x")
        assert "..." in short
        assert len(short) == 13
        
        # Should match full address
        full = config["agent"]["address"]
        assert short[:6] == full[:6]  # First part matches
        assert short[-4:] == full[-4:]  # Last part matches
    
    def test_recovery_phrase_saved_locally(self):
        """Test that recovery phrase is saved for pragmatic recovery."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'])
        
        assert result.exit_code == 0
        
        # Read recovery phrase
        recovery_path = os.path.join(temp_dir, ".co", "keys", "recovery.txt")
        assert os.path.exists(recovery_path)
        
        with open(recovery_path, "r") as f:
            seed_phrase = f.read().strip()
        
        # Check it's 12 words
        words = seed_phrase.split()
        assert len(words) == 12
        
        # Check each word is lowercase and non-empty
        for word in words:
            assert word == word.lower()
            assert len(word) > 0
    
    def test_gitignore_includes_keys_directory(self):
        """Test that .gitignore includes .co/keys/ to protect private keys."""
        temp_dir = self.create_temp_dir(empty=True)
        
        # Create .git directory to simulate git repo
        git_dir = os.path.join(temp_dir, ".git")
        os.makedirs(git_dir)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'])
        
        assert result.exit_code == 0
        
        # Check .gitignore exists and contains keys directory
        gitignore_file = os.path.join(temp_dir, ".gitignore")
        assert os.path.exists(gitignore_file)
        
        with open(gitignore_file, "r") as f:
            gitignore_content = f.read()
        
        assert ".co/keys/" in gitignore_content
        assert ".env" in gitignore_content
    
    def test_warning_file_in_keys_directory(self):
        """Test that a warning file is created in keys directory."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'])
        
        assert result.exit_code == 0
        
        # Check for warning file
        warning_path = os.path.join(temp_dir, ".co", "keys", "DO_NOT_SHARE")
        assert os.path.exists(warning_path)
        
        # Check content warns about private keys
        with open(warning_path, "r") as f:
            content = f.read()
        
        assert "private" in content.lower() or "secret" in content.lower()
        assert "never" in content.lower() or "do not" in content.lower()
    
    def test_existing_keys_not_regenerated(self):
        """Test that existing keys are preserved on subsequent inits."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            
            # First init
            result1 = self.runner.invoke(cli, ['init'])
            assert result1.exit_code == 0
            
            # Read the generated address
            config_file = os.path.join(temp_dir, ".co", "config.toml")
            import toml
            with open(config_file, "r") as f:
                config1 = toml.load(f)
            address1 = config1["agent"]["address"]
            
            # Read recovery phrase
            recovery_path = os.path.join(temp_dir, ".co", "keys", "recovery.txt")
            with open(recovery_path, "r") as f:
                phrase1 = f.read()
            
            # Second init with --force
            result2 = self.runner.invoke(cli, ['init', '--force'])
            assert result2.exit_code == 0
            
            # Check address hasn't changed
            with open(config_file, "r") as f:
                config2 = toml.load(f)
            address2 = config2["agent"]["address"]
            
            # Check recovery phrase hasn't changed
            with open(recovery_path, "r") as f:
                phrase2 = f.read()
            
            assert address1 == address2
            assert phrase1 == phrase2
    
    def test_algorithm_field_in_config(self):
        """Test that algorithm field is set to ed25519 in config."""
        temp_dir = self.create_temp_dir(empty=True)
        
        with patch('os.getcwd', return_value=temp_dir):
            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['init'])
        
        assert result.exit_code == 0
        
        # Check config
        config_file = os.path.join(temp_dir, ".co", "config.toml")
        import toml
        with open(config_file, "r") as f:
            config = toml.load(f)
        
        assert "algorithm" in config["agent"]
        assert config["agent"]["algorithm"] == "ed25519"


# Test fixtures and helpers would go in separate files
# This gives us comprehensive test coverage before implementing
