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

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from requests import RequestException

from connectonion.cli.oauth_loopback import OAuthLoopbackTimeout
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

    def test_connection_metadata_requires_strict_contract(self):
        from connectonion.cli.commands.auth_commands import (
            _is_valid_microsoft_connection,
        )

        assert _is_valid_microsoft_connection(
            {
                'connected': True,
                'scopes': 'Mail.ReadWrite,Mail.Send,Calendars.ReadWrite',
                'email': 'test@outlook.com',
            }
        )
        assert not _is_valid_microsoft_connection(
            {'connected': 'true', 'scopes': 'Mail.ReadWrite'}
        )
        assert not _is_valid_microsoft_connection(
            {'connected': True, 'scopes': ''}
        )
        assert not _is_valid_microsoft_connection(
            {'connected': True, 'scopes': ['Mail.ReadWrite']}
        )

    def test_save_microsoft_connection_to_new_env(self):
        """Save only connection metadata, never Microsoft bearer tokens."""
        from connectonion.cli.commands.auth_commands import _save_microsoft_to_env

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / '.env'

            connection = {
                'scopes': 'Mail.ReadWrite,Mail.Send,Calendars.ReadWrite',
                'email': 'test@outlook.com',
            }

            _save_microsoft_to_env(env_file, connection)

            assert env_file.exists()

            content = env_file.read_text()
            assert 'MICROSOFT_CONNECTED=true' in content
            assert (
                'MICROSOFT_SCOPES=Mail.ReadWrite,Mail.Send,Calendars.ReadWrite'
                in content
            )
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

    @patch('connectonion.cli.commands.auth_commands.MicrosoftOAuthLoopback')
    @patch('connectonion.cli.commands.auth_commands.webbrowser')
    @patch('connectonion.cli.commands.auth_commands.requests')
    def test_auth_microsoft_success_flow(
        self, mock_requests, mock_webbrowser, mock_loopback, isolated_home
    ):
        """Bind loopback, initialize, complete, and persist metadata only."""
        with self.runner.isolated_filesystem():
            Path('.env').write_text('OPENONION_API_KEY=test-key\n')

            listener = mock_loopback.return_value.__enter__.return_value
            listener.callback_uri = (
                'http://127.0.0.1:49152/oauth/microsoft/callback'
            )
            listener.wait_for_result.return_value = Mock(
                code='one-use-code',
                error=None,
            )

            mock_init_response = Mock()
            mock_init_response.status_code = 200
            mock_init_response.json.return_value = {
                'auth_url': 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?...',
                'authorization_id': 'a' * 43,
            }

            mock_complete_response = Mock()
            mock_complete_response.status_code = 200
            mock_complete_response.json.return_value = {
                'connected': True,
                'scopes': 'Mail.ReadWrite,Mail.Send,Calendars.ReadWrite',
                'email': 'test@outlook.com',
            }
            mock_requests.post.side_effect = [
                mock_init_response,
                mock_complete_response,
            ]
            mock_webbrowser.open.return_value = True

            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['auth', 'microsoft'])

            mock_requests.delete.assert_not_called()
            mock_webbrowser.open.assert_called_once()
            listener.wait_for_result.assert_called_once_with('a' * 43)
            init_call, complete_call = mock_requests.post.call_args_list
            assert init_call.args[0].endswith('/microsoft/init')
            assert init_call.kwargs['json'] == {
                'completion_redirect_uri': listener.callback_uri
            }
            assert complete_call.args[0].endswith('/microsoft/complete')
            assert complete_call.kwargs['json'] == {
                'authorization_id': 'a' * 43,
                'code': 'one-use-code',
            }
            mock_requests.get.assert_not_called()

            env_content = Path('.env').read_text()
            assert 'MICROSOFT_CONNECTED=true' in env_content
            assert 'MICROSOFT_EMAIL=test@outlook.com' in env_content
            assert 'MICROSOFT_ACCESS_TOKEN' not in env_content
            assert 'MICROSOFT_REFRESH_TOKEN' not in env_content
            assert '/credentials' not in str(mock_requests.mock_calls)
            assert 'one-use-code' not in result.output

            global_content = (isolated_home / '.co' / 'keys.env').read_text()
            assert 'MICROSOFT_CONNECTED=true' in global_content
            assert 'MICROSOFT_ACCESS_TOKEN' not in global_content
            assert 'MICROSOFT_REFRESH_TOKEN' not in global_content

    @patch('connectonion.cli.commands.auth_commands.MicrosoftOAuthLoopback')
    @patch('connectonion.cli.commands.auth_commands.requests')
    def test_auth_microsoft_init_failure(self, mock_requests, mock_loopback):
        """Test handling of OAuth init failure."""
        with self.runner.isolated_filesystem():
            Path('.env').write_text('OPENONION_API_KEY=test-key\n')

            listener = mock_loopback.return_value.__enter__.return_value
            listener.callback_uri = (
                'http://127.0.0.1:49152/oauth/microsoft/callback'
            )

            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = 'Internal Server Error'
            mock_requests.post.return_value = mock_response

            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['auth', 'microsoft'])

            assert 'Failed to initialize OAuth' in result.output or result.exit_code != 0
            mock_requests.get.assert_not_called()

    @patch('connectonion.cli.commands.auth_commands.MicrosoftOAuthLoopback')
    @patch('connectonion.cli.commands.auth_commands.webbrowser')
    @patch('connectonion.cli.commands.auth_commands.requests')
    def test_auth_microsoft_rejects_non_microsoft_authorization_url(
        self,
        mock_requests,
        mock_webbrowser,
        mock_loopback,
    ):
        with self.runner.isolated_filesystem():
            Path('.env').write_text('OPENONION_API_KEY=test-key\n')
            listener = mock_loopback.return_value.__enter__.return_value
            listener.callback_uri = (
                'http://127.0.0.1:49152/oauth/microsoft/callback'
            )
            response = Mock(status_code=200)
            response.json.return_value = {
                'auth_url': 'https://login.microsoftonline.com.evil/authorize',
                'authorization_id': 'a' * 43,
            }
            mock_requests.post.return_value = response

            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['auth', 'microsoft'])

            assert 'initialization response is invalid' in result.output
            mock_webbrowser.open.assert_not_called()
            listener.wait_for_result.assert_not_called()

    @patch('connectonion.cli.commands.auth_commands.MicrosoftOAuthLoopback')
    @patch('connectonion.cli.commands.auth_commands.webbrowser')
    @patch('connectonion.cli.commands.auth_commands.requests')
    def test_auth_microsoft_timeout(
        self,
        mock_requests,
        mock_webbrowser,
        mock_loopback,
    ):
        """Test handling of authorization timeout."""
        with self.runner.isolated_filesystem():
            Path('.env').write_text('OPENONION_API_KEY=test-key\n')

            listener = mock_loopback.return_value.__enter__.return_value
            listener.callback_uri = (
                'http://127.0.0.1:49152/oauth/microsoft/callback'
            )
            listener.wait_for_result.side_effect = OAuthLoopbackTimeout()

            mock_init_response = Mock()
            mock_init_response.status_code = 200
            mock_init_response.json.return_value = {
                'auth_url': 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?...',
                'authorization_id': 'a' * 43,
            }
            mock_requests.post.return_value = mock_init_response
            mock_webbrowser.open.return_value = True

            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['auth', 'microsoft'])

            assert 'timed out' in result.output.lower() or result.exit_code != 0
            assert mock_requests.post.call_count == 1
            mock_requests.get.assert_not_called()

    @patch('connectonion.cli.commands.auth_commands.MicrosoftOAuthLoopback')
    @patch('connectonion.cli.commands.auth_commands.webbrowser')
    @patch('connectonion.cli.commands.auth_commands.requests')
    def test_auth_microsoft_definitive_completion_failure_does_not_poll(
        self,
        mock_requests,
        mock_webbrowser,
        mock_loopback,
    ):
        """A definitive API failure is not treated as a lost response."""
        with self.runner.isolated_filesystem():
            Path('.env').write_text(
                'OPENONION_API_KEY=test-key\n'
                'MICROSOFT_CONNECTED=true\n'
                'MICROSOFT_EMAIL=existing@outlook.com\n'
            )
            listener = mock_loopback.return_value.__enter__.return_value
            listener.callback_uri = (
                'http://127.0.0.1:49152/oauth/microsoft/callback'
            )
            listener.wait_for_result.return_value = Mock(
                code='one-use-code',
                error=None,
            )

            init_response = Mock(status_code=200)
            init_response.json.return_value = {
                'auth_url': (
                    'https://login.microsoftonline.com/common/oauth2/v2.0/authorize'
                ),
                'authorization_id': 'a' * 43,
            }
            completion_response = Mock(status_code=409)
            mock_requests.post.side_effect = [
                init_response,
                completion_response,
            ]
            mock_webbrowser.open.return_value = True

            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['auth', 'microsoft'])

            assert 'could not be completed' in result.output
            mock_requests.get.assert_not_called()
            assert 'MICROSOFT_EMAIL=existing@outlook.com' in Path('.env').read_text()

    @patch('connectonion.cli.commands.auth_commands.MicrosoftOAuthLoopback')
    @patch('connectonion.cli.commands.auth_commands.webbrowser')
    @patch('connectonion.cli.commands.auth_commands.requests')
    def test_auth_microsoft_recovers_lost_completion_response(
        self,
        mock_requests,
        mock_webbrowser,
        mock_loopback,
    ):
        """A correlated status read recovers a committed but lost response."""
        with self.runner.isolated_filesystem():
            Path('.env').write_text('OPENONION_API_KEY=test-key\n')
            listener = mock_loopback.return_value.__enter__.return_value
            listener.callback_uri = (
                'http://127.0.0.1:49152/oauth/microsoft/callback'
            )
            listener.wait_for_result.return_value = Mock(
                code='one-use-code',
                error=None,
            )

            init_response = Mock(status_code=200)
            init_response.json.return_value = {
                'auth_url': (
                    'https://login.microsoftonline.com/common/oauth2/v2.0/authorize'
                ),
                'authorization_id': 'a' * 43,
            }
            mock_requests.post.side_effect = [
                init_response,
                RequestException('response lost'),
            ]
            status_response = Mock(status_code=200)
            status_response.json.return_value = {
                'connected': True,
                'scopes': 'Mail.ReadWrite,Mail.Send,Calendars.ReadWrite',
                'email': 'recovered@outlook.com',
            }
            mock_requests.get.return_value = status_response
            mock_webbrowser.open.return_value = True

            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['auth', 'microsoft'])

            assert 'Microsoft account connected' in result.output
            status_call = mock_requests.get.call_args
            assert status_call.kwargs['params'] == {
                'authorization_id': 'a' * 43
            }
            assert 'MICROSOFT_EMAIL=recovered@outlook.com' in Path('.env').read_text()

    @patch('connectonion.cli.commands.auth_commands.MicrosoftOAuthLoopback')
    @patch('connectonion.cli.commands.auth_commands.webbrowser')
    @patch('connectonion.cli.commands.auth_commands.requests')
    def test_auth_microsoft_cancel_keeps_existing_metadata(
        self,
        mock_requests,
        mock_webbrowser,
        mock_loopback,
    ):
        """A denied consent never completes or erases the working connection."""
        with self.runner.isolated_filesystem():
            Path('.env').write_text(
                'OPENONION_API_KEY=test-key\n'
                'MICROSOFT_CONNECTED=true\n'
                'MICROSOFT_EMAIL=existing@outlook.com\n'
            )
            listener = mock_loopback.return_value.__enter__.return_value
            listener.callback_uri = (
                'http://127.0.0.1:49152/oauth/microsoft/callback'
            )
            listener.wait_for_result.return_value = Mock(
                code=None,
                error='authorization_failed',
            )
            init_response = Mock(status_code=200)
            init_response.json.return_value = {
                'auth_url': (
                    'https://login.microsoftonline.com/common/oauth2/v2.0/authorize'
                ),
                'authorization_id': 'a' * 43,
            }
            mock_requests.post.return_value = init_response
            mock_webbrowser.open.return_value = True

            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['auth', 'microsoft'])

            assert 'cancelled or denied' in result.output
            assert mock_requests.post.call_count == 1
            assert 'MICROSOFT_EMAIL=existing@outlook.com' in Path('.env').read_text()
