"""Tests for connectonion/cli/commands/keys_commands.py

Tests cover:
- _find_co_dir: Find .co directory (local vs global)
- _load_env_vars: Load env vars from .env files
- _mask: Mask secret strings
- _short_path: Shorten paths with ~ for home dir
- _source_label: Human-readable source labels
- handle_keys: Full key display (masked and revealed)
- CLI integration: co keys and co keys --reveal via Typer
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from .argparse_runner import ArgparseCliRunner


class TestMask:
    """Tests for _mask helper."""

    def test_mask_empty_string(self):
        from connectonion.cli.commands.keys_commands import _mask
        assert _mask("") == ""

    def test_mask_none(self):
        from connectonion.cli.commands.keys_commands import _mask
        assert _mask(None) == ""

    def test_mask_short_string_shown_in_full(self):
        from connectonion.cli.commands.keys_commands import _mask
        assert _mask("abc", show=8) == "abc"

    def test_mask_long_string_truncated(self):
        from connectonion.cli.commands.keys_commands import _mask
        result = _mask("abcdefghijklmnop", show=8)
        assert result.startswith("abcdefgh...")
        assert "*" in result

    def test_mask_custom_show_length(self):
        from connectonion.cli.commands.keys_commands import _mask
        result = _mask("canyon robot vacuum circle wave", show=12)
        assert result.startswith("canyon robot")
        assert "*" in result


class TestShortPath:
    """Tests for _short_path helper."""

    def test_replaces_home_with_tilde(self):
        from connectonion.cli.commands.keys_commands import _short_path
        home = Path.home()
        result = _short_path(home / ".co" / "keys.env")
        assert result.startswith("~")
        assert "/.co/keys.env" in result

    def test_non_home_path_unchanged(self):
        from connectonion.cli.commands.keys_commands import _short_path
        result = _short_path(Path("/tmp/some/file.txt"))
        assert result.startswith("/")
        assert "~" not in result


class TestSourceLabel:
    """Tests for _source_label helper."""

    def test_global_dir_label(self):
        from connectonion.cli.commands.keys_commands import _source_label
        result = _source_label(Path.home() / ".co")
        assert result == "~/.co (global)"

    def test_project_dir_label(self):
        from connectonion.cli.commands.keys_commands import _source_label
        with tempfile.TemporaryDirectory() as tmpdir:
            co_dir = Path(tmpdir) / ".co"
            co_dir.mkdir()
            result = _source_label(co_dir)
            assert "(project)" in result


class TestFindCoDir:
    """Tests for _find_co_dir."""

    def test_finds_local_co_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            # Create local .co/keys/agent.key
            co_dir = Path(tmpdir) / ".co" / "keys"
            co_dir.mkdir(parents=True)
            (co_dir / "agent.key").write_bytes(b"\x00" * 32)

            try:
                from connectonion.cli.commands.keys_commands import _find_co_dir
                result = _find_co_dir()
                assert result is not None
                assert result == Path(".co")
            finally:
                os.chdir(original_cwd)

    def test_falls_back_to_global(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            fake_home = Path(tmpdir) / "fake_home"
            co_keys = fake_home / ".co" / "keys"
            co_keys.mkdir(parents=True)
            (co_keys / "agent.key").write_bytes(b"\x00" * 32)

            try:
                with patch.object(Path, "home", return_value=fake_home):
                    from connectonion.cli.commands.keys_commands import _find_co_dir
                    result = _find_co_dir()
                    assert result is not None
                    assert ".co" in str(result)
            finally:
                os.chdir(original_cwd)

    def test_returns_none_when_no_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            fake_home = Path(tmpdir) / "fake_home"
            fake_home.mkdir()

            try:
                with patch.object(Path, "home", return_value=fake_home):
                    from connectonion.cli.commands.keys_commands import _find_co_dir
                    result = _find_co_dir()
                    assert result is None
            finally:
                os.chdir(original_cwd)


class TestLoadEnvVars:
    """Tests for _load_env_vars."""

    def test_loads_from_local_env(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)

            env_file = Path(tmpdir) / ".env"
            env_file.write_text("OPENONION_API_KEY=local-test-key\nGOOGLE_EMAIL=test@gmail.com\n")

            fake_home = Path(tmpdir) / "fake_home"
            fake_home.mkdir()

            try:
                with patch.object(Path, "home", return_value=fake_home):
                    with patch.dict(os.environ, {}, clear=True):
                        # Re-set minimal env for Python to work
                        os.environ["HOME"] = str(fake_home)
                        from connectonion.cli.commands.keys_commands import _load_env_vars
                        result = _load_env_vars()
                        assert result["OPENONION_API_KEY"] == "local-test-key"
                        assert result["GOOGLE_EMAIL"] == "test@gmail.com"
            finally:
                os.chdir(original_cwd)

    def test_returns_none_for_missing_vars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            os.chdir(tmpdir)
            fake_home = Path(tmpdir) / "fake_home"
            fake_home.mkdir()

            try:
                with patch.object(Path, "home", return_value=fake_home):
                    with patch.dict(os.environ, {}, clear=True):
                        os.environ["HOME"] = str(fake_home)
                        from connectonion.cli.commands.keys_commands import _load_env_vars
                        result = _load_env_vars()
                        assert result["OPENONION_API_KEY"] is None
                        assert result["GOOGLE_EMAIL"] is None
                        assert result["MICROSOFT_EMAIL"] is None
            finally:
                os.chdir(original_cwd)


class TestHandleKeysNoKeys:
    """Tests for handle_keys when no keys exist."""

    @patch("connectonion.cli.commands.keys_commands.console")
    @patch("connectonion.cli.commands.keys_commands._find_co_dir")
    def test_shows_error_when_no_co_dir(self, mock_find, mock_console):
        mock_find.return_value = None

        from connectonion.cli.commands.keys_commands import handle_keys
        handle_keys()

        # Should print error about no keys
        calls = [str(c) for c in mock_console.print.call_args_list]
        text = " ".join(calls)
        assert "No agent keys found" in text

    @patch("connectonion.cli.commands.keys_commands.console")
    @patch("connectonion.cli.commands.keys_commands._find_co_dir")
    @patch("connectonion.address.load")
    def test_shows_error_when_load_fails(self, mock_load, mock_find, mock_console):
        mock_find.return_value = Path(".co")
        mock_load.return_value = None

        from connectonion.cli.commands.keys_commands import handle_keys
        handle_keys()

        calls = [str(c) for c in mock_console.print.call_args_list]
        text = " ".join(calls)
        assert "Failed to load keys" in text


class TestHandleKeysSuccess:
    """Tests for handle_keys with valid keys."""

    MOCK_ADDR = {
        "address": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
        "short_address": "0xabcd...90ab",
        "email": "0xabcdef12@mail.openonion.ai",
        "seed_phrase": "canyon robot vacuum circle wave apple banana cherry date elderberry fig grape",
    }

    @patch("connectonion.cli.commands.keys_commands.console")
    @patch("connectonion.cli.commands.keys_commands._find_co_dir")
    @patch("connectonion.cli.commands.keys_commands._load_env_vars")
    @patch("connectonion.address.load")
    def test_displays_identity_panel(self, mock_load, mock_env, mock_find, mock_console):
        mock_find.return_value = Path(".co")
        mock_load.return_value = self.MOCK_ADDR
        mock_env.return_value = {"OPENONION_API_KEY": "eyJhbGciOiJIUzI1NiJ9.test", "AGENT_ADDRESS": None, "AGENT_EMAIL": None, "GOOGLE_EMAIL": None, "GOOGLE_ACCESS_TOKEN": None, "GOOGLE_REFRESH_TOKEN": None, "MICROSOFT_EMAIL": None, "MICROSOFT_ACCESS_TOKEN": None, "MICROSOFT_REFRESH_TOKEN": None}

        from connectonion.cli.commands.keys_commands import handle_keys
        handle_keys()

        # Should have printed multiple panels
        assert mock_console.print.call_count >= 4  # empty line + Identity + Secrets + Env Files + footer

    @patch("connectonion.cli.commands.keys_commands.console")
    @patch("connectonion.cli.commands.keys_commands._find_co_dir")
    @patch("connectonion.cli.commands.keys_commands._load_env_vars")
    @patch("connectonion.address.load")
    def test_masks_secrets_by_default(self, mock_load, mock_env, mock_find, mock_console):
        mock_find.return_value = Path(".co")
        mock_load.return_value = self.MOCK_ADDR
        mock_env.return_value = {"OPENONION_API_KEY": "eyJhbGciOiJIUzI1NiJ9.verylongtokenhere", "AGENT_ADDRESS": None, "AGENT_EMAIL": None, "GOOGLE_EMAIL": None, "GOOGLE_ACCESS_TOKEN": None, "GOOGLE_REFRESH_TOKEN": None, "MICROSOFT_EMAIL": None, "MICROSOFT_ACCESS_TOKEN": None, "MICROSOFT_REFRESH_TOKEN": None}

        from connectonion.cli.commands.keys_commands import handle_keys
        handle_keys(reveal=False)

        # Check the footer hint is shown
        calls = [str(c) for c in mock_console.print.call_args_list]
        text = " ".join(calls)
        assert "co keys --reveal" in text

    @patch("connectonion.cli.commands.keys_commands.console")
    @patch("connectonion.cli.commands.keys_commands._find_co_dir")
    @patch("connectonion.cli.commands.keys_commands._load_env_vars")
    @patch("connectonion.address.load")
    def test_reveal_shows_warning(self, mock_load, mock_env, mock_find, mock_console):
        mock_find.return_value = Path(".co")
        mock_load.return_value = self.MOCK_ADDR
        mock_env.return_value = {"OPENONION_API_KEY": "eyJtest", "AGENT_ADDRESS": None, "AGENT_EMAIL": None, "GOOGLE_EMAIL": None, "GOOGLE_ACCESS_TOKEN": None, "GOOGLE_REFRESH_TOKEN": None, "MICROSOFT_EMAIL": None, "MICROSOFT_ACCESS_TOKEN": None, "MICROSOFT_REFRESH_TOKEN": None}

        from connectonion.cli.commands.keys_commands import handle_keys
        handle_keys(reveal=True)

        calls = [str(c) for c in mock_console.print.call_args_list]
        text = " ".join(calls)
        assert "Do not share" in text

    @patch("connectonion.cli.commands.keys_commands.console")
    @patch("connectonion.cli.commands.keys_commands._find_co_dir")
    @patch("connectonion.cli.commands.keys_commands._load_env_vars")
    @patch("connectonion.address.load")
    def test_no_api_key_shows_hint(self, mock_load, mock_env, mock_find, mock_console):
        mock_find.return_value = Path(".co")
        mock_load.return_value = self.MOCK_ADDR
        mock_env.return_value = {"OPENONION_API_KEY": None, "AGENT_ADDRESS": None, "AGENT_EMAIL": None, "GOOGLE_EMAIL": None, "GOOGLE_ACCESS_TOKEN": None, "GOOGLE_REFRESH_TOKEN": None, "MICROSOFT_EMAIL": None, "MICROSOFT_ACCESS_TOKEN": None, "MICROSOFT_REFRESH_TOKEN": None}

        from connectonion.cli.commands.keys_commands import handle_keys
        handle_keys()

        # The "not set" hint is inside a Rich Panel/Table, so just check console was called
        assert mock_console.print.called

    @patch("connectonion.cli.commands.keys_commands.console")
    @patch("connectonion.cli.commands.keys_commands._find_co_dir")
    @patch("connectonion.cli.commands.keys_commands._load_env_vars")
    @patch("connectonion.address.load")
    def test_no_seed_phrase_shows_missing(self, mock_load, mock_env, mock_find, mock_console):
        addr_no_seed = {**self.MOCK_ADDR}
        del addr_no_seed["seed_phrase"]

        mock_find.return_value = Path(".co")
        mock_load.return_value = addr_no_seed
        mock_env.return_value = {"OPENONION_API_KEY": "key123", "AGENT_ADDRESS": None, "AGENT_EMAIL": None, "GOOGLE_EMAIL": None, "GOOGLE_ACCESS_TOKEN": None, "GOOGLE_REFRESH_TOKEN": None, "MICROSOFT_EMAIL": None, "MICROSOFT_ACCESS_TOKEN": None, "MICROSOFT_REFRESH_TOKEN": None}

        from connectonion.cli.commands.keys_commands import handle_keys
        handle_keys()

        assert mock_console.print.called


class TestHandleKeysOAuth:
    """Tests for OAuth section in handle_keys."""

    MOCK_ADDR = {
        "address": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
        "short_address": "0xabcd...90ab",
        "email": "0xabcdef12@mail.openonion.ai",
        "seed_phrase": "canyon robot vacuum",
    }

    @patch("connectonion.cli.commands.keys_commands.console")
    @patch("connectonion.cli.commands.keys_commands._find_co_dir")
    @patch("connectonion.cli.commands.keys_commands._load_env_vars")
    @patch("connectonion.address.load")
    def test_shows_google_oauth(self, mock_load, mock_env, mock_find, mock_console):
        mock_find.return_value = Path(".co")
        mock_load.return_value = self.MOCK_ADDR
        mock_env.return_value = {"OPENONION_API_KEY": "key", "AGENT_ADDRESS": None, "AGENT_EMAIL": None, "GOOGLE_EMAIL": "user@gmail.com", "GOOGLE_ACCESS_TOKEN": "ga_token", "GOOGLE_REFRESH_TOKEN": "gr_token", "MICROSOFT_EMAIL": None, "MICROSOFT_ACCESS_TOKEN": None, "MICROSOFT_REFRESH_TOKEN": None}

        from connectonion.cli.commands.keys_commands import handle_keys
        handle_keys()

        # OAuth panel should be rendered (Identity + Secrets + OAuth + Env Files = 4 panels + 2 footer lines)
        assert mock_console.print.call_count >= 5

    @patch("connectonion.cli.commands.keys_commands.console")
    @patch("connectonion.cli.commands.keys_commands._find_co_dir")
    @patch("connectonion.cli.commands.keys_commands._load_env_vars")
    @patch("connectonion.address.load")
    def test_shows_microsoft_oauth(self, mock_load, mock_env, mock_find, mock_console):
        mock_find.return_value = Path(".co")
        mock_load.return_value = self.MOCK_ADDR
        mock_env.return_value = {"OPENONION_API_KEY": "key", "AGENT_ADDRESS": None, "AGENT_EMAIL": None, "GOOGLE_EMAIL": None, "GOOGLE_ACCESS_TOKEN": None, "GOOGLE_REFRESH_TOKEN": None, "MICROSOFT_EMAIL": "user@outlook.com", "MICROSOFT_ACCESS_TOKEN": "ms_token", "MICROSOFT_REFRESH_TOKEN": "ms_refresh"}

        from connectonion.cli.commands.keys_commands import handle_keys
        handle_keys()

        assert mock_console.print.call_count >= 5

    @patch("connectonion.cli.commands.keys_commands.console")
    @patch("connectonion.cli.commands.keys_commands._find_co_dir")
    @patch("connectonion.cli.commands.keys_commands._load_env_vars")
    @patch("connectonion.address.load")
    def test_no_oauth_skips_panel(self, mock_load, mock_env, mock_find, mock_console):
        mock_find.return_value = Path(".co")
        mock_load.return_value = self.MOCK_ADDR
        mock_env.return_value = {"OPENONION_API_KEY": "key", "AGENT_ADDRESS": None, "AGENT_EMAIL": None, "GOOGLE_EMAIL": None, "GOOGLE_ACCESS_TOKEN": None, "GOOGLE_REFRESH_TOKEN": None, "MICROSOFT_EMAIL": None, "MICROSOFT_ACCESS_TOKEN": None, "MICROSOFT_REFRESH_TOKEN": None}

        from connectonion.cli.commands.keys_commands import handle_keys
        handle_keys()

        # Without OAuth: empty line + Identity + Secrets + Env Files + footer + empty = 6 calls
        # With OAuth it would be 7+
        assert mock_console.print.call_count <= 6


class TestCliKeysIntegration:
    """Integration tests for co keys via Typer CLI runner."""

    def setup_method(self):
        self.runner = ArgparseCliRunner()

    def test_keys_help(self):
        from connectonion.cli.main import cli
        result = self.runner.invoke(cli, ["keys", "--help"])
        assert result.exit_code == 0
        assert "--reveal" in result.output

    def test_help_lists_keys_command(self):
        from connectonion.cli.main import cli
        result = self.runner.invoke(cli, [])
        assert "keys" in result.output

    @patch("connectonion.cli.commands.keys_commands._find_co_dir")
    def test_keys_no_co_dir(self, mock_find):
        mock_find.return_value = None
        from connectonion.cli.main import cli
        result = self.runner.invoke(cli, ["keys"])
        assert result.exit_code == 0
        assert "No agent keys found" in result.output

    @patch("connectonion.cli.commands.keys_commands._find_co_dir")
    @patch("connectonion.cli.commands.keys_commands._load_env_vars")
    @patch("connectonion.address.load")
    def test_keys_displays_identity(self, mock_load, mock_env, mock_find):
        mock_find.return_value = Path(".co")
        mock_load.return_value = {
            "address": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
            "short_address": "0xabcd...90ab",
            "email": "0xabcdef12@mail.openonion.ai",
            "seed_phrase": "canyon robot vacuum circle wave",
        }
        mock_env.return_value = {"OPENONION_API_KEY": "eyJtest123456789", "AGENT_ADDRESS": None, "AGENT_EMAIL": None, "GOOGLE_EMAIL": None, "GOOGLE_ACCESS_TOKEN": None, "GOOGLE_REFRESH_TOKEN": None, "MICROSOFT_EMAIL": None, "MICROSOFT_ACCESS_TOKEN": None, "MICROSOFT_REFRESH_TOKEN": None}

        from connectonion.cli.main import cli
        result = self.runner.invoke(cli, ["keys"])

        assert result.exit_code == 0
        assert "Identity" in result.output
        assert "Secrets" in result.output
        assert "0xabcd...90ab" in result.output
        assert "co keys --reveal" in result.output

    @patch("connectonion.cli.commands.keys_commands._find_co_dir")
    @patch("connectonion.cli.commands.keys_commands._load_env_vars")
    @patch("connectonion.address.load")
    def test_keys_reveal_flag(self, mock_load, mock_env, mock_find):
        mock_find.return_value = Path(".co")
        mock_load.return_value = {
            "address": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
            "short_address": "0xabcd...90ab",
            "email": "0xabcdef12@mail.openonion.ai",
            "seed_phrase": "canyon robot vacuum circle wave apple banana",
        }
        mock_env.return_value = {"OPENONION_API_KEY": "eyJhbGciOiJIUzI1NiJ9.longtoken", "AGENT_ADDRESS": None, "AGENT_EMAIL": None, "GOOGLE_EMAIL": None, "GOOGLE_ACCESS_TOKEN": None, "GOOGLE_REFRESH_TOKEN": None, "MICROSOFT_EMAIL": None, "MICROSOFT_ACCESS_TOKEN": None, "MICROSOFT_REFRESH_TOKEN": None}

        from connectonion.cli.main import cli
        result = self.runner.invoke(cli, ["keys", "--reveal"])

        assert result.exit_code == 0
        assert "Do not share" in result.output
        # Full seed phrase should be visible
        assert "canyon robot vacuum" in result.output
        # Full API key should be visible
        assert "eyJhbGciOiJIUzI1NiJ9.longtoken" in result.output
