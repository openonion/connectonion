"""Tests for the CLI status command (``co status``).

What it tests:
- TestLoadApiKey: API key loading from multiple sources
  - test_load_api_key_from_env_var: Load from OPENONION_API_KEY env var
  - test_load_api_key_from_local_env: Load from local .env file
  - test_load_api_key_from_global_keys_env: Load from ~/.co/keys.env
- TestLoadConfig: Config file loading
- Account status display without re-authentication

Components under test:
- connectonion.cli.commands.project_cmd_lib.load_api_key
- connectonion.cli.commands.status_commands._credential_rows
- connectonion.cli.commands.status_commands.handle_status
"""

import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from rich.console import Console

from .argparse_runner import ArgparseCliRunner


class TestCredentialStatus:
    """Credential diagnostics are redacted unless explicitly revealed."""

    @staticmethod
    def _row(rows, credential):
        return next(row for row in rows if row["credential"] == credential)

    def test_reports_configured_key_and_all_matching_sources(self, tmp_path):
        from connectonion.cli.commands.status_commands import _credential_rows

        project = tmp_path / "project"
        home = tmp_path / "home"
        project.mkdir()
        home.mkdir()
        secret = "gemini-super-secret-value"
        (project / ".env").write_text(f"GEMINI_API_KEY={secret}\n")

        rows = _credential_rows(
            project_dir=project,
            home=home,
            environ={"GEMINI_API_KEY": secret},
        )
        gemini = self._row(rows, "GEMINI_API_KEY")

        assert gemini == {
            "provider": "Gemini",
            "credential": "GEMINI_API_KEY",
            "status": "configured",
            "source": "process environment + <project>/.env",
        }
        assert secret not in repr(rows)

    def test_reports_discovered_key_without_loading_environment(self, tmp_path):
        from connectonion.cli.commands.status_commands import _credential_rows

        project = tmp_path / "project"
        home = tmp_path / "home"
        project.mkdir()
        home.mkdir()
        (project / ".env").write_text("OPENAI_API_KEY=local-secret\n")
        environment = {}

        rows = _credential_rows(
            project_dir=project,
            home=home,
            environ=environment,
        )
        openai = self._row(rows, "OPENAI_API_KEY")

        assert openai["status"] == "discovered · not loaded"
        assert openai["source"] == "<project>/.env"
        assert environment == {}
        assert "local-secret" not in repr(rows)

    def test_reports_conflicting_sources_without_values(self, tmp_path):
        from connectonion.cli.commands.status_commands import _credential_rows

        project = tmp_path / "project"
        home = tmp_path / "home"
        project.mkdir()
        (home / ".co").mkdir(parents=True)
        (project / ".env").write_text("ANTHROPIC_API_KEY=local-secret\n")
        (home / ".co" / "keys.env").write_text(
            "ANTHROPIC_API_KEY=global-secret\n"
        )

        rows = _credential_rows(
            project_dir=project,
            home=home,
            environ={},
        )
        anthropic = self._row(rows, "ANTHROPIC_API_KEY")

        assert anthropic["status"] == "conflict"
        assert anthropic["source"] == "<project>/.env + ~/.co/keys.env"
        assert "local-secret" not in repr(rows)
        assert "global-secret" not in repr(rows)
        assert str(tmp_path) not in repr(rows)

    def test_ignores_placeholders_and_empty_values(self, tmp_path):
        from connectonion.cli.commands.status_commands import _credential_rows

        project = tmp_path / "project"
        home = tmp_path / "home"
        project.mkdir()
        home.mkdir()
        (project / ".env").write_text(
            "GROQ_API_KEY=your-api-key-here\n"
            "XAI_API_KEY=\n"
            "OPENROUTER_API_KEY=${OPENROUTER_API_KEY}\n"
        )

        rows = _credential_rows(
            project_dir=project,
            home=home,
            environ={},
        )

        for credential in ("GROQ_API_KEY", "XAI_API_KEY", "OPENROUTER_API_KEY"):
            assert self._row(rows, credential)["status"] == "missing"

    @patch('connectonion.address.load')
    @patch('connectonion.address.sign')
    @patch('connectonion.cli.commands.status_commands.requests.get')
    @patch('connectonion.cli.commands.status_commands.requests.post')
    def test_default_status_never_prints_api_key_material(
        self,
        mock_post,
        mock_get,
        mock_sign,
        mock_load,
        tmp_path,
        monkeypatch,
    ):
        from connectonion.cli.commands import status_commands

        secret = "openonion-secret-that-must-never-appear"
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("OPENONION_API_KEY", secret)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        co_dir = tmp_path / ".co" / "keys"
        co_dir.mkdir(parents=True)
        (co_dir / "agent.key").write_text("dummy")

        mock_load.return_value = {"address": "0x1234567890abcdef"}
        mock_sign.return_value = b'\x00' * 64
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "user": {
                    "balance_usd": 1.0,
                    "total_cost_usd": 0.0,
                    "credits_usd": 1.0,
                    "email": {"address": "test@mail.openonion.ai"},
                }
            },
        )
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {"deployments": []},
        )

        output = StringIO()
        test_console = Console(
            file=output,
            force_terminal=False,
            color_system=None,
            width=140,
        )
        with patch.object(Path, "home", return_value=fake_home):
            with patch.object(status_commands, "console", test_console):
                status_commands.handle_status()

        rendered = output.getvalue()
        assert "Credential Sources" in rendered
        assert "OPENONION_API_KEY" in rendered
        assert "process environment" in rendered
        assert secret not in rendered
        assert secret[:20] not in rendered

    def test_explicit_reveal_prints_full_values_and_sources(
        self,
        tmp_path,
        monkeypatch,
    ):
        from connectonion.cli.commands import status_commands

        project = tmp_path / "project"
        fake_home = tmp_path / "home"
        project.mkdir()
        fake_home.mkdir()
        process_secret = "gemini-process-secret"
        local_secret = "gemini-project-secret"
        (project / ".env").write_text(f"GEMINI_API_KEY={local_secret}\n")
        monkeypatch.chdir(project)

        output = StringIO()
        test_console = Console(
            file=output,
            force_terminal=False,
            color_system=None,
            width=160,
        )
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": process_secret},
            clear=True,
        ):
            with patch.object(Path, "home", return_value=fake_home):
                with patch.object(status_commands, "console", test_console):
                    status_commands._show_credentials(reveal=True)

        rendered = output.getvalue()
        assert "Revealed Credential Values" in rendered
        assert "Secrets shown in full" in rendered
        assert "process environment" in rendered
        assert "<project>/.env" in rendered
        assert process_secret in rendered
        assert local_secret in rendered


