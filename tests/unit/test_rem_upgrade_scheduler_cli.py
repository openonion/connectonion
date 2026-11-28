"""CLI reconciliation never touches the real scheduler or notebook."""
import json

import pytest
from typer.testing import CliRunner

from connectonion.cli.commands import rem_commands
from connectonion.cli.main import app
from connectonion.rem import auto_upgrade
from connectonion.rem.files import RemError


@pytest.fixture
def scheduler(monkeypatch):
    class FakeScheduler:
        installed = False
        calls = []
        fail = False

        def describe(self):
            return {"scheduler": "launchd", "installed": self.installed}

        def install(self, **kwargs):
            self.calls.append(("install", kwargs))
            if self.fail:
                raise RemError("bootstrap denied")
            type(self).installed = True
            return self.describe()

        def uninstall(self):
            self.calls.append(("uninstall", {}))

    monkeypatch.setattr(auto_upgrade, "DailyUpgradeScheduler", FakeScheduler)
    monkeypatch.setattr(auto_upgrade, "detect_install_method", lambda: {"method": "uv_tool", "supported": True})
    monkeypatch.setattr(auto_upgrade, "read_upgrade_config", lambda: {"enabled": True, "channel": "preview", "time": "01:00"})
    return FakeScheduler


def test_reconcile_installs_once_at_configured_time(scheduler):
    rem_commands._reconcile_upgrade_scheduler()
    rem_commands._reconcile_upgrade_scheduler()
    assert scheduler.calls == [("install", {"hour": 1, "minute": 0})]


@pytest.mark.parametrize("config,install,reason", [
    ({"enabled": False, "channel": "preview"}, {"supported": True}, "disabled"),
    ({"enabled": True, "channel": "pinned"}, {"supported": True}, "pinned"),
    ({"enabled": True, "channel": "preview"}, {"supported": False}, "unsupported install"),
])
def test_reconcile_respects_ineligible_states(monkeypatch, scheduler, config, install, reason):
    monkeypatch.setattr(auto_upgrade, "read_upgrade_config", lambda: config)
    monkeypatch.setattr(auto_upgrade, "detect_install_method", lambda: install)
    rem_commands._reconcile_upgrade_scheduler()
    assert scheduler.calls == []
    assert rem_commands._upgrade_schedule_state(config, install, scheduler().describe()) == {
        "effective": False, "reason": reason}


def test_failed_install_is_reported_and_cleaned_up(monkeypatch, scheduler):
    messages = []
    scheduler.fail = True
    monkeypatch.setattr(rem_commands.rem_look, "line", lambda message, **kw: messages.append(message))
    rem_commands._reconcile_upgrade_scheduler()
    assert [call[0] for call in scheduler.calls] == ["install", "uninstall"]
    assert "bootstrap denied" in messages[0]


def test_status_distinguishes_missing_and_unverified_job(tmp_path, scheduler):
    result = CliRunner().invoke(app, ["rem", "--root", str(tmp_path), "--json", "upgrade", "status"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["effective_state"] == {
        "effective": False, "reason": "scheduler not installed"}
    scheduler.installed = True
    result = CliRunner().invoke(app, ["rem", "--root", str(tmp_path), "--json", "upgrade", "status"])
    assert json.loads(result.stdout)["data"]["effective_state"]["effective"] == "unknown"


def test_scheduled_failure_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setattr(auto_upgrade, "run_atomic_upgrade", lambda **kwargs: {"outcome": "failed", "error": "fixture failure"})
    result = CliRunner().invoke(app, ["rem", "--root", str(tmp_path), "--json", "upgrade", "run", "--scheduled"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False


def test_default_reader_entry_reconciles(tmp_path, monkeypatch, scheduler):
    from connectonion import address
    from connectonion.rem import reader

    from pathlib import Path

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".co" / "rem").mkdir(parents=True)
    monkeypatch.setattr(address, "load", lambda path: {"address": "fixture"})
    monkeypatch.setattr(reader, "local_or_snapshot", lambda *args, **kwargs: {"opened": True})
    result = CliRunner().invoke(app, ["rem", "open"])
    assert result.exit_code == 0, result.output
    assert scheduler.calls == [("install", {"hour": 1, "minute": 0})]
