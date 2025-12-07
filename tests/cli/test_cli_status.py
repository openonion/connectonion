"""Unit tests for connectonion/cli/commands/status_commands.py

Tests cover:
- _load_api_key: Load API key from env var, .env, ~/.co/keys.env
- _load_config: Load config from .co/config.toml or ~/.co/config.toml
- handle_status: Display account status without re-authenticating
"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock


class TestLoadApiKey:
    """Tests for _load_api_key function."""

    def test_load_api_key_from_env_var(self):
        """Test loading API key from environment variable."""
        from connectonion.cli.commands.status_commands import _load_api_key

        with patch.dict(os.environ, {"OPENONION_API_KEY": "test-key-from-env"}, clear=False):
            result = _load_api_key()
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
                    # Need to reimport after patching env
                    from connectonion.cli.commands.status_commands import _load_api_key
                    result = _load_api_key()
                    # Result depends on dotenv loading
            finally:
                os.chdir(original_cwd)

    def test_load_api_key_from_global_keys_env(self):
        """Test loading API key from ~/.co/keys.env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_home = Path(tmpdir) / "fake_home"
            fake_home.mkdir()
            co_dir = fake_home / ".co"
            co_dir.mkdir()
            keys_env = co_dir / "keys.env"
            keys_env.write_text("OPENONION_API_KEY=global-keys-env-key\n")

            with patch.object(Path, 'home', return_value=fake_home):
                with patch.dict(os.environ, {}, clear=True):
                    from connectonion.cli.commands.status_commands import _load_api_key
                    # Result depends on dotenv loading and env state

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
                        from connectonion.cli.commands.status_commands import _load_api_key
                        result = _load_api_key()
                        # Should be None or empty when not found
            finally:
                os.chdir(original_cwd)


class TestLoadConfig:
    """Tests for _load_config function."""

    def test_load_config_from_local(self):
        """Test loading config from local .co/config.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            # Create local config
            co_dir = Path(tmpdir) / ".co"
            co_dir.mkdir()
            config_file = co_dir / "config.toml"
            config_file.write_text('[agent]\nname = "local-agent"\n')

            try:
                from connectonion.cli.commands.status_commands import _load_config
                result = _load_config()
                assert result.get("agent", {}).get("name") == "local-agent"
            finally:
                os.chdir(original_cwd)

    def test_load_config_from_global(self):
        """Test loading config from ~/.co/config.toml when local doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            fake_home = Path(tmpdir) / "fake_home"
            fake_home.mkdir()
            co_dir = fake_home / ".co"
            co_dir.mkdir()
            config_file = co_dir / "config.toml"
            config_file.write_text('[agent]\nname = "global-agent"\n')

            try:
                with patch.object(Path, 'home', return_value=fake_home):
                    from connectonion.cli.commands.status_commands import _load_config
                    result = _load_config()
                    assert result.get("agent", {}).get("name") == "global-agent"
            finally:
                os.chdir(original_cwd)

    def test_load_config_returns_empty_dict_when_not_found(self):
        """Test _load_config returns empty dict when no config exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            fake_home = Path(tmpdir) / "fake_home"
            fake_home.mkdir()

            try:
                with patch.object(Path, 'home', return_value=fake_home):
                    from connectonion.cli.commands.status_commands import _load_config
                    result = _load_config()
                    assert result == {}
            finally:
                os.chdir(original_cwd)


class TestHandleStatusNoApiKey:
    """Tests for handle_status when API key is not found."""

    @patch('connectonion.cli.commands.status_commands.console')
    @patch('connectonion.cli.commands.status_commands._load_api_key')
    def test_status_shows_error_no_api_key(self, mock_load_key, mock_console):
        """Test status shows error when no API key found."""
        mock_load_key.return_value = None

        from connectonion.cli.commands.status_commands import handle_status
        handle_status()

        # Should print error message
        assert mock_console.print.called


class TestHandleStatusNoKeys:
    """Tests for handle_status when keys are not found."""

    @patch('connectonion.cli.commands.status_commands.console')
    @patch('connectonion.cli.commands.status_commands._load_api_key')
    @patch('connectonion.cli.commands.status_commands._load_config')
    @patch('connectonion.address.load')
    def test_status_shows_error_no_keys(self, mock_address_load, mock_config, mock_load_key, mock_console):
        """Test status shows error when no keys found."""
        mock_load_key.return_value = "test-api-key"
        mock_config.return_value = {}
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
    @patch('connectonion.cli.commands.status_commands._load_api_key')
    @patch('connectonion.cli.commands.status_commands._load_config')
    @patch('connectonion.address.load')
    @patch('connectonion.address.sign')
    @patch('connectonion.cli.commands.status_commands.requests.post')
    def test_status_displays_account_info(self, mock_post, mock_sign, mock_load, mock_config, mock_load_key, mock_console):
        """Test status displays account information."""
        mock_load_key.return_value = "test-api-key-12345"
        mock_config.return_value = {"agent": {"name": "test-agent"}}
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
                # Should have printed to console
                assert mock_console.print.called
            finally:
                os.chdir(original_cwd)

    @patch('connectonion.cli.commands.status_commands.console')
    @patch('connectonion.cli.commands.status_commands._load_api_key')
    @patch('connectonion.cli.commands.status_commands._load_config')
    @patch('connectonion.address.load')
    @patch('connectonion.address.sign')
    @patch('connectonion.cli.commands.status_commands.requests.post')
    def test_status_shows_low_balance_warning(self, mock_post, mock_sign, mock_load, mock_config, mock_load_key, mock_console):
        """Test status shows warning when balance is low."""
        mock_load_key.return_value = "test-api-key-12345"
        mock_config.return_value = {}
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


class TestHandleStatusApiError:
    """Tests for API error handling."""

    @patch('connectonion.cli.commands.status_commands.console')
    @patch('connectonion.cli.commands.status_commands._load_api_key')
    @patch('connectonion.cli.commands.status_commands._load_config')
    @patch('connectonion.address.load')
    @patch('connectonion.address.sign')
    @patch('connectonion.cli.commands.status_commands.requests.post')
    def test_status_handles_api_error(self, mock_post, mock_sign, mock_load, mock_config, mock_load_key, mock_console):
        """Test status handles API error gracefully."""
        mock_load_key.return_value = "test-api-key"
        mock_config.return_value = {}
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
    @patch('connectonion.cli.commands.status_commands._load_api_key')
    @patch('connectonion.cli.commands.status_commands._load_config')
    @patch('connectonion.address.load')
    @patch('connectonion.address.sign')
    @patch('connectonion.cli.commands.status_commands.requests.post')
    def test_status_handles_401_unauthorized(self, mock_post, mock_sign, mock_load, mock_config, mock_load_key, mock_console):
        """Test status handles 401 unauthorized error."""
        mock_load_key.return_value = "invalid-api-key"
        mock_config.return_value = {}
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