class TestLoadApiKey:
    """Tests for _load_api_key function."""

    def test_load_api_key_from_env_var(self):
        """Test loading API key from environment variable."""
        from connectonion.cli.commands.project_cmd_lib import load_api_key

        with patch.dict(os.environ, {"OPENONION_API_KEY": "test-key-from-env"}, clear=False):
            result = load_api_key()
            assert result == "test-key-from-env"

    def test_load_api_key_from_local_env(self):
        """Test loading API key from local .env file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            # Create .env file
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("OPENONION_API_KEY=local-env-key\n")

            try:
                # Clear env var
                with patch.dict(os.environ, {}, clear=True):
                    from connectonion.cli.commands.project_cmd_lib import load_api_key

                    result = load_api_key()
                    assert result == "local-env-key"
            finally:
                os.chdir(original_cwd)

    def test_load_api_key_from_global_keys_env(self):
        """Test loading API key from ~/.co/keys.env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            fake_home = Path(tmpdir) / "fake_home"
            fake_home.mkdir()
            co_dir = fake_home / ".co"
            co_dir.mkdir()
            keys_env = co_dir / "keys.env"
            keys_env.write_text("OPENONION_API_KEY=global-keys-env-key\n")

            try:
                with patch.object(Path, 'home', return_value=fake_home):
                    with patch.dict(os.environ, {}, clear=True):
                        from connectonion.cli.commands.project_cmd_lib import load_api_key

                        assert load_api_key() == "global-keys-env-key"
            finally:
                os.chdir(original_cwd)

    def test_load_api_key_returns_none_when_not_found(self):
        """Test _load_api_key returns None when key not found anywhere."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            fake_home = Path(tmpdir) / "fake_home"
            fake_home.mkdir()

            try:
                with patch.object(Path, 'home', return_value=fake_home):
                    with patch.dict(os.environ, {}, clear=True):
                        from connectonion.cli.commands.project_cmd_lib import load_api_key

                        result = load_api_key()
                        assert not result
            finally:
                os.chdir(original_cwd)


class TestHandleStatusNoApiKey:
    """Tests for handle_status when API key is not found."""

    @patch('connectonion.cli.commands.status_commands.console')
    @patch('connectonion.cli.commands.status_commands.load_api_key')
    def test_status_shows_error_no_api_key(self, mock_load_key, mock_console):
        """Test status shows error when no API key found."""
        mock_load_key.return_value = None

        from connectonion.cli.commands.status_commands import handle_status
        handle_status()

        # Should print error message
        assert mock_console.print.called

    @patch('connectonion.cli.commands.status_commands._show_credentials')
    @patch('connectonion.cli.commands.status_commands.load_api_key')
    def test_status_forwards_explicit_reveal(
        self,
        mock_load_key,
        mock_show_credentials,
    ):
        mock_load_key.return_value = None

        from connectonion.cli.commands.status_commands import handle_status

        handle_status(reveal=True)

        mock_show_credentials.assert_called_once_with(reveal=True)


class TestStatusCli:
    """Tests for the status command's Typer options."""

    def setup_method(self):
        self.runner = ArgparseCliRunner()

    @patch('connectonion.cli.commands.status_commands.handle_status')
    def test_status_reveal_flag(self, mock_handle_status):
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ["status", "--reveal"])

        assert result.exit_code == 0
        mock_handle_status.assert_called_once_with(reveal=True)


