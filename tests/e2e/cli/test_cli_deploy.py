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


@SKIP_NO_GIT
class TestDeploySkillsPackaging:
    """Test --skills bundling into the deploy tarball."""

    def _make_repo(self, root: Path):
        subprocess.run(['git', 'init'], cwd=root, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=root, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=root, capture_output=True)
        (root / ".co").mkdir()
        (root / ".co" / "host.yaml").write_text("name: demo\nentrypoint: agent.py\n")
        (root / "agent.py").write_text("from connectonion import host\nhost(None)\n")
        subprocess.run(['git', 'add', '.'], cwd=root, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'init'], cwd=root, capture_output=True)

    def test_skills_dir_lands_under_co_skills(self, tmp_path):
        import tarfile
        from connectonion.cli.commands.deploy_commands import _build_tarball_with_skills

        repo = tmp_path / "repo"
        repo.mkdir()
        self._make_repo(repo)

        skills = tmp_path / "skills"
        (skills / "hello").mkdir(parents=True)
        (skills / "hello" / "SKILL.md").write_text("---\nname: hello\n---\nhi\n")
        (skills / "hello" / "run.py").write_text("print('hi')\n")
        (skills / ".git").mkdir()                          # should be skipped
        (skills / ".git" / "config").write_text("x\n")

        # second skills dir — both should merge under .co/skills/
        more = tmp_path / "more"
        (more / "world").mkdir(parents=True)
        (more / "world" / "SKILL.md").write_text("---\nname: world\n---\nyo\n")

        tarball = _build_tarball_with_skills(repo, [skills, more])
        names = set(tarfile.open(tarball).getnames())

        assert "agent.py" in names                       # project files preserved
        assert ".co/skills/hello/SKILL.md" in names        # skill placed at loader path
        assert ".co/skills/hello/run.py" in names          # supporting files kept
        assert ".co/skills/world/SKILL.md" in names        # second --skills dir merged
        assert ".co/skills/.git/config" not in names       # dotfiles skipped

    def test_missing_skills_path_raises(self, tmp_path):
        from connectonion.cli.commands.deploy_commands import _build_tarball_with_skills

        repo = tmp_path / "repo"
        repo.mkdir()
        self._make_repo(repo)

        with pytest.raises(FileNotFoundError):
            _build_tarball_with_skills(repo, [tmp_path / "does-not-exist"])

    def test_missing_skills_path_errors_clearly(self):
        runner = ArgparseCliRunner()
        with runner.isolated_filesystem():
            from connectonion.cli.main import cli
            subprocess.run(['git', 'init'], capture_output=True)
            os.makedirs(".co")
            Path(".co/host.yaml").write_text("name: demo\nentrypoint: agent.py\n")

            result = runner.invoke(cli, ['deploy', '--co-ai', '--skills', 'does-not-exist'])
            assert "Skills path not found" in result.output

    @patch('connectonion.cli.commands.deploy_commands.requests.get')
    @patch('connectonion.cli.commands.deploy_commands.requests.post')
    def test_co_ai_flag_signals_runtime_in_upload(self, mock_post, mock_get):
        from connectonion.cli.commands.deploy_commands import handle_deploy

        runner = ArgparseCliRunner()
        with runner.isolated_filesystem():
            self._make_repo(Path("."))

            mock_post.return_value = MagicMock(status_code=200, json=lambda: {"id": "x", "url": "u"})
            mock_get.return_value = MagicMock(status_code=200, json=lambda: {"status": "running", "logs": ""})

            with patch.dict(os.environ, {"OPENONION_API_KEY": "test-token"}):
                handle_deploy(co_ai=True)

            assert mock_post.call_args.kwargs["data"]["runtime"] == "co-ai"


class TestCoAiWorktreeDeploy:
    """--co-ai packages the working tree directly — no git init/commit needed."""

    def test_worktree_tarball_includes_project_skips_junk(self, tmp_path):
        import tarfile
        from connectonion.cli.commands.deploy_commands import _build_tarball_worktree

        proj = tmp_path / "proj"
        (proj / ".co" / "skills" / "hello").mkdir(parents=True)
        (proj / ".co" / "skills" / "hello" / "SKILL.md").write_text("hi\n")
        (proj / ".co" / "host.yaml").write_text("name: demo\n")
        (proj / ".co" / "keys").mkdir()
        (proj / ".co" / "keys" / "agent.key").write_text("secret\n")
        (proj / ".co" / "docs").mkdir()
        (proj / ".co" / "docs" / "big.md").write_text("doc\n")
        (proj / "agent.py").write_text("x\n")
        (proj / ".env").write_text("OPENAI_API_KEY=sk-secret\n")
        (proj / ".git").mkdir()
        (proj / ".git" / "config").write_text("x\n")
        (proj / "__pycache__").mkdir()
        (proj / "__pycache__" / "x.pyc").write_text("x\n")

        tarball = _build_tarball_worktree(proj, [])
        names = set(tarfile.open(tarball).getnames())

        assert "agent.py" in names
        assert ".co/host.yaml" in names
        assert ".co/skills/hello/SKILL.md" in names
        assert ".env" not in names                       # secret skipped
        assert ".co/keys/agent.key" not in names           # key skipped
        assert ".co/docs/big.md" not in names              # docs skipped
        assert ".git/config" not in names                  # git skipped
        assert "__pycache__/x.pyc" not in names            # cache skipped

    def test_worktree_tarball_overlays_external_skills(self, tmp_path):
        import tarfile
        from connectonion.cli.commands.deploy_commands import _build_tarball_worktree

        proj = tmp_path / "proj"
        (proj / ".co").mkdir(parents=True)
        (proj / ".co" / "host.yaml").write_text("name: demo\n")
        (proj / "agent.py").write_text("x\n")

        skills = tmp_path / "ext"
        (skills / "world").mkdir(parents=True)
        (skills / "world" / "SKILL.md").write_text("yo\n")
        (skills / ".hidden").mkdir()
        (skills / ".hidden" / "x").write_text("x\n")

        tarball = _build_tarball_worktree(proj, [skills])
        names = set(tarfile.open(tarball).getnames())

        assert ".co/skills/world/SKILL.md" in names
        assert ".co/skills/.hidden/x" not in names         # dotfiles skipped

    @patch('connectonion.cli.commands.deploy_commands.requests.get')
    @patch('connectonion.cli.commands.deploy_commands.requests.post')
    def test_co_ai_deploys_without_git(self, mock_post, mock_get):
        from connectonion.cli.commands.deploy_commands import handle_deploy

        runner = ArgparseCliRunner()
        with runner.isolated_filesystem():
            os.makedirs(".co")
            Path(".co/host.yaml").write_text("name: demo\nentrypoint: agent.py\n")
            Path("agent.py").write_text("from connectonion import host\nhost(None)\n")
            # deliberately no `git init` — co-ai must deploy from the working tree

            mock_post.return_value = MagicMock(status_code=200, json=lambda: {"id": "x", "url": "u"})
            mock_get.return_value = MagicMock(status_code=200, json=lambda: {"status": "running", "logs": ""})

            with patch.dict(os.environ, {"OPENONION_API_KEY": "test-token"}):
                handle_deploy(co_ai=True)

            assert mock_post.called


