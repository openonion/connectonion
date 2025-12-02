"""Tests for co auth microsoft CLI command."""

import os
import tempfile
from pathlib import Path
import pytest
from unittest.mock import Mock, patch, MagicMock

from .argparse_runner import ArgparseCliRunner


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

    @patch('connectonion.cli.commands.auth_commands._load_api_key')
    def test_auth_microsoft_requires_openonion_auth(self, mock_load_key):
        """Test that co auth microsoft requires prior OpenOnion authentication."""
        mock_load_key.return_value = None

        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            result = self.runner.invoke(cli, ['auth', 'microsoft'])
            assert 'Not authenticated with OpenOnion' in result.output


class TestSaveMicrosoftToEnv:
    """Test the _save_microsoft_to_env helper function."""

    def test_save_microsoft_credentials_to_new_env(self):
        """Test saving Microsoft credentials to a new .env file."""
        from connectonion.cli.commands.auth_commands import _save_microsoft_to_env

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / '.env'

            credentials = {
                'access_token': 'eyJ0eXAi.test123',
                'refresh_token': '0.ATcA.test456',
                'expires_at': '2025-12-31T23:59:59',
                'scopes': 'Mail.Read,Mail.Send,Calendars.Read',
                'microsoft_email': 'test@outlook.com'
            }

            _save_microsoft_to_env(env_file, credentials)

            assert env_file.exists()

            content = env_file.read_text()
            assert 'MICROSOFT_ACCESS_TOKEN=eyJ0eXAi.test123' in content
            assert 'MICROSOFT_REFRESH_TOKEN=0.ATcA.test456' in content
            assert 'MICROSOFT_TOKEN_EXPIRES_AT=2025-12-31T23:59:59' in content
            assert 'MICROSOFT_SCOPES=Mail.Read,Mail.Send,Calendars.Read' in content
            assert 'MICROSOFT_EMAIL=test@outlook.com' in content

    def test_save_microsoft_credentials_updates_existing_env(self):
        """Test that saving Microsoft credentials updates existing .env."""
        from connectonion.cli.commands.auth_commands import _save_microsoft_to_env

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / '.env'

            env_file.write_text('''OPENONION_API_KEY=existing-key
MICROSOFT_ACCESS_TOKEN=old-token
MICROSOFT_REFRESH_TOKEN=old-refresh
MICROSOFT_EMAIL=old@outlook.com
OTHER_VAR=keep-this
''')

            credentials = {
                'access_token': 'new-token',
                'refresh_token': 'new-refresh',
                'expires_at': '2025-12-31T23:59:59',
                'scopes': 'Mail.Read',
                'microsoft_email': 'new@outlook.com'
            }

            _save_microsoft_to_env(env_file, credentials)

            content = env_file.read_text()

            assert 'OPENONION_API_KEY=existing-key' in content
            assert 'OTHER_VAR=keep-this' in content

            assert 'MICROSOFT_ACCESS_TOKEN=new-token' in content
            assert 'MICROSOFT_REFRESH_TOKEN=new-refresh' in content
            assert 'MICROSOFT_EMAIL=new@outlook.com' in content

            assert 'old-token' not in content
            assert 'old-refresh' not in content

    def test_save_microsoft_credentials_file_permissions(self):
        """Test that .env file has restrictive permissions on Unix."""
        from connectonion.cli.commands.auth_commands import _save_microsoft_to_env
        import sys

        if sys.platform == 'win32':
            pytest.skip("File permissions test not applicable on Windows")

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / '.env'

            credentials = {
                'access_token': 'test',
                'refresh_token': 'test',
                'expires_at': '2025-12-31T23:59:59',
                'scopes': 'Mail.Read',
                'microsoft_email': 'test@outlook.com'
            }

            _save_microsoft_to_env(env_file, credentials)

            stat = env_file.stat()
            assert oct(stat.st_mode)[-3:] == '600'


class TestAuthMicrosoftFlow:
    """Test the co auth microsoft flow with mocked backend."""

    def setup_method(self):
        """Setup test environment."""
        self.runner = ArgparseCliRunner()

    @patch('connectonion.cli.commands.auth_commands.webbrowser')
    @patch('connectonion.cli.commands.auth_commands.requests')
    def test_auth_microsoft_success_flow(self, mock_requests, mock_webbrowser):
        """Test successful Microsoft OAuth flow."""
        with self.runner.isolated_filesystem():
            Path('.env').write_text('OPENONION_API_KEY=test-key\n')

            mock_revoke_response = Mock()
            mock_revoke_response.status_code = 404

            mock_init_response = Mock()
            mock_init_response.status_code = 200
            mock_init_response.json.return_value = {
                'auth_url': 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?...'
            }

            mock_status_response = Mock()
            mock_status_response.status_code = 200
            mock_status_response.json.return_value = {'connected': True}

            mock_creds_response = Mock()
            mock_creds_response.status_code = 200
            mock_creds_response.json.return_value = {
                'access_token': 'eyJ0eXAi.test',
                'refresh_token': '0.ATcA.test',
                'expires_at': '2025-12-31T23:59:59',
                'scopes': 'Mail.Read,Mail.Send,Calendars.Read,Calendars.ReadWrite',
                'microsoft_email': 'test@outlook.com'
            }

            mock_requests.delete.return_value = mock_revoke_response
            mock_requests.get.side_effect = [
                mock_init_response,
                mock_status_response,
                mock_creds_response
            ]

            mock_webbrowser.open.return_value = True

            with patch('time.sleep', return_value=None):
                from connectonion.cli.main import cli
                result = self.runner.invoke(cli, ['auth', 'microsoft'])

            mock_requests.delete.assert_called_once()
            mock_webbrowser.open.assert_called_once()

            env_content = Path('.env').read_text()
            assert 'MICROSOFT_ACCESS_TOKEN=eyJ0eXAi.test' in env_content
            assert 'MICROSOFT_REFRESH_TOKEN=0.ATcA.test' in env_content
            assert 'MICROSOFT_EMAIL=test@outlook.com' in env_content

    @patch('connectonion.cli.commands.auth_commands.requests')
    def test_auth_microsoft_init_failure(self, mock_requests):
        """Test handling of OAuth init failure."""
        with self.runner.isolated_filesystem():
            Path('.env').write_text('OPENONION_API_KEY=test-key\n')

            mock_revoke_response = Mock()
            mock_revoke_response.status_code = 404
            mock_requests.delete.return_value = mock_revoke_response

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

            mock_revoke_response = Mock()
            mock_revoke_response.status_code = 404
            mock_requests.delete.return_value = mock_revoke_response

            mock_init_response = Mock()
            mock_init_response.status_code = 200
            mock_init_response.json.return_value = {
                'auth_url': 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?...'
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


@pytest.mark.cli
@pytest.mark.skip(reason="Integration test requires manual OAuth flow")
class TestAuthMicrosoftIntegration:
    """Integration tests for co auth microsoft (requires installation)."""

    def test_auth_microsoft_command_exists(self):
        """Test that 'co auth microsoft' command is recognized."""
        import subprocess

        result = subprocess.run(
            ['co', 'auth', '--help'],
            capture_output=True,
            text=True,
            timeout=5
        )

        assert 'microsoft' in result.stdout.lower() or 'microsoft' in result.stderr.lower()
