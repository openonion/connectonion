"""`co auth lark` begins on Lark, and every sentence around it says Lark.

Found 2026-09-14 when the owner asked for a Lark application and was handed an
open.feishu.cn link. The SDK starts on the Feishu accounts domain whichever
brand you ask for, and only moves to Lark after polling notices the scanner's
tenant is one. It works — and a Lark user asking for Lark reads it as the wrong
product, because it is the wrong product until they scan.

`brand` was already a parameter. It decided which env-file prefix to write and
nothing else: the domain, the "Creating a Feishu application" line, the
incomplete-registration remedy, and the reuse command lark-cli's config feeds
all said Feishu unconditionally. Two of those are commands a person is told to
run, which is the class of wrong instruction this codebase keeps finding.
"""

import json
from pathlib import Path

import pytest

from connectonion.cli.commands import feishu_auth


class FakeRegistration:
    def __init__(self, brand="lark"):
        self.kwargs = None
        self.brand = brand

    def __call__(self, on_qr_code, on_status_change=None, **kwargs):
        self.kwargs = kwargs
        host = "open.larksuite.com" if kwargs.get("domain") else "open.feishu.cn"
        on_qr_code({"url": f"https://{host}/page/launcher?user_code=ABC", "expire_in": 600})
        return {"client_id": kwargs.get("app_id") or "cli_new",
                "client_secret": "secret-x",
                "user_info": {"open_id": "ou_me", "tenant_brand": self.brand}}


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path / ".co"))
    (tmp_path / ".co").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(feishu_auth, "upsert_env", lambda path, values: None)
    return tmp_path


def lark_cli_config(apps):
    directory = Path.home() / ".lark-cli"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "config.json").write_text(
        json.dumps({"currentApp": apps[0]["appId"], "apps": apps})
    )


def test_lark_starts_on_the_lark_accounts_domain(rig, monkeypatch):
    register = FakeRegistration()
    monkeypatch.setattr(feishu_auth, "_register_app", lambda: register)

    feishu_auth.handle_feishu_auth(brand="lark")

    assert register.kwargs.get("domain") == feishu_auth.LARK_ACCOUNTS


def test_feishu_leaves_the_sdk_on_its_feishu_default(rig, monkeypatch):
    """Not a regression guard for its own sake: the SDK still switches a Feishu
    flow to Lark when a Lark tenant scans, so passing nothing keeps that."""
    register = FakeRegistration(brand="feishu")
    monkeypatch.setattr(feishu_auth, "_register_app", lambda: register)

    feishu_auth.handle_feishu_auth(brand="feishu")

    assert "domain" not in register.kwargs


def test_the_link_a_lark_user_is_shown_is_a_lark_link(rig, monkeypatch, capsys):
    register = FakeRegistration()
    monkeypatch.setattr(feishu_auth, "_register_app", lambda: register)

    feishu_auth.handle_feishu_auth(brand="lark")

    out = capsys.readouterr().out
    assert "open.larksuite.com" in out
    assert "open.feishu.cn" not in out


def test_lark_says_it_is_creating_a_lark_application(rig, monkeypatch, capsys):
    register = FakeRegistration()
    monkeypatch.setattr(feishu_auth, "_register_app", lambda: register)

    feishu_auth.handle_feishu_auth(brand="lark")

    assert "Creating a Lark application" in capsys.readouterr().out


def test_the_reuse_command_names_the_apps_own_brand(rig, monkeypatch, capsys):
    """The app's brand was recorded by lark-cli at login — better evidence than
    what the person typed just now."""
    lark_cli_config([
        {"appId": "cli_aaa", "brand": "lark",
         "appSecret": {"source": "keychain", "id": "x"},
         "users": [{"userName": "xie Aaron"}]},
    ])
    register = FakeRegistration()
    monkeypatch.setattr(feishu_auth, "_register_app", lambda: register)

    feishu_auth.handle_feishu_auth(brand="lark")

    out = capsys.readouterr().out
    assert "co auth lark --app-id cli_aaa" in out
    assert "co auth feishu --app-id" not in out


def test_a_lark_app_is_offered_as_lark_even_when_feishu_was_typed(rig, monkeypatch, capsys):
    lark_cli_config([
        {"appId": "cli_aaa", "brand": "lark", "appSecret": {"source": "keychain"}},
    ])
    register = FakeRegistration(brand="feishu")
    monkeypatch.setattr(feishu_auth, "_register_app", lambda: register)

    feishu_auth.handle_feishu_auth(brand="feishu")

    assert "co auth lark --app-id cli_aaa" in capsys.readouterr().out


def test_an_incomplete_lark_registration_names_the_lark_command(rig, monkeypatch, capsys):
    """A remedy that sends a Lark user to `co auth feishu` is the bug, restated."""
    class Half(FakeRegistration):
        def __call__(self, on_qr_code, on_status_change=None, **kwargs):
            on_qr_code({"url": "https://open.larksuite.com/x", "expire_in": 600})
            return {"client_id": "cli_new"}  # no secret

    monkeypatch.setattr(feishu_auth, "_register_app", lambda: Half())

    with pytest.raises(SystemExit):
        feishu_auth.handle_feishu_auth(brand="lark")

    out = capsys.readouterr().out
    assert "Lark returned an incomplete registration" in out
    assert "Next: co auth lark" in out
    assert "co auth feishu" not in out
