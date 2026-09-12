"""
LLM-Note: Tests for authorizing an application you already have —
`co auth feishu --app-id`. The point is reuse: a bot that is already in the
group with its permissions set, rather than a new one that is in no group.
Also the lark-cli hint, which reads app ids from a plaintext config and never
touches the secret those ids are keyed to.
"""

import json
from pathlib import Path

import pytest

from connectonion.cli.commands import feishu_auth


class FakeRegistration:
    def __init__(self, brand="feishu"):
        self.kwargs = None
        self.brand = brand

    def __call__(self, on_qr_code, on_status_change=None, **kwargs):
        self.kwargs = kwargs
        on_qr_code({"url": "https://open.feishu.cn/page/cli?user_code=ABC", "expire_in": 600})
        return {"client_id": kwargs.get("app_id") or "cli_new",
                "client_secret": "secret-x",
                "user_info": {"open_id": "ou_me", "tenant_brand": self.brand}}


@pytest.fixture
def rig(tmp_path, monkeypatch):
    # conftest's _never_touch_the_real_home already points HOME at its own
    # temp directory, and that is the one Path.home() resolves to. Writing a
    # fake lark-cli config anywhere else would be writing where nothing looks.
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path / ".co"))
    (tmp_path / ".co").mkdir(parents=True, exist_ok=True)
    written = {}
    monkeypatch.setattr(feishu_auth, "upsert_env",
                        lambda path, values: written.setdefault(str(path), {}).update(values))
    return tmp_path, written


def lark_cli_config(apps):
    directory = Path.home() / ".lark-cli"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "config.json").write_text(json.dumps({"currentApp": apps[0]["appId"], "apps": apps}))
    return directory / "config.json"


class TestAuthorizingAnApplicationYouAlreadyHave:
    def test_the_app_id_is_passed_to_the_scan(self, rig, monkeypatch):
        register = FakeRegistration()
        monkeypatch.setattr(feishu_auth, "_register_app", lambda: register)
        feishu_auth.handle_feishu_auth(app_id="cli_existing")
        assert register.kwargs["app_id"] == "cli_existing"

    def test_its_credentials_are_what_gets_saved(self, rig, monkeypatch):
        tmp_path, written = rig
        register = FakeRegistration()
        monkeypatch.setattr(feishu_auth, "_register_app", lambda: register)
        feishu_auth.handle_feishu_auth(app_id="cli_existing")
        values = next(iter(written.values()))
        assert values["FEISHU_APP_ID"] == "cli_existing"
        assert values["FEISHU_APP_SECRET"] == "secret-x"

    def test_creating_a_new_one_passes_no_app_id(self, rig, monkeypatch):
        register = FakeRegistration()
        monkeypatch.setattr(feishu_auth, "_register_app", lambda: register)
        feishu_auth.handle_feishu_auth()
        assert register.kwargs.get("app_id") is None

    def test_an_app_id_that_is_not_one_is_refused_before_the_scan(self, rig, monkeypatch, capsys):
        register = FakeRegistration()
        monkeypatch.setattr(feishu_auth, "_register_app", lambda: register)
        with pytest.raises(SystemExit) as exit:
            feishu_auth.handle_feishu_auth(app_id="not-an-app-id")
        assert exit.value.code == 2
        assert register.kwargs is None, "the scan started before the id was checked"
        assert "cli_" in capsys.readouterr().out


class TestTheHintFromLarkCli:
    """Reading app ids from lark-cli's plaintext config. Never the secret:
    that lives in the OS keychain, keyed by an id in this same file, and
    copying it out would downgrade it into a plaintext env file."""

    def test_configured_applications_are_offered(self, rig, monkeypatch, capsys):
        tmp_path, _ = rig
        lark_cli_config([
            {"appId": "cli_aaa", "brand": "lark",
             "appSecret": {"source": "keychain", "id": "appsecret:cli_aaa"},
             "users": [{"userName": "xie Aaron"}]},
            {"appId": "cli_bbb", "brand": "feishu", "appSecret": {"source": "keychain"}},
        ])
        register = FakeRegistration()
        monkeypatch.setattr(feishu_auth, "_register_app", lambda: register)
        feishu_auth.handle_feishu_auth()
        out = capsys.readouterr().out
        assert "cli_aaa" in out and "cli_bbb" in out
        assert "--app-id" in out

    def test_the_secret_is_never_read_or_shown(self, rig, monkeypatch, capsys):
        tmp_path, _ = rig
        lark_cli_config([
            {"appId": "cli_aaa", "brand": "lark",
             "appSecret": {"source": "keychain", "id": "appsecret:cli_aaa"}},
        ])
        register = FakeRegistration()
        monkeypatch.setattr(feishu_auth, "_register_app", lambda: register)
        feishu_auth.handle_feishu_auth()
        out = capsys.readouterr().out
        assert "appsecret:" not in out
        assert "keychain" not in out.lower()

    def test_no_lark_cli_means_no_hint_and_no_error(self, rig, monkeypatch, capsys):
        register = FakeRegistration()
        monkeypatch.setattr(feishu_auth, "_register_app", lambda: register)
        feishu_auth.handle_feishu_auth()
        assert "--app-id" not in capsys.readouterr().out

    def test_a_config_that_does_not_parse_is_not_an_error(self, rig, monkeypatch):
        directory = Path.home() / ".lark-cli"
        directory.mkdir()
        (directory / "config.json").write_text("{ not json")
        register = FakeRegistration()
        monkeypatch.setattr(feishu_auth, "_register_app", lambda: register)
        feishu_auth.handle_feishu_auth()          # must not raise
        assert register.kwargs is not None

    def test_reading_it_finds_the_ids(self, rig):
        tmp_path, _ = rig
        lark_cli_config([
            {"appId": "cli_aaa", "brand": "lark", "users": [{"userName": "xie Aaron"}]},
            {"appId": "cli_bbb", "brand": "feishu"},
        ])
        found = feishu_auth.lark_cli_applications()
        assert [a["app_id"] for a in found] == ["cli_aaa", "cli_bbb"]
        assert found[0]["brand"] == "lark"
        assert found[0]["user"] == "xie Aaron"
        assert "secret" not in json.dumps(found).lower()
