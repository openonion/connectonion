"""Tests for co auth microsoft CLI command."""

"""
LLM-Note: Tests for Microsoft OAuth CLI authentication flow

What it tests:
- TestAuthMicrosoftHelp: Help text and prerequisites
  - test_auth_help_shows_microsoft_option: Verify microsoft appears in help
  - test_auth_microsoft_requires_openonion_auth: Verify OpenOnion auth required first
- TestSaveMicrosoftToEnv: Credential persistence
  - test_save_microsoft_connection_to_new_env: Save non-secret metadata only
  - test_save_microsoft_connection_removes_legacy_tokens: Purge old local tokens
  - test_save_microsoft_credentials_file_permissions: Verify 0600 permissions on Unix
- TestAuthMicrosoftFlow: OAuth flow with mocked backend
  - test_auth_microsoft_success_flow: Complete successful OAuth flow
  - test_auth_microsoft_init_failure: Handle OAuth init errors
  - test_auth_microsoft_timeout: Handle authorization timeout
- TestAuthMicrosoftIntegration: Manual integration tests (skipped)

Components under test:
- connectonion.cli.commands.auth_commands (auth microsoft command)
- connectonion.cli.commands.auth_commands._save_microsoft_to_env
"""

import os
import tempfile
from pathlib import Path
import pytest
from unittest.mock import Mock, patch, MagicMock

from .argparse_runner import ArgparseCliRunner


@pytest.fixture(autouse=True)
def isolated_home(tmp_path):
    """Never let CLI auth tests read or modify the developer's real config."""
    home = tmp_path / "home"
    config_dir = home / ".co"
    config_dir.mkdir(parents=True)
    (config_dir / "keys.env").write_text("OPENONION_API_KEY=global-key\n")
    with patch.object(Path, "home", return_value=home):
        yield home


