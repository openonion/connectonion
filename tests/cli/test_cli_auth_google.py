"""Tests for co auth google CLI command."""

import os
import tempfile
from pathlib import Path
import pytest
from unittest.mock import Mock, patch, MagicMock

from .argparse_runner import ArgparseCliRunner


class TestAuthGoogleHelp:
    """Test help text for co auth google command."""

    def setup_method(self):
        """Setup test environment."""
        self.runner = ArgparseCliRunner()

    def test_auth_help_shows_google_option(self):
        """Test that co auth --help mentions google service."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['auth', '--help'])
        assert result.exit_code == 0
        assert 'google' in result.output.lower()
        assert 'gmail' in result.output.lower() or 'calendar' in result.output.lower()

    @patch('connectonion.cli.commands.auth_commands._load_api_key')
    def test_auth_google_requires_openonion_auth(self, mock_load_key):
        """Test that co auth google requires prior OpenOnion authentication."""
        # Mock _load_api_key to return None (no API key found)
        mock_load_key.return_value = None

        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # co auth google should fail without OPENONION_API_KEY
            result = self.runner.invoke(cli, ['auth', 'google'])
            assert 'Not authenticated with OpenOnion' in result.output


class TestLoadApiKey:
    """Test the _load_api_key helper function."""

    def test_load_api_key_from_env_var(self):
        """Test loading API key from environment variable."""
        from connectonion.cli.commands.auth_commands import _load_api_key

        with patch.dict(os.environ, {'OPENONION_API_KEY': 'test-key-123'}):
            key = _load_api_key()
            assert key == 'test-key-123'

    def test_load_api_key_from_local_env(self):
        """Test loading API key from local .env file."""
        from connectonion.cli.commands.auth_commands import _load_api_key

        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)

            # Create .env with API key
            Path('.env').write_text('OPENONION_API_KEY=local-key-456\n')

            # Clear environment variable
            with patch.dict(os.environ, {}, clear=True):
                key = _load_api_key()
                assert key == 'local-key-456'

    def test_load_api_key_from_global_keys_env(self):
        """Test loading API key from global ~/.co/keys.env."""
        from connectonion.cli.commands.auth_commands import _load_api_key

        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)

            # Create mock ~/.co/keys.env
            co_dir = Path(tmpdir) / '.co'
            co_dir.mkdir()
            keys_env = co_dir / 'keys.env'
            keys_env.write_text('OPENONION_API_KEY=global-key-789\n')

            # Mock Path.home() to return tmpdir
            with patch('pathlib.Path.home', return_value=Path(tmpdir)):
                with patch.dict(os.environ, {}, clear=True):
                    key = _load_api_key()
                    assert key == 'global-key-789'

    def test_load_api_key_returns_none_when_not_found(self):
        """Test that _load_api_key returns None when no key found."""
        from connectonion.cli.commands.auth_commands import _load_api_key

        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)

            # Mock Path.home() to return tmpdir (no keys.env)
            with patch('pathlib.Path.home', return_value=Path(tmpdir)):
                with patch.dict(os.environ, {}, clear=True):
                    key = _load_api_key()
                    assert key is None


class TestSaveGoogleToEnv:
    """Test the _save_google_to_env helper function."""

    def test_save_google_credentials_to_new_env(self):
        """Test saving Google credentials to a new .env file."""
        from connectonion.cli.commands.auth_commands import _save_google_to_env

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / '.env'

            credentials = {
                'access_token': 'ya29.test123',
                'refresh_token': '1//0gtest456',
                'expires_at': '2025-12-31T23:59:59',
                'scopes': 'gmail.send,calendar.readonly',
                'google_email': 'test@gmail.com'
            }

            _save_google_to_env(env_file, credentials)

            # Verify file was created
            assert env_file.exists()

            # Verify content
            content = env_file.read_text()
            assert 'GOOGLE_ACCESS_TOKEN=ya29.test123' in content
            assert 'GOOGLE_REFRESH_TOKEN=1//0gtest456' in content
            assert 'GOOGLE_TOKEN_EXPIRES_AT=2025-12-31T23:59:59' in content
            assert 'GOOGLE_SCOPES=gmail.send,calendar.readonly' in content
            assert 'GOOGLE_EMAIL=test@gmail.com' in content

    def test_save_google_credentials_updates_existing_env(self):
        """Test that saving Google credentials updates existing .env."""
        from connectonion.cli.commands.auth_commands import _save_google_to_env

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / '.env'

            # Create existing .env with old Google credentials
            env_file.write_text('''OPENONION_API_KEY=existing-key
GOOGLE_ACCESS_TOKEN=old-token
GOOGLE_REFRESH_TOKEN=old-refresh
GOOGLE_EMAIL=old@gmail.com
OTHER_VAR=keep-this
''')

            credentials = {
                'access_token': 'new-token',
                'refresh_token': 'new-refresh',
                'expires_at': '2025-12-31T23:59:59',
                'scopes': 'gmail.send',
                'google_email': 'new@gmail.com'
            }

            _save_google_to_env(env_file, credentials)

            content = env_file.read_text()

            # Should preserve non-Google variables
            assert 'OPENONION_API_KEY=existing-key' in content
            assert 'OTHER_VAR=keep-this' in content

            # Should update Google credentials
            assert 'GOOGLE_ACCESS_TOKEN=new-token' in content
            assert 'GOOGLE_REFRESH_TOKEN=new-refresh' in content
            assert 'GOOGLE_EMAIL=new@gmail.com' in content

            # Should not contain old Google credentials
            assert 'old-token' not in content
            assert 'old-refresh' not in content

    def test_save_google_credentials_file_permissions(self):
        """Test that .env file has restrictive permissions on Unix."""
        from connectonion.cli.commands.auth_commands import _save_google_to_env
        import sys

        if sys.platform == 'win32':
            pytest.skip("File permissions test not applicable on Windows")

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / '.env'

            credentials = {
                'access_token': 'test',
                'refresh_token': 'test',
                'expires_at': '2025-12-31T23:59:59',
                'scopes': 'gmail.send',
                'google_email': 'test@gmail.com'
            }

            _save_google_to_env(env_file, credentials)

            # Check file permissions (should be 0o600 = rw-------)
            stat = env_file.stat()
            assert oct(stat.st_mode)[-3:] == '600'


class TestAuthGoogleFlow:
    """Test the co auth google flow with mocked backend."""

    def setup_method(self):
        """Setup test environment."""
        self.runner = ArgparseCliRunner()

    @patch('connectonion.cli.commands.auth_commands.webbrowser')
    @patch('connectonion.cli.commands.auth_commands.requests')
    def test_auth_google_success_flow(self, mock_requests, mock_webbrowser):
        """Test successful Google OAuth flow."""
        with self.runner.isolated_filesystem():
            # Setup: Create .env with API key
            Path('.env').write_text('OPENONION_API_KEY=test-key\n')

            # Mock API responses
            mock_init_response = Mock()
            mock_init_response.status_code = 200
            mock_init_response.json.return_value = {
                'auth_url': 'https://accounts.google.com/o/oauth2/v2/auth?...'
            }

            mock_status_response = Mock()
            mock_status_response.status_code = 200
            mock_status_response.json.return_value = {'connected': True}

            mock_creds_response = Mock()
            mock_creds_response.status_code = 200
            mock_creds_response.json.return_value = {
                'access_token': 'ya29.test',
                'refresh_token': '1//0g.test',
                'expires_at': '2025-12-31T23:59:59',
                'scopes': 'gmail.send,calendar.readonly',
                'google_email': 'test@gmail.com'
            }

            # Setup mock to return different responses
            mock_requests.get.side_effect = [
                mock_init_response,  # /google/init
                mock_status_response,  # /google/status
                mock_creds_response  # /google/credentials
            ]

            # Mock webbrowser.open to not actually open browser
            mock_webbrowser.open.return_value = True

            # Mock time.sleep to speed up test
            with patch('time.sleep', return_value=None):
                from connectonion.cli.main import cli
                result = self.runner.invoke(cli, ['auth', 'google'])

            # Verify browser was opened
            mock_webbrowser.open.assert_called_once()

            # Verify credentials were saved to .env
            env_content = Path('.env').read_text()
            assert 'GOOGLE_ACCESS_TOKEN=ya29.test' in env_content
            assert 'GOOGLE_REFRESH_TOKEN=1//0g.test' in env_content
            assert 'GOOGLE_EMAIL=test@gmail.com' in env_content

    @patch('connectonion.cli.commands.auth_commands.requests')
    def test_auth_google_init_failure(self, mock_requests):
        """Test handling of OAuth init failure."""
        with self.runner.isolated_filesystem():
            # Setup: Create .env with API key
            Path('.env').write_text('OPENONION_API_KEY=test-key\n')

            # Mock failed init response
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = 'Internal Server Error'
            mock_requests.get.return_value = mock_response

            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['auth', 'google'])

            # Should show error message
            assert 'Failed to initialize OAuth' in result.output or result.exit_code != 0

    @patch('connectonion.cli.commands.auth_commands.webbrowser')
    @patch('connectonion.cli.commands.auth_commands.requests')
    @patch('time.sleep')
    def test_auth_google_timeout(self, mock_sleep, mock_requests, mock_webbrowser):
        """Test handling of authorization timeout."""
        with self.runner.isolated_filesystem():
            # Setup: Create .env with API key
            Path('.env').write_text('OPENONION_API_KEY=test-key\n')

            # Mock init response
            mock_init_response = Mock()
            mock_init_response.status_code = 200
            mock_init_response.json.return_value = {
                'auth_url': 'https://accounts.google.com/o/oauth2/v2/auth?...'
            }

            # Mock status always returns not connected
            mock_status_response = Mock()
            mock_status_response.status_code = 200
            mock_status_response.json.return_value = {'connected': False}

            mock_requests.get.side_effect = [
                mock_init_response,
                *[mock_status_response] * 60  # Never becomes connected
            ]

            from connectonion.cli.main import cli
            result = self.runner.invoke(cli, ['auth', 'google'])

            # Should timeout and show error
            assert 'timed out' in result.output.lower() or result.exit_code != 0


@pytest.mark.cli
@pytest.mark.skip(reason="Integration test requires manual OAuth flow")
class TestAuthGoogleIntegration:
    """Integration tests for co auth google (requires installation)."""

    def test_auth_google_command_exists(self):
        """Test that 'co auth google' command is recognized."""
        import subprocess

        # Just check that the command is recognized (won't work without API key)
        result = subprocess.run(
            ['co', 'auth', '--help'],
            capture_output=True,
            text=True,
            timeout=5
        )

        # Command should show google as an option
        assert 'google' in result.stdout.lower() or 'google' in result.stderr.lower()
