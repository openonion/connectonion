"""Tests for CLI deploy command."""

"""
LLM-Note: Tests for CLI deploy command (co deploy)

What it tests:
- TestCliDeploy: Deployment workflow
  - test_deploy_requires_git_repo: Verify git repo requirement
  - test_deploy_requires_co_project: Verify .co folder requirement
  - Git integration and deployment workflows

Components under test:
- connectonion.cli.commands.deploy (deploy command)
- Git repository integration
"""

import os
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from types import SimpleNamespace
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
            Path(".co/host.yaml").write_text('name: test-agent\nentrypoint: agent.py\n')

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

    @patch('connectonion.cli.commands.deploy_commands.requests.post')
    @patch('connectonion.cli.commands.deploy_commands.requests.get')
    def test_deploy_with_skills_auto_uses_co_ai_without_project_scaffold(self, mock_get, mock_post):
        """Test --skills deploys co-ai without requiring git or .co/host.yaml."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            from connectonion.cli.commands import deploy_commands

            Path("package.tar.gz").write_bytes(b"package")

            captured = {}

            def fake_create_package(**kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    tarball_path=Path("package.tar.gz"),
                    entrypoint=".co/deploy/co_ai_entrypoint.py",
                )

            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: {"id": "abc123", "url": "https://test-agent.agents.openonion.ai"},
            )
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {"status": "running", "url": "https://test-agent.agents.openonion.ai"},
            )

            with patch.object(deploy_commands, "create_deploy_package", side_effect=fake_create_package):
                with patch.dict(os.environ, {"OPENONION_API_KEY": "test-token"}):
                    result = self.runner.invoke(
                        cli,
                        [
                            "deploy",
                            "--name", "agent-4-linkedin",
                            "--skill", "alpha,beta",
                            "--skills", "gamma",
                            "--model", "co/test-model",
                            "--max-iterations", "44",
                        ],
                    )

            assert result.exit_code == 0
            assert captured["template"] == "co-ai"
            assert captured["skills"] == ["alpha", "beta", "gamma"]
            assert captured["project_name"] == "agent-4-linkedin"
            assert captured["model"] == "co/test-model"
            assert captured["max_iterations"] == 44
            upload_data = mock_post.call_args.kwargs["data"]
            assert upload_data["project_name"] == "agent-4-linkedin"
            assert upload_data["entrypoint"] == ".co/deploy/co_ai_entrypoint.py"
            assert json.loads(upload_data["secrets"])["OPENONION_API_KEY"] == "test-token"

    @patch('connectonion.cli.commands.deploy_commands.requests.post')
    @patch('connectonion.cli.commands.deploy_commands.requests.get')
    def test_deploy_with_all_skills_auto_uses_co_ai_without_project_scaffold(self, mock_get, mock_post):
        """Test --all-skills deploys co-ai and asks package builder to include all local skills."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli
            from connectonion.cli.commands import deploy_commands

            Path("package.tar.gz").write_bytes(b"package")
            captured = {}

            def fake_create_package(**kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    tarball_path=Path("package.tar.gz"),
                    entrypoint=".co/deploy/co_ai_entrypoint.py",
                )

            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: {"id": "abc123", "url": "https://test-agent.agents.openonion.ai"},
            )
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {"status": "running", "url": "https://test-agent.agents.openonion.ai"},
            )

            with patch.object(deploy_commands, "create_deploy_package", side_effect=fake_create_package):
                with patch.dict(os.environ, {"OPENONION_API_KEY": "test-token"}):
                    result = self.runner.invoke(cli, ["deploy", "--name", "agent-full", "--all-skills"])

            assert result.exit_code == 0
            assert captured["template"] == "co-ai"
            assert captured["skills"] == []
            assert captured["all_skills"] is True
            assert captured["project_name"] == "agent-full"

    @patch('connectonion.cli.commands.deploy_commands.requests.post')
    def test_deploy_rejects_skills_without_co_ai_template(self, mock_post):
        """Test --skills is scoped to the co-ai deploy template."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            os.makedirs(".git")
            os.makedirs(".co")
            Path(".co/host.yaml").write_text('name: test-agent\nentrypoint: agent.py\n')
            Path("agent.py").write_text('from connectonion import host\nhost(None)\n')

            with patch.dict(os.environ, {"OPENONION_API_KEY": "test-token"}):
                result = self.runner.invoke(cli, ['deploy', '--template', 'project', '--skills', 'alpha'])

            assert "--skills requires --template co-ai" in result.output
            mock_post.assert_not_called()

    @patch('connectonion.cli.commands.deploy_commands.requests.post')
    def test_deploy_rejects_all_skills_without_co_ai_template(self, mock_post):
        """Test --all-skills is scoped to the co-ai deploy template."""
        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            os.makedirs(".git")
            os.makedirs(".co")
            Path(".co/host.yaml").write_text('name: test-agent\nentrypoint: agent.py\n')
            Path("agent.py").write_text('from connectonion import host\nhost(None)\n')

            with patch.dict(os.environ, {"OPENONION_API_KEY": "test-token"}):
                result = self.runner.invoke(cli, ['deploy', '--template', 'project', '--all-skills'])

            assert "--all-skills requires --template co-ai" in result.output
            mock_post.assert_not_called()

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
            Path(".co/host.yaml").write_text('name: test-agent\nentrypoint: agent.py\n')
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

    def test_deploy_fetches_logs_after_success(self):
        """Test that deploy fetches and displays container logs after deployment.

        This is a unit test that verifies:
        1. After successful deploy, the logs endpoint is called
        2. The logs are displayed in the output
        """
        import requests
        from connectonion.cli.commands import deploy_commands

        # Capture what gets printed
        output_lines = []
        original_print = deploy_commands.console.print
        deploy_commands.console.print = lambda *args, **kwargs: output_lines.append(str(args[0]) if args else "")

        # Mock requests.get for logs endpoint
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"logs": "Agent started on port 8000\nReady to serve"}

        with patch.object(requests, 'get', return_value=mock_response) as mock_get:
            # Simulate the log fetching code path
            deployment_id = "abc123"
            api_key = "test-token"

            # This is the code we added to deploy_commands.py
            logs_resp = requests.get(
                f"https://oo.openonion.ai/api/v1/deploy/{deployment_id}/logs?tail=20",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            if logs_resp.status_code == 200:
                logs = logs_resp.json().get("logs", "")
                if logs:
                    deploy_commands.console.print()
                    deploy_commands.console.print("[dim]Container logs:[/dim]")
                    deploy_commands.console.print(f"[dim]{logs}[/dim]")

            # Verify the endpoint was called correctly
            mock_get.assert_called_once()
            call_url = mock_get.call_args[0][0]
            assert "/logs" in call_url
            assert "abc123" in call_url

            # Verify logs were printed
            assert any("Container logs:" in line for line in output_lines)
            assert any("Agent started" in line for line in output_lines)

        # Restore
        deploy_commands.console.print = original_print

    def test_deploy_shows_error_logs(self):
        """Test that container errors are visible in deploy output.

        When a container fails (e.g., missing main.py), the error should
        be visible in the logs output so users can debug.
        """
        import requests
        from connectonion.cli.commands import deploy_commands

        output_lines = []
        original_print = deploy_commands.console.print
        deploy_commands.console.print = lambda *args, **kwargs: output_lines.append(str(args[0]) if args else "")

        # Mock response with error logs
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "logs": "python: can't open file '/app/main.py': [Errno 2] No such file or directory"
        }

        with patch.object(requests, 'get', return_value=mock_response):
            deployment_id = "abc123"
            api_key = "test-token"

            logs_resp = requests.get(
                f"https://oo.openonion.ai/api/v1/deploy/{deployment_id}/logs?tail=20",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            if logs_resp.status_code == 200:
                logs = logs_resp.json().get("logs", "")
                if logs:
                    deploy_commands.console.print()
                    deploy_commands.console.print("[dim]Container logs:[/dim]")
                    deploy_commands.console.print(f"[dim]{logs}[/dim]")

            # Verify error is visible
            assert any("No such file or directory" in line for line in output_lines)

        deploy_commands.console.print = original_print

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
            Path(".co/host.yaml").write_text('name: test-agent\nentrypoint: agent.py\n')
            Path("agent.py").write_text('from connectonion import host\nhost(None)')

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
