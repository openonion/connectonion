"""Tests for CLI project helpers — upsert_env credential writing."""

import sys
from pathlib import Path

from connectonion.cli.commands.project_cmd_lib import (
    configure_env_for_provider,
    copy_control_center_template,
    detect_api_provider,
    upsert_env,
)


class TestControlCenterTemplate:
    """Every new project gets an editable full Web app without freezing updates."""

    def test_copies_the_complete_default_app(self, tmp_path):
        co_dir = tmp_path / ".co"
        co_dir.mkdir()

        assert copy_control_center_template(co_dir) is True

        app = co_dir / "control-center"
        assert {path.name for path in app.iterdir()} == {
            "index.html", "control-center.js", "CONTROL_CENTER.md",
        }
        html = (app / "index.html").read_text(encoding="utf-8")
        bridge = (app / "control-center.js").read_text(encoding="utf-8")
        contract = (app / "CONTROL_CENTER.md").read_text(encoding="utf-8")
        assert 'src="./control-center.js"' in html
        assert "send_message" in bridge and "run_skill" in bridge
        assert "message.skills" in bridge
        assert "current Agent Chat" in contract
        assert "content-addressed URL" in contract
        assert "<agent-address>/<sha256-revision>/index.html" in contract

    def test_never_overwrites_an_authored_app(self, tmp_path):
        app = tmp_path / ".co" / "control-center"
        app.mkdir(parents=True)
        custom = app / "index.html"
        custom.write_text("<h1>Mine</h1>", encoding="utf-8")

        assert copy_control_center_template(tmp_path / ".co") is False
        assert custom.read_text(encoding="utf-8") == "<h1>Mine</h1>"


class TestApiProviderDetection:
    """Provider-specific key prefixes win before generic prefixes."""

    def test_specific_sk_prefixes_win_before_generic_openai_prefix(self):
        assert detect_api_provider("sk-or-v1-test-key") == (
            "openrouter",
            "openrouter",
        )
        assert detect_api_provider("sk-proj-test-key") == ("openai", "project")
        assert detect_api_provider("sk-test-key") == ("openai", "user")

    def test_openrouter_key_configures_openrouter_environment(self):
        api_key = "sk-or-v1-test-key"
        provider, _key_type = detect_api_provider(api_key)

        env_content = configure_env_for_provider(provider, api_key)

        assert f"OPENROUTER_API_KEY={api_key}" in env_content
        assert "OPENAI_API_KEY=" not in env_content
        assert "MODEL=openrouter/openai/o4-mini" in env_content


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

    def test_a_project_mismatch_reauthenticates_with_the_project_key(
        self, tmp_path, monkeypatch
    ):
        from connectonion.cli.commands import project_cmd_lib as lib

        project = tmp_path / "project"
        nested = project / "src"
        project_co = project / ".co"
        home = tmp_path / "home"
        global_co = home / ".co"
        project_co.mkdir(parents=True)
        nested.mkdir()
        global_co.mkdir(parents=True)
        project_account = "0x" + "c" * 64
        global_account = "0x" + "d" * 64
        fresh = self._token(project_account)
        calls = []

        def identity_at(path):
            path = Path(path).resolve()
            if path == project_co.resolve():
                return {"address": project_account}
            if path == global_co.resolve():
                return {"address": global_account}
            return None

        def authenticate(co_dir, **_kwargs):
            calls.append(Path(co_dir).resolve())
            monkeypatch.setenv("OPENONION_API_KEY", fresh)
            return True

        monkeypatch.chdir(nested)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        monkeypatch.setattr(lib.address, "load", identity_at)
        monkeypatch.setattr(
            "connectonion.cli.commands.auth_commands.authenticate",
            authenticate,
        )
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: True)

        assert lib._token_for_this_account(self._token(self.THEIRS)) == fresh
        assert calls == [project_co.resolve()]

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