class TestHandleStatusNoKeys:
    """Tests for handle_status when keys are not found."""

    @patch('connectonion.cli.commands.status_commands.console')
    @patch('connectonion.cli.commands.status_commands.load_api_key')
    @patch('connectonion.address.load')
    def test_status_shows_error_no_keys(self, mock_address_load, mock_load_key, mock_console):
        """Test status shows error when no keys found."""
        mock_load_key.return_value = "test-api-key"
        mock_address_load.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            fake_home = Path(tmpdir) / "fake_home"
            fake_home.mkdir()

            try:
                with patch.object(Path, 'home', return_value=fake_home):
                    from connectonion.cli.commands.status_commands import handle_status
                    handle_status()

                assert mock_console.print.called
            finally:
                os.chdir(original_cwd)


class TestHandleStatusSuccess:
    """Tests for successful status display."""

    @patch('connectonion.cli.commands.status_commands.console')
    @patch('connectonion.cli.commands.status_commands.load_api_key')
    @patch('connectonion.address.load')
    @patch('connectonion.address.sign')
    @patch('connectonion.cli.commands.status_commands.requests.get')
    @patch('connectonion.cli.commands.status_commands.requests.post')
    def test_status_displays_account_info(self, mock_post, mock_get, mock_sign, mock_load, mock_load_key, mock_console):
        """Test status displays account information."""
        mock_load_key.return_value = "test-api-key-12345"
        mock_load.return_value = {"address": "0x1234567890abcdef"}
        mock_sign.return_value = b'\x00' * 64  # Dummy signature

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "user": {
                "balance_usd": 10.5,
                "total_cost_usd": 2.5,
                "credits_usd": 5.0,
                "email": {"address": "test@mail.openonion.ai"}
            }
        }
        mock_post.return_value = mock_response
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "deployments": [
                    {
                        "project_name": "co-ai-agent",
                        "status": "running",
                        "is_active": True,
                        "container_running": True,
                        "url": "https://co-ai-agent.agents.openonion.ai",
                    }
                ]
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            # Create .co/keys directory
            co_dir = Path(tmpdir) / ".co"
            co_dir.mkdir()
            keys_dir = co_dir / "keys"
            keys_dir.mkdir()
            (keys_dir / "agent.key").write_text("dummy")

            try:
                from connectonion.cli.commands.status_commands import handle_status
                handle_status()

                # Should have called the API
                mock_post.assert_called_once()
                mock_get.assert_called_once()
                # Should have printed to console
                assert mock_console.print.called
            finally:
                os.chdir(original_cwd)

    @patch('connectonion.cli.commands.status_commands.console')
    @patch('connectonion.cli.commands.status_commands.load_api_key')
    @patch('connectonion.address.load')
    @patch('connectonion.address.sign')
    @patch('connectonion.cli.commands.status_commands.requests.get')
    @patch('connectonion.cli.commands.status_commands.requests.post')
    def test_status_shows_low_balance_warning(self, mock_post, mock_get, mock_sign, mock_load, mock_load_key, mock_console):
        """Test status shows warning when balance is low."""
        mock_load_key.return_value = "test-api-key-12345"
        mock_load.return_value = {"address": "0x1234567890abcdef"}
        mock_sign.return_value = b'\x00' * 64

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "user": {
                "balance_usd": 0.0,  # Zero balance
                "total_cost_usd": 10.0,
                "credits_usd": 0.0
            }
        }
        mock_post.return_value = mock_response
        mock_get.return_value = Mock(status_code=200, json=lambda: {"deployments": []})

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            co_dir = Path(tmpdir) / ".co"
            co_dir.mkdir()
            keys_dir = co_dir / "keys"
            keys_dir.mkdir()
            (keys_dir / "agent.key").write_text("dummy")

            try:
                from connectonion.cli.commands.status_commands import handle_status
                handle_status()

                assert mock_console.print.called
            finally:
                os.chdir(original_cwd)