class TestAuthMicrosoftHelp:
    """Test help text for co auth microsoft command."""

    def setup_method(self):
        """Setup test environment."""
        self.runner = ArgparseCliRunner()

    def test_auth_help_shows_microsoft_option(self):
        """Test that co auth --help mentions microsoft service."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['auth', '--help'])
        assert result.exit_code == 0
        assert 'microsoft' in result.output.lower()

    @patch('connectonion.cli.commands.auth_commands.load_api_key')
    def test_auth_microsoft_requires_openonion_auth(self, mock_load_key):
        """Test that co auth microsoft requires prior OpenOnion authentication."""
        mock_load_key.return_value = None

        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['auth', 'microsoft'])
            assert 'Not authenticated with OpenOnion' in result.output


class TestSaveMicrosoftToEnv:
    """Test the _save_microsoft_to_env helper function."""

    def test_save_microsoft_connection_to_new_env(self):
        """Save only connection metadata, never Microsoft bearer tokens."""
        from connectonion.cli.commands.auth_commands import _save_microsoft_to_env

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / '.env'

            connection = {
                'scopes': 'Mail.Read,Mail.Send,Calendars.Read',
                'email': 'test@outlook.com',
            }

            _save_microsoft_to_env(env_file, connection)

            assert env_file.exists()

            content = env_file.read_text()
            assert 'MICROSOFT_CONNECTED=true' in content
            assert 'MICROSOFT_SCOPES=Mail.Read,Mail.Send,Calendars.Read' in content
            assert 'MICROSOFT_EMAIL=test@outlook.com' in content
            assert 'TOKEN' not in content

    def test_save_microsoft_connection_removes_legacy_tokens(self):
        """A new authorization removes tokens left by older SDK releases."""
        from connectonion.cli.commands.auth_commands import _save_microsoft_to_env

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / '.env'

            env_file.write_text('''OPENONION_API_KEY=existing-key
MICROSOFT_ACCESS_TOKEN=old-token
MICROSOFT_REFRESH_TOKEN=old-refresh
MICROSOFT_TOKEN_EXPIRES_AT=old-expiry
MICROSOFT_EMAIL=old@outlook.com
OTHER_VAR=keep-this
''')

            connection = {
                'scopes': 'Mail.Read',
                'email': 'new@outlook.com',
            }

            _save_microsoft_to_env(env_file, connection)

            content = env_file.read_text()

            assert 'OPENONION_API_KEY=existing-key' in content
            assert 'OTHER_VAR=keep-this' in content

            assert 'MICROSOFT_CONNECTED=true' in content
            assert 'MICROSOFT_EMAIL=new@outlook.com' in content
            assert 'MICROSOFT_ACCESS_TOKEN' not in content
            assert 'MICROSOFT_REFRESH_TOKEN' not in content
            assert 'MICROSOFT_TOKEN_EXPIRES_AT' not in content

    def test_save_microsoft_credentials_file_permissions(self):
        """Test that .env file has restrictive permissions on Unix."""
        from connectonion.cli.commands.auth_commands import _save_microsoft_to_env
        import sys

        if sys.platform == 'win32':
            pytest.skip("File permissions test not applicable on Windows")

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / '.env'

            connection = {
                'scopes': 'Mail.Read',
                'email': 'test@outlook.com',
            }

            _save_microsoft_to_env(env_file, connection)

            stat = env_file.stat()
            assert oct(stat.st_mode)[-3:] == '600'


class TestAuthMicrosoftFlow:
    """Test the co auth microsoft flow with mocked backend."""

    def setup_method(self):
        """Setup test environment."""
        self.runner = ArgparseCliRunner()

    @patch('connectonion.cli.commands.auth_commands.webbrowser')
    @patch('connectonion.cli.commands.auth_commands.requests')
    def test_auth_microsoft_success_flow(
        self, mock_requests, mock_webbrowser, isolated_home
    ):
        """Test successful Microsoft OAuth flow."""
        with self.runner.isolated_filesystem():
            Path('.env').write_text('OPENONION_API_KEY=test-key\n')

            mock_init_response = Mock()
            mock_init_response.status_code = 200
            mock_init_response.json.return_value = {
                'auth_url': 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?...',
                'authorization_id': 'authorization-id',
            }

            mock_status_response = Mock()
            mock_status_response.status_code = 200
            mock_status_response.json.return_value = {
                'connected': True,
                'scopes': 'Mail.Read,Mail.Send,Calendars.Read,Calendars.ReadWrite',
                'email': 'test@outlook.com',
            }

            mock_requests.get.side_effect = [
                mock_init_response,
                mock_status_response,
            ]

            mock_webbrowser.open.return_value = True

            with patch('time.sleep', return_value=None):
                from connectonion.cli.main import cli
                result = self.runner.invoke(cli, ['auth', 'microsoft'])

            mock_requests.delete.assert_not_called()
            mock_webbrowser.open.assert_called_once()
            status_call = mock_requests.get.call_args_list[1]
            assert status_call.kwargs["params"] == {
                "authorization_id": "authorization-id"
            }

            env_content = Path('.env').read_text()
            assert 'MICROSOFT_CONNECTED=true' in env_content
            assert 'MICROSOFT_EMAIL=test@outlook.com' in env_content
            assert 'MICROSOFT_ACCESS_TOKEN' not in env_content
            assert 'MICROSOFT_REFRESH_TOKEN' not in env_content
            assert all('/credentials' not in call.args[0] for call in mock_requests.get.call_args_list)

            global_content = (isolated_home / '.co' / 'keys.env').read_text()
            assert 'MICROSOFT_CONNECTED=true' in global_content
            assert 'MICROSOFT_ACCESS_TOKEN' not in global_content
            assert 'MICROSOFT_REFRESH_TOKEN' not in global_content

    @patch('connectonion.cli.commands.auth_commands.requests')
    def test_auth_microsoft_init_failure(self, mock_requests):
        """Test handling of OAuth init failure."""
        with self.runner.isolated_filesystem():
            Path('.env').write_text('OPENONION_API_KEY=test-key\n')

            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = 'Internal Server Error'
            mock_requests.get.return_value = mock_response

            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['auth', 'microsoft'])

            assert 'Failed to initialize OAuth' in result.output or result.exit_code != 0

    @patch('connectonion.cli.commands.auth_commands.webbrowser')
    @patch('connectonion.cli.commands.auth_commands.requests')
    @patch('time.sleep')
    def test_auth_microsoft_timeout(self, mock_sleep, mock_requests, mock_webbrowser):
        """Test handling of authorization timeout."""
        with self.runner.isolated_filesystem():
            Path('.env').write_text('OPENONION_API_KEY=test-key\n')

            mock_init_response = Mock()
            mock_init_response.status_code = 200
            mock_init_response.json.return_value = {
                'auth_url': 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?...',
                'authorization_id': 'authorization-id',
            }

            mock_status_response = Mock()
            mock_status_response.status_code = 200
            mock_status_response.json.return_value = {'connected': False}

            mock_requests.get.side_effect = [
                mock_init_response,
                *[mock_status_response] * 60
            ]

            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['auth', 'microsoft'])

            assert 'timed out' in result.output.lower() or result.exit_code != 0
