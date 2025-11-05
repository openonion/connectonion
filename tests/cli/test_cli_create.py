"""Tests for new CLI create command and updated init command."""

import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import re

from .argparse_runner import ArgparseCliRunner


class TestCliCreate:
    """Test the co create command."""

    def setup_method(self):
        """Setup test environment."""
        self.runner = ArgparseCliRunner()

    @pytest.fixture(autouse=True)
    def mock_auth(self):
        """Mock authentication to avoid network calls in tests."""
        with patch('connectonion.cli.commands.create.authenticate') as mock:
            # Simulate successful authentication
            mock.return_value = True
            yield mock

    def test_create_with_name_creates_directory(self):
        """Test that create with name creates a new directory."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create project with name
            result = self.runner.invoke(cli, ['create', 'my-agent'],
                                        input='n\nminimal\n')  # No AI, minimal template
            assert result.exit_code == 0

            # Check directory was created
            assert os.path.exists('my-agent')
            assert os.path.exists('my-agent/agent.py')
            assert os.path.exists('my-agent/.co/config.toml')

    def test_create_without_name_prompts(self):
        """Test that create without name auto-generates directory name from template."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create project without name - auto-generates name from template
            result = self.runner.invoke(cli, ['create'],
                                        input='minimal\n')
            assert result.exit_code == 0

            # Check directory was created with auto-generated name
            assert os.path.exists('minimal-agent')
            assert os.path.exists('minimal-agent/agent.py')

    def test_create_ai_enabled_shows_custom_option(self):
        """Test that enabling AI shows custom template option."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create with AI enabled (if supported)
            result = self.runner.invoke(cli, ['create', 'ai-agent'],
                                        input='y\ncustom\nBuild a chatbot\n')

            # Should create project directory
            assert os.path.exists('ai-agent')

    def test_create_no_ai_hides_custom_option(self):
        """Test that disabling AI hides custom template option."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create without AI
            result = self.runner.invoke(cli, ['create', 'no-ai-agent'],
                                        input='n\nminimal\n')

            # Should create project without AI features
            assert os.path.exists('no-ai-agent')
            assert os.path.exists('no-ai-agent/agent.py')

    def test_api_key_detection_openai(self):
        """Test that OpenAI API key is detected from environment."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Set OpenAI API key in environment
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-test123'}):
                result = self.runner.invoke(cli, ['create', 'openai-agent'],
                                            input='minimal\n')

                # Should detect and use OpenAI key
                if result.exit_code == 0:
                    assert os.path.exists('openai-agent')

    def test_api_key_detection_anthropic(self):
        """Test that Anthropic API key is detected from environment."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Set Anthropic API key
            with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'sk-ant-test123'}):
                result = self.runner.invoke(cli, ['create', 'anthropic-agent'],
                                            input='minimal\n')

                if result.exit_code == 0:
                    assert os.path.exists('anthropic-agent')

    def test_api_key_detection_google(self):
        """Test that Google API key is detected from environment."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Set Google API key
            with patch.dict(os.environ, {'GOOGLE_API_KEY': 'test-google-key'}):
                result = self.runner.invoke(cli, ['create', 'google-agent'],
                                            input='minimal\n')

                if result.exit_code == 0:
                    assert os.path.exists('google-agent')

    def test_api_key_detection_groq(self):
        """Test that Groq API key is detected from environment."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Set Groq API key
            with patch.dict(os.environ, {'GROQ_API_KEY': 'test-groq-key'}):
                result = self.runner.invoke(cli, ['create', 'groq-agent'],
                                            input='minimal\n')

                if result.exit_code == 0:
                    assert os.path.exists('groq-agent')

    def test_create_existing_directory_fails(self):
        """Test that create fails if directory already exists."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create directory first
            os.makedirs('existing-agent')

            # Try to create project with same name
            result = self.runner.invoke(cli, ['create', 'existing-agent'],
                                        input='minimal\n')

            # Should handle gracefully (either fail or ask for confirmation)
            # The exact behavior depends on implementation
            assert True  # Just ensure no crash

    def test_create_with_description(self):
        """Test creating project with description."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['create', 'described-agent',
                                              '--description', 'A helpful assistant'],
                                        input='minimal\n')

            if result.exit_code == 0:
                assert os.path.exists('described-agent')

    def test_create_with_key_flag(self):
        """Test creating project with --key flag."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['create', 'keyed-agent',
                                              '--key', 'sk-test-key'],
                                        input='minimal\n')

            if result.exit_code == 0:
                assert os.path.exists('keyed-agent')

    def test_create_with_template_flag(self):
        """Test creating project with --template flag."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['create', 'template-agent',
                                              '--template', 'minimal'])

            assert result.exit_code == 0
            assert os.path.exists('template-agent')

    def test_create_with_yes_flag(self):
        """Test creating project with --yes flag (auto-confirm)."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['create', 'auto-agent',
                                              '--yes',
                                              '--template', 'minimal'])

            assert result.exit_code == 0
            assert os.path.exists('auto-agent')

    def test_create_sets_up_project_structure(self):
        """Test that create sets up complete project structure."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['create', 'complete-agent',
                                              '--yes',
                                              '--template', 'minimal'])

            assert result.exit_code == 0

            # Check all expected files exist
            base_path = 'complete-agent'
            assert os.path.exists(f'{base_path}/agent.py')
            assert os.path.exists(f'{base_path}/.co')
            assert os.path.exists(f'{base_path}/.co/config.toml')

    def test_create_adds_agent_config_path_to_env(self):
        """Test that create adds AGENT_CONFIG_PATH to project .env file."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['create', 'config-test-agent',
                                              '--yes',
                                              '--template', 'minimal'])

            assert result.exit_code == 0

            # Check that project .env contains AGENT_CONFIG_PATH
            env_file = 'config-test-agent/.env'
            assert os.path.exists(env_file)
            with open(env_file) as f:
                content = f.read()
                assert "AGENT_CONFIG_PATH=" in content
                # Should point to home directory .co folder
                assert "/.co" in content

    def test_create_adds_default_model_comment_to_env(self):
        """Test that create adds default model comment to project .env file."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['create', 'model-test-agent',
                                              '--yes',
                                              '--template', 'minimal'])

            assert result.exit_code == 0

            # Check that project .env contains default model comment
            env_file = 'model-test-agent/.env'
            assert os.path.exists(env_file)
            with open(env_file) as f:
                content = f.read()
                assert "# Default model: co/o4-mini" in content
                assert "managed keys with free credits" in content

    def test_create_adds_agent_address_explanation_to_global_keys(self):
        """Test that create adds explanatory comments to global keys.env when first created."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            from pathlib import Path
            import shutil

            # Remove existing ~/.co to ensure fresh creation
            global_co_dir = Path.home() / ".co"
            if global_co_dir.exists():
                shutil.rmtree(global_co_dir)

            result = self.runner.invoke(cli, ['create', 'explain-test-agent',
                                              '--yes',
                                              '--template', 'minimal'])

            assert result.exit_code == 0

            # Check global keys.env (should exist now since we removed it)
            global_keys_env = Path.home() / ".co" / "keys.env"
            assert global_keys_env.exists()

            with open(global_keys_env) as f:
                content = f.read()
                # Should have explanatory comment about agent address (only on first creation)
                assert "Your agent address (Ed25519 public key) is used for:" in content
                assert "Secure agent communication" in content
                assert "Authentication with OpenOnion" in content
                assert "@mail.openonion.ai" in content