class TestDeploymentsStatus:
    """Tests for deployment list display in co status."""

    @patch('connectonion.cli.commands.status_commands.requests.get')
    def test_fetch_deployments(self, mock_get):
        """Test loading deployments from the cloud API."""
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "deployments": [
                    {
                        "project_name": "my-agent",
                        "status": "running",
                        "is_active": True,
                        "container_running": True,
                        "url": "https://my-agent.agents.openonion.ai",
                    }
                ]
            },
        )

        from connectonion.cli.commands.status_commands import _fetch_deployments

        deployments = _fetch_deployments("api-key")

        assert deployments[0]["project_name"] == "my-agent"
        mock_get.assert_called_once()

    @patch('connectonion.cli.commands.status_commands.console')
    @patch('connectonion.cli.commands.status_commands.requests.get')
    def test_fetch_deployments_api_error_returns_empty_list(self, mock_get, mock_console):
        """Test deployment API errors do not hide account status."""
        mock_get.return_value = Mock(status_code=500)

        from connectonion.cli.commands.status_commands import _fetch_deployments

        assert _fetch_deployments("api-key") == []
        assert mock_console.print.called


class TestHandleStatusApiError:
    """Tests for API error handling."""

    @patch('connectonion.cli.commands.status_commands.console')
    @patch('connectonion.cli.commands.status_commands.load_api_key')
    @patch('connectonion.address.load')
    @patch('connectonion.address.sign')
    @patch('connectonion.cli.commands.status_commands.requests.post')
    def test_status_handles_api_error(self, mock_post, mock_sign, mock_load, mock_load_key, mock_console):
        """Test status handles API error gracefully."""
        mock_load_key.return_value = "test-api-key"
        mock_load.return_value = {"address": "0x1234567890abcdef"}
        mock_sign.return_value = b'\x00' * 64

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            co_dir = Path(tmpdir) / ".co"
            co_dir.mkdir()
            keys_dir = co_dir / "keys"
            keys_dir.mkdir()
            (keys_dir / "agent.key").write_text("dummy")

            try:
                from connectonion.cli.commands.status_commands import handle_status
                handle_status()

                # Should print error
                assert mock_console.print.called
            finally:
                os.chdir(original_cwd)

    @patch('connectonion.cli.commands.status_commands.console')
    @patch('connectonion.cli.commands.status_commands.load_api_key')
    @patch('connectonion.address.load')
    @patch('connectonion.address.sign')
    @patch('connectonion.cli.commands.status_commands.requests.post')
    def test_status_handles_401_unauthorized(self, mock_post, mock_sign, mock_load, mock_load_key, mock_console):
        """Test status handles 401 unauthorized error."""
        mock_load_key.return_value = "invalid-api-key"
        mock_load.return_value = {"address": "0x1234567890abcdef"}
        mock_sign.return_value = b'\x00' * 64

        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_post.return_value = mock_response

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            co_dir = Path(tmpdir) / ".co"
            co_dir.mkdir()
            keys_dir = co_dir / "keys"
            keys_dir.mkdir()
            (keys_dir / "agent.key").write_text("dummy")

            try:
                from connectonion.cli.commands.status_commands import handle_status
                handle_status()

                assert mock_console.print.called
            finally:
                os.chdir(original_cwd)
