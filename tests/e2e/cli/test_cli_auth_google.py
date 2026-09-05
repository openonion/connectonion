"""Tests for co auth google CLI command."""

"""
LLM-Note: Tests for Google OAuth CLI authentication flow

What it tests:
- TestAuthGoogleHelp: Help text and prerequisites
  - test_auth_help_shows_google_option: Verify google appears in help
  - test_auth_google_requires_openonion_auth: Verify OpenOnion auth required first
- TestLoadApiKey: API key loading from multiple sources
  - test_load_api_key_from_env_var: Load from OPENONION_API_KEY env var
  - test_load_api_key_from_local_env: Load from local .env file
  - test_load_api_key_from_global_keys_env: Load from ~/.co/keys.env
  - test_load_api_key_returns_none_when_not_found: Fallback when not found
- TestSaveGoogleToEnv: Credential persistence
  - test_save_google_credentials_to_new_env: Create new .env with credentials
  - test_save_google_credentials_updates_existing_env: Update existing .env preserving other vars
  - test_save_google_credentials_file_permissions: Verify 0600 permissions on Unix
- TestAuthGoogleFlow: OAuth flow with mocked backend
  - test_auth_google_success_flow: Complete successful OAuth flow
  - test_auth_google_init_failure: Handle OAuth init errors
  - test_auth_google_timeout: Handle authorization timeout
- TestAuthGoogleIntegration: Manual integration tests (skipped)

Components under test:
- connectonion.cli.commands.auth_commands (auth google command)
- connectonion.cli.commands.project_cmd_lib.load_api_key
- connectonion.cli.commands.auth_commands._save_google_to_env
"""

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

    @patch('connectonion.cli.commands.google_auth.load_api_key')
    def test_auth_google_requires_openonion_auth(self, mock_load_key):
        """Test that co auth google requires prior OpenOnion authentication."""
        # Mock _load_api_key to return None (no API key found)
        mock_load_key.return_value = None

        with self.runner.isolated_filesystem():
            from connectonion.cli.main import cli

            # co auth google should fail without OPENONION_API_KEY
            result = self.runner.invoke(cli, ['auth', 'google'])
            assert 'OpenOnion account not connected' in result.output


class TestLoadApiKey:
    """Test the _load_api_key helper function."""

    def test_load_api_key_from_env_var(self):
        """Test loading API key from environment variable."""
        from connectonion.cli.commands.project_cmd_lib import load_api_key

        with patch.dict(os.environ, {'OPENONION_API_KEY': 'test-key-123'}):
            key = load_api_key()
            assert key == 'test-key-123'

    def test_load_api_key_from_local_env(self, tmp_path, monkeypatch):
        """Test loading API key from local .env file."""
        from connectonion.cli.commands.project_cmd_lib import load_api_key

        monkeypatch.chdir(tmp_path)

        # Create .env with API key
        Path('.env').write_text('OPENONION_API_KEY=local-key-456\n')

        # Clear environment variable
        with patch.dict(os.environ, {}, clear=True):
            key = load_api_key()
            assert key == 'local-key-456'

    def test_load_api_key_from_global_keys_env(self, tmp_path, monkeypatch):
        """Test loading API key from global ~/.co/keys.env."""
        from connectonion.cli.commands.project_cmd_lib import load_api_key

        monkeypatch.chdir(tmp_path)

        # Create mock ~/.co/keys.env
        co_dir = tmp_path / '.co'
        co_dir.mkdir()
        keys_env = co_dir / 'keys.env'
        keys_env.write_text('OPENONION_API_KEY=global-key-789\n')

        # Mock Path.home() to return the isolated home.
        with patch('pathlib.Path.home', return_value=tmp_path):
            with patch.dict(os.environ, {}, clear=True):
                key = load_api_key()
                assert key == 'global-key-789'

    def test_load_api_key_returns_none_when_not_found(self, tmp_path, monkeypatch):
        """Test that _load_api_key returns None when no key found."""
        from connectonion.cli.commands.project_cmd_lib import load_api_key

        monkeypatch.chdir(tmp_path)

        # Mock Path.home() to return the isolated home (no keys.env).
        with patch('pathlib.Path.home', return_value=tmp_path):
            with patch.dict(os.environ, {}, clear=True):
                key = load_api_key()
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



# The remote polling flow is retired. Encrypted CLI handoff, denial, and
# provider failure regressions are covered in tests/unit/test_google_local_auth.py.
