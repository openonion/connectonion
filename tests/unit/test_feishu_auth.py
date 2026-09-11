"""
LLM-Note: Tests for connectonion.cli.commands.feishu_auth — `co auth feishu`,
the scan that creates the app and writes its credentials. The SDK call is
faked: no browser, no network, no app created.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from connectonion.cli.commands import feishu_auth


class FakeRegistration:
    """Stands in for lark_oapi.register_app."""

    def __init__(self, result=None, error=None, brand="feishu"):
        self.result = result or {
            "client_id": "cli_new123",
            "client_secret": "secret-new123",
            "user_info": {"open_id": "ou_me", "tenant_brand": brand},
        }
        self.error = error
        self.shown = []

    def __call__(self, on_qr_code, on_status_change=None, **kwargs):
        on_qr_code({"url": "https://open.feishu.cn/page/cli?user_code=ABC", "expire_in": 600})
        self.shown.append(kwargs)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def rig(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path / ".co"))
    (tmp_path / ".co").mkdir(parents=True, exist_ok=True)
    written = {}

    def fake_upsert(path, values):
        written.setdefault(str(path), {}).update(values)

    monkeypatch.setattr(feishu_auth, "upsert_env", fake_upsert)
    return tmp_path, written


def run(register, monkeypatch, **kwargs):
    monkeypatch.setattr(feishu_auth, "_register_app", lambda: register)
    return feishu_auth.handle_feishu_auth(**kwargs)


class TestTheScan:
    def test_the_link_is_printed_so_a_terminal_without_a_camera_still_works(self, rig, monkeypatch, capsys):
        register = FakeRegistration()
        run(register, monkeypatch)
        out = capsys.readouterr().out
        assert "https://open.feishu.cn/page/cli?user_code=ABC" in out

    def test_a_qr_code_is_drawn(self, rig, monkeypatch, capsys):
        register = FakeRegistration()
        run(register, monkeypatch)
        out = capsys.readouterr().out
        # The block characters a terminal QR is made of.
        assert any(ch in out for ch in "█▀▄")

    def test_the_app_is_named_so_it_is_findable_later(self, rig, monkeypatch):
        register = FakeRegistration()
        run(register, monkeypatch)
        preset = register.shown[0].get("app_preset") or {}
        assert "ConnectOnion" in (preset.get("name") or "")


class TestWhatGetsWritten:
    def test_credentials_land_in_the_selected_env_file(self, rig, monkeypatch):
        tmp_path, written = rig
        run(FakeRegistration(), monkeypatch)
        values = next(iter(written.values()))
        assert values["FEISHU_APP_ID"] == "cli_new123"
        assert values["FEISHU_APP_SECRET"] == "secret-new123"

    def test_a_lark_tenant_writes_the_lark_names(self, rig, monkeypatch):
        # The flow always starts on Feishu and switches if the tenant is Lark,
        # so which brand it was is only known at the end.
        tmp_path, written = rig
        run(FakeRegistration(brand="lark"), monkeypatch)
        values = next(iter(written.values()))
        assert values["LARK_APP_ID"] == "cli_new123"
        assert "FEISHU_APP_ID" not in values

    def test_the_secret_is_never_printed(self, rig, monkeypatch, capsys):
        run(FakeRegistration(), monkeypatch)
        assert "secret-new123" not in capsys.readouterr().out

    def test_it_ends_by_naming_the_next_command(self, rig, monkeypatch, capsys):
        run(FakeRegistration(), monkeypatch)
        out = capsys.readouterr().out
        assert "co feishu check" in out or "co ai" in out


class TestWhenItCannotRun:
    def test_a_missing_sdk_names_the_install_command(self, rig, monkeypatch, capsys):
        def no_sdk():
            raise RuntimeError("The Feishu SDK is not installed. Run: pip install lark-oapi")

        monkeypatch.setattr(feishu_auth, "_register_app", no_sdk)
        with pytest.raises(SystemExit) as exit:
            feishu_auth.handle_feishu_auth()
        assert exit.value.code == 3
        assert "pip install lark-oapi" in capsys.readouterr().out

    def test_a_refused_scan_is_one_line_not_a_traceback(self, rig, monkeypatch, capsys):
        register = FakeRegistration(error=RuntimeError("app registration denied by user"))
        with pytest.raises(SystemExit) as exit:
            run(register, monkeypatch)
        assert exit.value.code == 1
        out = capsys.readouterr().out
        assert "denied" in out.lower()
        assert "Traceback" not in out

    def test_nothing_is_written_when_the_scan_fails(self, rig, monkeypatch):
        tmp_path, written = rig
        register = FakeRegistration(error=RuntimeError("device code expired"))
        with pytest.raises(SystemExit):
            run(register, monkeypatch)
        assert written == {}, "a failed scan must not leave half a credential behind"

    def test_a_response_without_a_secret_is_refused(self, rig, monkeypatch, capsys):
        tmp_path, written = rig
        register = FakeRegistration(result={"client_id": "cli_x", "client_secret": ""})
        with pytest.raises(SystemExit) as exit:
            run(register, monkeypatch)
        assert exit.value.code == 1
        assert written == {}


class TestEnvSetStillRefusesTheseNames:
    def test_the_app_secret_points_at_this_command(self):
        # co env set must refuse a Feishu credential the way it refuses a
        # Google one, or two ways of writing it drift apart.
        from connectonion.cli.commands.env_commands import _PROVIDER_AUTH

        assert _PROVIDER_AUTH["FEISHU"] == "co auth feishu"
        assert _PROVIDER_AUTH["LARK"] == "co auth lark"
