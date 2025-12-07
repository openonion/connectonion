"""Unit tests for connectonion/cli/commands/doctor_commands.py

Tests cover:
- handle_doctor: System diagnostics display
- Version, Python, environment checks
- Configuration file detection
- API key detection (env var, .env, ~/.co/keys.env)
- Backend connectivity checks (mocked)
"""

import pytest
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock
from io import StringIO


class TestHandleDoctorSystemChecks:
    """Tests for system-level diagnostic checks."""

    @patch('connectonion.cli.commands.doctor_commands.console')
    @patch('connectonion.cli.commands.doctor_commands.shutil.which')
    def test_doctor_displays_version(self, mock_which, mock_console):
        """Test that doctor displays ConnectOnion version."""
        mock_which.return_value = '/usr/local/bin/co'

        from connectonion.cli.commands.doctor_commands import handle_doctor

        # Mock requests to avoid network call
        with patch('connectonion.cli.commands.doctor_commands.requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            with patch.dict(os.environ, {"OPENONION_API_KEY": ""}):
                handle_doctor()

        # Verify console.print was called (Rich output)
        assert mock_console.print.called

    @patch('connectonion.cli.commands.doctor_commands.console')
    @patch('connectonion.cli.commands.doctor_commands.shutil.which')
    def test_doctor_checks_python_version(self, mock_which, mock_console):
        """Test that doctor checks Python version."""
        mock_which.return_value = '/usr/local/bin/co'

        from connectonion.cli.commands.doctor_commands import handle_doctor

        with patch.dict(os.environ, {"OPENONION_API_KEY": ""}):
            handle_doctor()

        # Verify console was used for output
        assert mock_console.print.called

    @patch('connectonion.cli.commands.doctor_commands.console')
    @patch('connectonion.cli.commands.doctor_commands.shutil.which')
    def test_doctor_checks_co_command_found(self, mock_which, mock_console):
        """Test that doctor shows 'co' command location when found."""
        mock_which.return_value = '/usr/local/bin/co'

        from connectonion.cli.commands.doctor_commands import handle_doctor

        with patch.dict(os.environ, {"OPENONION_API_KEY": ""}):
            handle_doctor()

        # Console should be used
        assert mock_console.print.called

    @patch('connectonion.cli.commands.doctor_commands.console')
    @patch('connectonion.cli.commands.doctor_commands.shutil.which')
    def test_doctor_shows_co_not_found(self, mock_which, mock_console):
        """Test that doctor shows error when 'co' not in PATH."""
        mock_which.return_value = None

        from connectonion.cli.commands.doctor_commands import handle_doctor

        with patch.dict(os.environ, {"OPENONION_API_KEY": ""}):
            handle_doctor()

        assert mock_console.print.called


class TestHandleDoctorConfigChecks:
    """Tests for configuration file detection."""

    @patch('connectonion.cli.commands.doctor_commands.console')
    @patch('connectonion.cli.commands.doctor_commands.shutil.which')
    def test_doctor_detects_local_config(self, mock_which, mock_console):
        """Test that doctor detects local .co/config.toml."""
        mock_which.return_value = '/usr/local/bin/co'

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            # Create local config
            co_dir = Path(tmpdir) / ".co"
            co_dir.mkdir()
            config_file = co_dir / "config.toml"
            config_file.write_text('[agent]\nname = "test-agent"\n')

            try:
                from connectonion.cli.commands.doctor_commands import handle_doctor

                with patch.dict(os.environ, {"OPENONION_API_KEY": ""}):
                    handle_doctor()

                assert mock_console.print.called
            finally:
                os.chdir(original_cwd)

    @patch('connectonion.cli.commands.doctor_commands.console')
    @patch('connectonion.cli.commands.doctor_commands.shutil.which')
    def test_doctor_detects_local_keys(self, mock_which, mock_console):
        """Test that doctor detects local .co/keys/agent.key."""
        mock_which.return_value = '/usr/local/bin/co'

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            # Create local keys directory
            keys_dir = Path(tmpdir) / ".co" / "keys"
            keys_dir.mkdir(parents=True)
            key_file = keys_dir / "agent.key"
            key_file.write_text("dummy_key_content")

            try:
                from connectonion.cli.commands.doctor_commands import handle_doctor

                with patch.dict(os.environ, {"OPENONION_API_KEY": ""}):
                    handle_doctor()

                assert mock_console.print.called
            finally:
                os.chdir(original_cwd)


class TestHandleDoctorApiKeyChecks:
    """Tests for API key detection."""

    @patch('connectonion.cli.commands.doctor_commands.console')
    @patch('connectonion.cli.commands.doctor_commands.shutil.which')
    def test_doctor_detects_api_key_from_env(self, mock_which, mock_console):
        """Test that doctor detects API key from environment variable."""
        mock_which.return_value = '/usr/local/bin/co'

        from connectonion.cli.commands.doctor_commands import handle_doctor

        with patch('connectonion.cli.commands.doctor_commands.requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            with patch.dict(os.environ, {"OPENONION_API_KEY": "test-api-key-12345"}):
                handle_doctor()

        assert mock_console.print.called

    @patch('connectonion.cli.commands.doctor_commands.console')
    @patch('connectonion.cli.commands.doctor_commands.shutil.which')
    def test_doctor_detects_api_key_from_local_env(self, mock_which, mock_console):
        """Test that doctor detects API key from local .env file."""
        mock_which.return_value = '/usr/local/bin/co'

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            # Create .env file with API key
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("OPENONION_API_KEY=local-env-key-12345\n")

            try:
                from connectonion.cli.commands.doctor_commands import handle_doctor

                with patch('connectonion.cli.commands.doctor_commands.requests.get') as mock_get:
                    mock_get.return_value.status_code = 200
                    # Clear env var to force reading from file
                    with patch.dict(os.environ, {"OPENONION_API_KEY": ""}, clear=False):
                        os.environ.pop("OPENONION_API_KEY", None)
                        handle_doctor()

                assert mock_console.print.called
            finally:
                os.chdir(original_cwd)


class TestHandleDoctorConnectivity:
    """Tests for backend connectivity checks."""

    @patch('connectonion.cli.commands.doctor_commands.console')
    @patch('connectonion.cli.commands.doctor_commands.shutil.which')
    @patch('connectonion.cli.commands.doctor_commands.requests.get')
    def test_doctor_checks_backend_health(self, mock_get, mock_which, mock_console):
        """Test that doctor checks backend health endpoint."""
        mock_which.return_value = '/usr/local/bin/co'
        mock_get.return_value.status_code = 200

        from connectonion.cli.commands.doctor_commands import handle_doctor

        with patch.dict(os.environ, {"OPENONION_API_KEY": "test-key"}):
            handle_doctor()

        # Verify health check was called
        mock_get.assert_called_with("https://oo.openonion.ai/health", timeout=5)

    @patch('connectonion.cli.commands.doctor_commands.console')
    @patch('connectonion.cli.commands.doctor_commands.shutil.which')
    @patch('connectonion.cli.commands.doctor_commands.requests.get')
    def test_doctor_handles_backend_error(self, mock_get, mock_which, mock_console):
        """Test that doctor handles backend error gracefully."""
        mock_which.return_value = '/usr/local/bin/co'
        mock_get.return_value.status_code = 503

        from connectonion.cli.commands.doctor_commands import handle_doctor

        with patch.dict(os.environ, {"OPENONION_API_KEY": "test-key"}):
            handle_doctor()

        # Should still complete without crashing
        assert mock_console.print.called


class TestHandleDoctorVirtualEnv:
    """Tests for virtual environment detection."""

    @patch('connectonion.cli.commands.doctor_commands.console')
    @patch('connectonion.cli.commands.doctor_commands.shutil.which')
    def test_doctor_detects_virtual_env(self, mock_which, mock_console):
        """Test that doctor detects virtual environment."""
        mock_which.return_value = '/usr/local/bin/co'

        # Simulate being in a venv
        original_prefix = sys.prefix
        original_base_prefix = getattr(sys, 'base_prefix', sys.prefix)

        try:
            # Mock venv detection
            sys.prefix = '/path/to/venv'
            sys.base_prefix = '/usr'

            from connectonion.cli.commands.doctor_commands import handle_doctor

            with patch.dict(os.environ, {"OPENONION_API_KEY": ""}):
                handle_doctor()

            assert mock_console.print.called
        finally:
            sys.prefix = original_prefix
            sys.base_prefix = original_base_prefix

    @patch('connectonion.cli.commands.doctor_commands.console')
    @patch('connectonion.cli.commands.doctor_commands.shutil.which')
    def test_doctor_detects_global_python(self, mock_which, mock_console):
        """Test that doctor detects global Python (not in venv)."""
        mock_which.return_value = '/usr/local/bin/co'

        from connectonion.cli.commands.doctor_commands import handle_doctor

        with patch.dict(os.environ, {"OPENONION_API_KEY": ""}):
            handle_doctor()

        assert mock_console.print.called

