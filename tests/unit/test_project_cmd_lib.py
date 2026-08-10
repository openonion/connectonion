"""Tests for CLI project helpers — upsert_env credential writing."""

import sys

import pytest

from connectonion.cli.commands.project_cmd_lib import (
    detect_api_provider,
    upsert_env,
)


class TestDetectApiProvider:
    """detect_api_provider maps key prefixes to providers, most-specific first."""

    @pytest.mark.parametrize(
        ("key", "provider"),
        [
            ("sk-ant-test", "anthropic"),
            ("sk-proj-test", "openai"),
            ("sk-or-v1-test", "openrouter"),
            # sk-orca- must not be claimed by the shorter sk- OpenAI prefix.
            ("sk-orca-test", "orcarouter"),
            ("sk-regular-openai", "openai"),
            ("AIza-test", "google"),
            ("gsk_test", "groq"),
            ("xai-test", "grok"),
            ("totally-unknown", "openai"),
        ],
    )
    def test_detects_by_prefix(self, key, provider):
        assert detect_api_provider(key)[0] == provider


class TestUpsertEnv:
    """upsert_env replaces, appends, and creates .env files safely."""

    def test_creates_file_with_new_keys(self, tmp_path):
        env_file = tmp_path / "keys.env"
        upsert_env(env_file, {"A": "1", "B": "2"})

        assert env_file.read_text() == "A=1\nB=2\n"

    def test_replaces_existing_key_and_keeps_the_rest(self, tmp_path):
        env_file = tmp_path / "keys.env"
        env_file.write_text("# comment\nA=old\nOTHER=keep\n")

        upsert_env(env_file, {"A": "new"})

        assert env_file.read_text() == "# comment\nA=new\nOTHER=keep\n"

    def test_appends_to_file_without_trailing_newline(self, tmp_path):
        env_file = tmp_path / "keys.env"
        env_file.write_text("A=1")

        upsert_env(env_file, {"B": "2"})

        assert env_file.read_text() == "A=1\nB=2\n"

    def test_skips_none_values(self, tmp_path):
        env_file = tmp_path / "keys.env"
        env_file.write_text("A=1\n")

        upsert_env(env_file, {"A": None, "B": "2"})

        assert env_file.read_text() == "A=1\nB=2\n"

    def test_strip_prefix_drops_stale_credentials(self, tmp_path):
        env_file = tmp_path / "keys.env"
        env_file.write_text("MICROSOFT_OLD=x\nMICROSOFT_EMAIL=a@b.com\nKEEP=1\n")

        upsert_env(env_file, {"MICROSOFT_EMAIL": "c@d.com"}, strip_prefix="MICROSOFT_")

        assert env_file.read_text() == "KEEP=1\nMICROSOFT_EMAIL=c@d.com\n"

    def test_written_file_is_owner_only(self, tmp_path):
        env_file = tmp_path / "keys.env"
        upsert_env(env_file, {"TOKEN": "secret"})

        if sys.platform != "win32":
            assert env_file.stat().st_mode & 0o777 == 0o600


class TestATokenThatNamesAnotherAccount:
    """oo-api#67. After `co account migrate` the stored token names the address
    the account left. Nothing errors: `/api/v1/auth` creates an account for any
    key that authenticates, so the old address becomes a fresh, empty, working
    one and every command keeps succeeding against the wrong row. `co status`
    read the migrated balance while `co server new` spent $180 of an account the
    operator did not know existed.
    """

    MINE = "0x" + "a" * 64
    THEIRS = "0x" + "b" * 64

    def _token(self, public_key):
        import base64
        import json

        body = base64.urlsafe_b64encode(
            json.dumps({"public_key": public_key, "iat": 1}).encode()).rstrip(b"=")
        return "header." + body.decode() + ".signature"

    def _patched(self, monkeypatch, identity_address, refreshed_to=None):
        from connectonion.cli.commands import project_cmd_lib as lib

        calls = []

        def fake_authenticate(co_dir, save_to_project=True, quiet=False):
            calls.append(co_dir)
            if refreshed_to:
                monkeypatch.setenv("OPENONION_API_KEY", refreshed_to)
                return True
            return False

        monkeypatch.setattr(lib.address, "load",
                            lambda co_dir: {"address": identity_address})
        monkeypatch.setattr(
            "connectonion.cli.commands.auth_commands.authenticate", fake_authenticate)
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: True)
        return lib, calls

    def test_the_token_is_refreshed_when_it_names_a_different_account(
            self, monkeypatch):
        fresh = self._token(self.MINE)
        lib, calls = self._patched(monkeypatch, self.MINE, refreshed_to=fresh)

        assert lib._token_for_this_account(self._token(self.THEIRS)) == fresh
        assert calls, "a token for another account was used as-is"

    def test_a_token_for_this_account_costs_no_network_call(self, monkeypatch):
        lib, calls = self._patched(monkeypatch, self.MINE)
        token = self._token(self.MINE)

        assert lib._token_for_this_account(token) == token
        assert not calls, "re-authenticated for no reason"

    def test_an_unreadable_token_is_left_alone(self, monkeypatch):
        """It may be a shape we do not know. The server is the authority on
        whether a token is valid — guessing here would lock somebody out of a
        working setup."""
        lib, calls = self._patched(monkeypatch, self.MINE)

        assert lib._token_for_this_account("not-a-jwt") == "not-a-jwt"
        assert not calls

    def test_the_claim_is_read_without_verifying_it(self):
        from connectonion.cli.commands.project_cmd_lib import account_in_token

        assert account_in_token(self._token(self.THEIRS)) == self.THEIRS
        assert account_in_token("garbage") is None
        assert account_in_token("a.b.c") is None
