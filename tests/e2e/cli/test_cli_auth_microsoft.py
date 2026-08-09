"""Tests for co auth microsoft CLI command."""

"""
LLM-Note: Tests for Microsoft OAuth CLI authentication flow

What it tests:
- TestAuthMicrosoftHelp: Help text and prerequisites
  - test_auth_help_shows_microsoft_option: Verify microsoft appears in help
  - test_auth_microsoft_requires_openonion_auth: Verify OpenOnion auth required first
- TestSaveMicrosoftToEnv: Credential persistence
  - test_save_microsoft_credentials_to_new_env: Create new .env with credentials
  - test_save_microsoft_credentials_updates_existing_env: Update existing .env preserving other vars
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
import base64
import json
import threading
import requests
from pathlib import Path
import pytest
from unittest.mock import Mock, patch
from nacl.encoding import HexEncoder
from nacl.public import PublicKey, SealedBox

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

    def test_tampered_handoff_cannot_be_saved(self):
        from nacl.public import PrivateKey
        from connectonion.cli.commands.auth_commands import (
            _decrypt_microsoft_handoff,
        )

        with pytest.raises(ValueError, match="could not be decrypted"):
            _decrypt_microsoft_handoff(
                PrivateKey.generate(),
                base64.urlsafe_b64encode(b"not-a-sealed-box").decode(),
            )

    def test_loopback_callback_accepts_only_matching_state(self):
        from connectonion.cli.commands.auth_commands import (
            _microsoft_callback_server,
        )

        server, callback_url, expected_state, result = (
            _microsoft_callback_server()
        )
        expected_state["value"] = "expected"
        try:
            for state, expected_status in (("wrong", 400), ("expected", 200)):
                worker = threading.Thread(target=server.handle_request)
                worker.start()
                response = requests.get(
                    callback_url,
                    params={"state": state, "ciphertext": "sealed"},
                    timeout=2,
                )
                worker.join(timeout=2)
                assert response.status_code == expected_status
            assert result == {"ciphertext": "sealed"}
        finally:
            server.server_close()


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

            mock_init_response = Mock()
            mock_init_response.status_code = 200
            mock_init_response.json.return_value = {
                'auth_url': 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=state-1'
            }

            credentials = {
                'access_token': 'eyJ0eXAi.test',
                'refresh_token': '0.ATcA.test',
                'expires_at': '2025-12-31T23:59:59',
                'scopes': 'Mail.ReadWrite,Mail.Send,Contacts.ReadWrite,Calendars.Read,Calendars.ReadWrite',
                'microsoft_email': 'test@outlook.com'
            }
            callback_result = {}
            expected_state = {'value': None}
            fake_server = Mock()

            def handle_request():
                callback_result['ciphertext'] = fake_server.ciphertext

            fake_server.handle_request.side_effect = handle_request

            def get(url, **kwargs):
                if url.endswith('/microsoft/init'):
                    public_key = PublicKey(
                        kwargs['params']['handoff_public_key'].encode('ascii'),
                        encoder=HexEncoder,
                    )
                    sealed = SealedBox(public_key).encrypt(
                        json.dumps(credentials).encode()
                    )
                    fake_server.ciphertext = base64.urlsafe_b64encode(sealed).decode()
                    assert kwargs['params']['handoff_url'].startswith(
                        'http://127.0.0.1:'
                    )
                    return mock_init_response
                raise AssertionError(f"Unexpected backend request: {url}")

            mock_requests.get.side_effect = get

            mock_webbrowser.open.return_value = True

            callback = (
                fake_server,
                'http://127.0.0.1:54321/callback',
                expected_state,
                callback_result,
            )
            with patch(
                'connectonion.cli.commands.auth_commands._microsoft_callback_server',
                return_value=callback,
            ):
                from connectonion.cli.main import cli
                self.runner.invoke(cli, ['auth', 'microsoft'])

            mock_requests.delete.assert_not_called()
            mock_webbrowser.open.assert_called_once()

            env_content = Path('.env').read_text()
            assert 'MICROSOFT_ACCESS_TOKEN=eyJ0eXAi.test' in env_content
            assert 'MICROSOFT_REFRESH_TOKEN=0.ATcA.test' in env_content
            assert 'Contacts.ReadWrite' in env_content
            assert 'MICROSOFT_EMAIL=test@outlook.com' in env_content

    @patch('connectonion.cli.commands.auth_commands.requests')
    def test_auth_microsoft_init_failure(self, mock_requests):
        """Test handling of OAuth init failure."""
        with self.runner.isolated_filesystem():
            Path('.env').write_text('OPENONION_API_KEY=test-key\n')

            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = 'Internal Server Error'
            mock_requests.get.return_value = mock_response

            callback = (Mock(), 'http://127.0.0.1:54321/callback', {'value': None}, {})
            with patch(
                'connectonion.cli.commands.auth_commands._microsoft_callback_server',
                return_value=callback,
            ):
                from connectonion.cli.main import cli
                result = self.runner.invoke(cli, ['auth', 'microsoft'])

            assert 'Failed to initialize OAuth' in result.output or result.exit_code != 0

    @patch('connectonion.cli.commands.auth_commands.webbrowser')
    @patch('connectonion.cli.commands.auth_commands.requests')
    def test_auth_microsoft_timeout(self, mock_requests, mock_webbrowser):
        """Test handling of authorization timeout."""
        with self.runner.isolated_filesystem():
            Path('.env').write_text('OPENONION_API_KEY=test-key\n')

            mock_init_response = Mock()
            mock_init_response.status_code = 200
            mock_init_response.json.return_value = {
                'auth_url': 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=state-timeout'
            }

            mock_requests.get.return_value = mock_init_response
            callback = (Mock(), 'http://127.0.0.1:54321/callback', {'value': None}, {})
            with (
                patch(
                    'connectonion.cli.commands.auth_commands._microsoft_callback_server',
                    return_value=callback,
                ),
                patch(
                    'connectonion.cli.commands.auth_commands.monotonic',
                    side_effect=[0, 301, 301],
                ),
            ):
                from connectonion.cli.main import cli
                result = self.runner.invoke(cli, ['auth', 'microsoft'])

            assert 'timed out' in result.output.lower() or result.exit_code != 0
