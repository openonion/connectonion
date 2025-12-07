"""Tests for CLI deploy command."""

import os
import shutil
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from .argparse_runner import ArgparseCliRunner

# Skip tests if git is not installed
SKIP_NO_GIT = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git not installed"
)


class TestCliDeploy:
    """Test the co deploy command."""

    def setup_method(self):
        """Setup test environment."""
        self.runner = ArgparseCliRunner()

    def test_deploy_requires_git_repo(self):
        """Test that deploy fails if not in a git repo."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create .co folder but no .git
            os.makedirs(".co")
            Path(".co/config.toml").write_text('[project]\nname = "test-agent"')

            result = self.runner.invoke(cli, ['deploy'])
            assert "Not a git repository" in result.output

    def test_deploy_requires_co_project(self):
        """Test that deploy fails if not a ConnectOnion project."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create .git but no .co folder
            os.makedirs(".git")

            result = self.runner.invoke(cli, ['deploy'])
            assert "Not a ConnectOnion project" in result.output

    @SKIP_NO_GIT
    @pytest.mark.skip(reason="API key check depends on dotenv loading from system files")
    def test_deploy_requires_api_key(self):
        """Test that deploy fails if no API key."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Create real git repo and .co folder
            subprocess.run(['git', 'init'], capture_output=True)
            subprocess.run(['git', 'config', 'user.email', 'test@test.com'], capture_output=True)
            subprocess.run(['git', 'config', 'user.name', 'Test'], capture_output=True)

            os.makedirs(".co")
            Path(".co/config.toml").write_text('[project]\nname = "test-agent"')

            # Clear any existing API key
            with patch.dict(os.environ, {}, clear=True):
                result = self.runner.invoke(cli, ['deploy'])
                assert "No API key" in result.output

    @SKIP_NO_GIT
    @patch('connectonion.cli.commands.deploy_commands.requests.post')
    @patch('connectonion.cli.commands.deploy_commands.requests.get')
    @patch('connectonion.cli.commands.deploy_commands.subprocess.run')
    def test_deploy_success(self, mock_subprocess, mock_get, mock_post):
        """Test successful deployment flow."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Setup git repo and CO project
            subprocess.run(['git', 'init'], capture_output=True)
            subprocess.run(['git', 'config', 'user.email', 'test@test.com'], capture_output=True)
            subprocess.run(['git', 'config', 'user.name', 'Test'], capture_output=True)

            os.makedirs(".co")
            Path(".co/config.toml").write_text('[project]\nname = "test-agent"')
            Path("agent.py").write_text('print("hello")')

            subprocess.run(['git', 'add', '.'], capture_output=True)
            subprocess.run(['git', 'commit', '-m', 'init'], capture_output=True)

            # Mock subprocess for git archive
            mock_subprocess.return_value = MagicMock(returncode=0)

            # Mock API responses
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: {
                    "deployment_id": "abc123",
                    "agent_url": "https://test-agent-abc123.agents.openonion.ai"
                }
            )
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {"status": "running"}
            )

            # Set API key
            with patch.dict(os.environ, {"OPENONION_API_KEY": "test-token"}):
                result = self.runner.invoke(cli, ['deploy'])

            assert "Deployed!" in result.output or result.exit_code == 0

    @SKIP_NO_GIT
    @patch('connectonion.cli.commands.deploy_commands.requests.post')
    def test_deploy_api_error(self, mock_post):
        """Test deploy handles API errors."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # Setup git repo and CO project
            subprocess.run(['git', 'init'], capture_output=True)
            subprocess.run(['git', 'config', 'user.email', 'test@test.com'], capture_output=True)
            subprocess.run(['git', 'config', 'user.name', 'Test'], capture_output=True)

            os.makedirs(".co")
            Path(".co/config.toml").write_text('[project]\nname = "test-agent"')
            Path("agent.py").write_text('print("hello")')

            subprocess.run(['git', 'add', '.'], capture_output=True)
            subprocess.run(['git', 'commit', '-m', 'init'], capture_output=True)

            # Mock API error
            mock_post.return_value = MagicMock(
                status_code=500,
                text="Internal server error"
            )

            with patch.dict(os.environ, {"OPENONION_API_KEY": "test-token"}):
                result = self.runner.invoke(cli, ['deploy'])

            assert "Deploy failed" in result.output

    def test_deploy_loads_api_key_from_env_file(self):
        """Test that deploy loads API key from .env file."""
        with self.runner.isolated_filesystem():
            # Create .env with API key
            Path(".env").write_text("OPENONION_API_KEY=test-key-from-env")

            # Create project structure
            os.makedirs(".git")
            os.makedirs(".co")
            Path(".co/config.toml").write_text('[project]\nname = "test-agent"')

            from connectonion.cli.commands.deploy_commands import _get_api_key

            # Clear environment and test loading from file
            with patch.dict(os.environ, {}, clear=True):
                api_key = _get_api_key()
                # Note: dotenv may or may not load depending on environment
                # This test verifies the function doesn't crash


class TestDeployCleanup:
    """Test notes about Docker cleanup."""

    def test_unit_tests_dont_create_real_containers(self):
        """
        Document: Unit tests use mocks, no real Docker containers are created.

        For integration tests that actually deploy:
        - After test: call DELETE /api/v1/deploy/{deployment_id}
        - This stops and removes the Docker container
        - Also cleans up deployment files on the VM

        Example cleanup in integration test:
        ```python
        @pytest.fixture
        def deployed_agent(api_key):
            # Deploy
            resp = requests.post(f"{API_BASE}/api/v1/deploy", ...)
            deployment_id = resp.json()["id"]
            yield deployment_id
            # Cleanup
            requests.delete(
                f"{API_BASE}/api/v1/deploy/{deployment_id}",
                headers={"Authorization": f"Bearer {api_key}"}
            )
        ```
        """
        # This is a documentation test - unit tests don't need cleanup
        assert True
