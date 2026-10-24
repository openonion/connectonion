"""Native registration, ownership and migration contracts; no real user tasks."""

import json
import sqlite3
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

from connectonion.rem.codex_schedule import CodexNative, automation_id, recurrence
from connectonion.rem.config import default_config
from connectonion.rem.files import RemError, atomic_write, state_path, write_json
from connectonion.rem.schedule import Launchd, default_scheduler


class Launcher:
    def __init__(self, *, state="waiting", installed=True):
        self.state, self.present, self.removed = state, installed, False

    def installed(self, root):
        return self.present

    def describe(self, root):
        return {"installed": self.present, "loaded": self.present, "state": self.state}

    def uninstall(self, root):
        self.present, self.removed = False, True
        return True

    def unload_for_migration(self, root):
        return self.uninstall(root)


def running(command, **kwargs):
    return subprocess.CompletedProcess(command, 0, stdout="123\n")


@pytest.fixture(autouse=True)
def known_timezone(monkeypatch):
    monkeypatch.setattr("connectonion.rem.config.local_timezone", lambda: "Australia/Sydney")
    monkeypatch.setattr("connectonion.rem.codex_schedule.desktop_timezone", lambda: "Australia/Sydney")


@pytest.fixture
def native(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.rem.codex_schedule._checkout_path", lambda: "")
    monkeypatch.setattr("connectonion.rem.codex_schedule.desktop_app", lambda: Path("/Applications/Codex.app"))
    return CodexNative(tmp_path / "codex", launcher=Launcher(),
                       command=["/venv with spaces/bin/python", "-m", "connectonion.cli.main"],
                       run=running, wait_seconds=0)


def adopt(native, root):
    """A private test index, standing in for desktop file adoption."""
    definition = native.definition(root)
    database = native.home / "sqlite" / "codex-dev.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS automations "
                           "(id TEXT PRIMARY KEY, rrule TEXT, status TEXT, cwds TEXT, "
                           "updated_at INTEGER, next_run_at INTEGER, last_run_at INTEGER)")
        connection.execute("INSERT OR REPLACE INTO automations VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (definition["id"], definition["rrule"], definition["status"],
                            json.dumps(definition["cwds"]), definition["updated_at"],
                            1900000000000 if definition["status"] == "ACTIVE" else None, None))


def test_exact_time_pairs_are_selected_without_extra_slots():
    config = default_config()
    config["schedule"] = {"times": ["03:15", "17:45", "06:15"], "timezone": "Australia/Sydney"}
    assert recurrence(config) == "FREQ=DAILY;BYHOUR=3,6,17;BYMINUTE=15,45;BYSECOND=0;BYSETPOS=1,3,6"


def test_different_saved_timezone_cannot_silently_shift(native, tmp_path, monkeypatch):
    config = default_config()
    config["schedule"]["timezone"] = "Asia/Kathmandu"
    with pytest.raises(RemError, match="different saved timezone"):
        native.install(tmp_path / "notes", config)
    assert not native.launcher.removed


def test_private_file_pins_interpreter_root_model_and_archival(native, tmp_path):
    root = tmp_path / 'notes with "quotes"'
    data = native.render(root, default_config(), active=False)
    native._write(root, data)
    saved = tomllib.loads(native.definition_path(root).read_text())
    assert saved["status"] == "PAUSED" and saved["auto_archive"] is True
    assert saved["model"] == "gpt-6-luna" and saved["execution_environment"] == "local"
    assert "'/venv with spaces/bin/python' -m connectonion.cli.main" in saved["prompt"]
    assert "sync --scheduled" in saved["prompt"] and saved["cwds"] == [str(root.resolve())]
    assert native.definition_path(root).stat().st_mode & 0o777 == 0o600


def test_running_legacy_batch_is_kept_without_creating_another_clock(native, tmp_path):
    native.launcher.state = "running"
    with pytest.raises(RemError, match="still running"):
        native.install(tmp_path / "notes", default_config())
    assert not native.launcher.removed
    assert not native.definition_path(tmp_path / "notes").exists()


def test_unsupported_dense_rule_keeps_the_existing_clock(native, tmp_path):
    config = default_config()
    config["schedule"]["times"] = [f"{hour:02}:{hour:02}" for hour in range(20)]
    with pytest.raises(RemError, match="exceed Codex's rule limits"):
        native.install(tmp_path / "notes", config)
    assert not native.launcher.removed
    assert not native.definition_path(tmp_path / "notes").exists()


def test_failed_registration_keeps_old_clock_and_only_stages_a_paused_task(native, tmp_path):
    root = tmp_path / "notes"
    with pytest.raises(RemError, match="previous clock"):
        native.install(root, default_config())
    assert not native.launcher.removed
    assert native.definition(root)["status"] == "PAUSED"
    assert native.describe(root)["loaded"] is False


def test_failed_update_restores_the_previous_active_definition(native, tmp_path):
    root = tmp_path / "notes"
    native.launcher.present = False
    previous = native.render(root, default_config())
    native._write(root, previous)
    before = native.definition_path(root).read_bytes()
    with pytest.raises(RemError, match="previous clock"):
        native.install(root, default_config())
    assert native.definition_path(root).read_bytes() == before


def test_unload_failure_prevents_native_activation(native, tmp_path, monkeypatch):
    root = tmp_path / "notes"
    write = native._write

    def desktop_write(root, data):
        write(root, data)
        adopt(native, root)

    monkeypatch.setattr(native, "_write", desktop_write)
    monkeypatch.setattr(native.launcher, "unload_for_migration", lambda root: False)
    with pytest.raises(RemError, match="did not unload"):
        native.install(root, default_config())
    assert not native.launcher.removed
    assert native.definition(root)["status"] == "PAUSED"


def test_saved_time_change_requires_reapplying_the_native_rule(native, tmp_path):
    root = tmp_path / "notes"
    config = default_config()
    native._write(root, native.render(root, config))
    adopt(native, root)
    config["schedule"]["times"] = ["12:34"]
    atomic_write(root / "config.yaml", yaml.safe_dump(config))
    assert not native.describe(root)["active"]
    assert "run co rem start" in native.describe(root)["reason"]


def test_verified_paused_adoption_precedes_legacy_removal_then_activation(native, tmp_path, monkeypatch):
    root = tmp_path / "notes"
    write = native._write
    states = []

    def desktop_write(root, data):
        states.append((data["status"], native.launcher.removed))
        write(root, data)
        adopt(native, root)

    monkeypatch.setattr(native, "_write", desktop_write)
    result = native.install(root, default_config())
    assert states == [("PAUSED", False), ("ACTIVE", True)]
    assert result["scheduler"] == "codex-native"
    assert native.describe(root)["active"] is True
    assert native.uninstall(root)
    assert native.definition(root)["status"] == "PAUSED"
    assert not native.describe(root)["active"]


def test_foreign_id_or_copied_root_cannot_be_overwritten_or_stopped(native, tmp_path):
    root = tmp_path / "a"
    data = native.render(root, default_config())
    data["cwds"] = [str(tmp_path / "b")]
    native._write(root, data)
    before = native.definition_path(root).read_bytes()
    with pytest.raises(RemError, match="another notebook"):
        native.uninstall(root)
    assert native.definition_path(root).read_bytes() == before
    assert automation_id(root) != automation_id(tmp_path / "b")


def test_updated_file_is_not_adopted_until_native_index_agrees(native, tmp_path):
    root = tmp_path / "notes"
    data = native.render(root, default_config())
    native._write(root, data)
    adopt(native, root)
    assert native.describe(root)["active"]
    data["updated_at"] += 1
    native._write(root, data)
    assert not native.describe(root)["loaded"]


def test_activation_requires_desktop_acknowledgement(native, tmp_path, monkeypatch):
    root = tmp_path / "notes"
    write = native._write

    def paused_only(root, data):
        write(root, data)
        if data["status"] == "PAUSED":
            adopt(native, root)

    monkeypatch.setattr(native, "_write", paused_only)
    with pytest.raises(RemError, match="activation.*not confirmed"):
        native.install(root, default_config())


def test_active_registration_without_a_next_run_is_not_an_armed_timer(native, tmp_path, monkeypatch):
    root = tmp_path / "notes"
    write = native._write

    def no_next_run(root, data):
        write(root, data)
        adopt(native, root)
        with sqlite3.connect(native.home / "sqlite" / "codex-dev.db") as connection:
            connection.execute("UPDATE automations SET next_run_at = NULL")

    monkeypatch.setattr(native, "_write", no_next_run)
    with pytest.raises(RemError, match="activation.*not confirmed"):
        native.install(root, default_config())


def test_pause_cannot_report_success_while_desktop_still_observes_active(native, tmp_path):
    root = tmp_path / "notes"
    native._write(root, native.render(root, default_config()))
    adopt(native, root)
    with pytest.raises(RemError, match="pause.*not confirmed"):
        native.uninstall(root)
    info = native.describe(root)
    assert info["observed_active"] is True
    assert info["desired_status"] == "PAUSED"
    assert info["loaded"] is False


def migrate_index(native, root, *, status="ACTIVE"):
    native._write(root, native.render(root, default_config()))
    adopt(native, root)
    database = native.home / "sqlite" / "codex-dev.db"
    with sqlite3.connect(database) as connection:
        connection.execute("ALTER TABLE automations ADD COLUMN legacy_automation_id TEXT")
        connection.execute("ALTER TABLE automations ADD COLUMN account_id TEXT")
        connection.execute("UPDATE automations SET id=?, legacy_automation_id=?, account_id=?, status=?",
                           ("canonical-rem-id", automation_id(root), "test-account", status))
    native.definition_path(root).unlink()


def test_account_migration_is_discovered_without_recreating_a_legacy_file(native, tmp_path):
    root = tmp_path / "notes"
    migrate_index(native, root)
    assert native.installed(root)
    info = native.describe(root)
    assert info["automation_id"] == "canonical-rem-id"
    assert info["storage"] == "account" and info["observed_active"] is True
    with pytest.raises(RemError, match="Scheduled"):
        native.install(root, default_config())
    with pytest.raises(RemError, match="Scheduled"):
        native.uninstall(root)
    assert not native.definition_path(root).exists()


def test_cached_account_pause_cannot_substitute_for_authoritative_confirmation(native, tmp_path):
    root = tmp_path / "notes"
    migrate_index(native, root, status="PAUSED")
    with pytest.raises(RemError, match="not been confirmed"):
        native.uninstall(root)
    assert not native.definition_path(root).exists()


def test_stopped_file_cannot_hide_an_active_orphan_index(native, tmp_path):
    root = tmp_path / "notes"
    native._write(root, native.render(root, default_config()))
    adopt(native, root)
    native.definition_path(root).unlink()
    assert native.describe(root)["observed_active"]
    with pytest.raises(RemError, match="pause it in Scheduled"):
        native.uninstall(root)


def test_repeated_confirmed_pause_needs_no_new_file_adoption(native, tmp_path):
    root = tmp_path / "notes"
    native._write(root, native.render(root, default_config(), active=False))
    adopt(native, root)
    before = native.definition_path(root).read_bytes()
    assert native.uninstall(root)
    assert native.definition_path(root).read_bytes() == before


def test_desktop_is_opened_normally_when_needed_for_initialization(native, tmp_path, monkeypatch):
    root = tmp_path / "notes"
    commands = []
    write = native._write

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, int(command[0] == "pgrep"))

    def desktop_write(root, data):
        write(root, data)
        adopt(native, root)

    native.run = run
    monkeypatch.setattr("connectonion.rem.codex_schedule.desktop_app", lambda: Path("/Applications/Codex.app"))
    monkeypatch.setattr(native, "_write", desktop_write)
    native.install(root, default_config())
    assert ["/usr/bin/open", "-a", "/Applications/Codex.app", "codex://automations"] in commands


def test_registration_opens_scheduled_even_when_desktop_is_running(native, monkeypatch):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(native, "run", run)
    monkeypatch.setattr("connectonion.rem.codex_schedule.desktop_app", lambda: Path("/Applications/Codex.app"))
    native._open_desktop()
    assert commands == [["/usr/bin/open", "-a", "/Applications/Codex.app", "codex://automations"]]


def test_launchd_cannot_start_before_a_native_pause_is_confirmed(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(CodexNative, "installed", lambda self, root: True)

    def unconfirmed(self, root):
        raise RemError("Native pause was not confirmed")

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(CodexNative, "uninstall", unconfirmed)
    launcher = Launchd(tmp_path / "agents", run=run)
    with pytest.raises(RemError, match="not confirmed"):
        launcher.install(tmp_path / "notes", default_config())
    assert not commands
    assert not launcher.plist_path(tmp_path / "notes").exists()


def test_stop_does_not_mark_worker_disabled_when_native_pause_is_unconfirmed(native, tmp_path, monkeypatch):
    from connectonion.rem.service import stop, worker_state
    root = tmp_path / "notes"
    write_json(state_path(root, "worker.json"), {"enabled": True, "scheduler": "codex-native"})
    native._write(root, native.render(root, default_config()))
    adopt(native, root)
    with pytest.raises(RemError, match="not confirmed"):
        stop(root, scheduler=native)
    assert worker_state(root)["enabled"] is True


def test_a_concurrent_activation_cannot_acknowledge_this_pause(native, tmp_path, monkeypatch):
    from connectonion.rem.service import stop, worker_state
    root = tmp_path / "notes"
    write_json(state_path(root, "worker.json"), {"enabled": True, "scheduler": "codex-native"})
    native._write(root, native.render(root, default_config()))
    adopt(native, root)
    wait = native._wait_for_definition

    def concurrent_activation(root, expected):
        other = native.definition(root)
        other.update(status="ACTIVE", updated_at=expected["updated_at"] + 1)
        native._write(root, other)
        adopt(native, root)
        return wait(root, expected)

    monkeypatch.setattr(native, "_wait_for_definition", concurrent_activation)
    with pytest.raises(RemError, match="changed while waiting"):
        stop(root, scheduler=native)
    assert native.describe(root)["observed_active"] is True
    assert worker_state(root)["enabled"] is True


def test_late_activation_is_visible_even_without_a_worker_provider(native, tmp_path, monkeypatch):
    from connectonion.rem.service import _state_line
    from zoneinfo import ZoneInfo
    root = tmp_path / "notes"
    write_json(state_path(root, "consent.json"), {})
    write = native._write

    def paused_only(root, data):
        write(root, data)
        if data["status"] == "PAUSED":
            adopt(native, root)

    monkeypatch.setattr(native, "_write", paused_only)
    with pytest.raises(RemError, match="activation.*not confirmed"):
        native.install(root, default_config())
    adopt(native, root)
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setenv("CODEX_HOME", str(native.home))
    text, slot = _state_line(root, default_config(), ZoneInfo("Australia/Sydney"))
    assert "without a confirmed worker registration" in text and "Stopped" not in text


def test_failed_reactivation_cannot_hide_behind_a_previously_stopped_worker(native, tmp_path, monkeypatch):
    from connectonion.rem.service import _state_line
    from zoneinfo import ZoneInfo
    root = tmp_path / "notes"
    native.launcher.present = False
    write_json(state_path(root, "consent.json"), {})
    write_json(state_path(root, "worker.json"), {"enabled": False, "scheduler": "codex-native"})
    native._write(root, native.render(root, default_config(), active=False))
    adopt(native, root)
    write = native._write

    def paused_only(root, data):
        write(root, data)
        if data["status"] == "PAUSED":
            adopt(native, root)

    monkeypatch.setattr(native, "_write", paused_only)
    with pytest.raises(RemError, match="activation.*not confirmed"):
        native.install(root, default_config())
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setenv("CODEX_HOME", str(native.home))
    text, slot = _state_line(root, default_config(), ZoneInfo("Australia/Sydney"))
    assert "activation is still pending" in text and "Stopped" not in text


@pytest.mark.parametrize("provider,enabled", [(None, False), ("codex-native", False),
                                             ("codex-native", True), ("launchd", True)])
@pytest.mark.parametrize("desired,observed,storage", [("ACTIVE", False, "file"),
                                                     ("PAUSED", True, "file"),
                                                     (None, False, "account")])
def test_status_never_says_stopped_for_pending_active_or_account_unknown_task(
        tmp_path, monkeypatch, provider, enabled, desired, observed, storage):
    from connectonion.rem.service import _state_line
    from zoneinfo import ZoneInfo
    root = tmp_path / "notes"
    write_json(state_path(root, "consent.json"), {})
    write_json(state_path(root, "worker.json"), {"enabled": enabled, "scheduler": provider})
    info = {"installed": True, "loaded": False, "active": False, "app_running": True,
            "desired_status": desired, "observed_active": observed, "storage": storage,
            **({"reason": "Account registration needs confirmation"} if storage == "account" else {})}
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(CodexNative, "installed", lambda self, root: True)
    monkeypatch.setattr(CodexNative, "describe", lambda self, root: info)
    text, slot = _state_line(root, default_config(), ZoneInfo("Australia/Sydney"))
    assert "Background needs attention" in text and "Stopped" not in text


def test_provider_selection_keeps_track_of_active_account_task(native, tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setenv("CODEX_HOME", str(native.home))
    monkeypatch.setattr(Launchd, "installed", lambda self, root: True)
    root = tmp_path / "notes"
    migrate_index(native, root)
    config = default_config()
    config["runner"] = "coai"
    atomic_write(root / "config.yaml", yaml.safe_dump(config))
    assert isinstance(default_scheduler(root), CodexNative)


def test_status_cannot_hide_a_native_timer_behind_a_stopped_worker(tmp_path, monkeypatch):
    from connectonion.rem.service import _state_line
    from zoneinfo import ZoneInfo
    root = tmp_path / "notes"
    write_json(state_path(root, "consent.json"), {})
    write_json(state_path(root, "worker.json"), {"enabled": False, "scheduler": "codex-native"})
    monkeypatch.setattr(CodexNative, "describe", lambda self, root: {"observed_active": True})
    text, slot = _state_line(root, default_config(), ZoneInfo("Australia/Sydney"))
    assert "still reports" in text and "Stopped" not in text


def test_stopped_worker_cannot_claim_account_authority_from_a_cached_pause(tmp_path, monkeypatch):
    from connectonion.rem.service import _state_line
    from zoneinfo import ZoneInfo
    root = tmp_path / "notes"
    write_json(state_path(root, "consent.json"), {})
    write_json(state_path(root, "worker.json"), {"enabled": False, "scheduler": "codex-native"})
    info = {"observed_active": False, "storage": "account", "reason": "account registration needs confirmation"}
    monkeypatch.setattr(CodexNative, "describe", lambda self, root: info)
    text, slot = _state_line(root, default_config(), ZoneInfo("Australia/Sydney"))
    assert "needs confirmation" in text and "Stopped" not in text


def test_default_prefers_native_for_codex_with_app_and_stop_finds_saved_provider(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setattr("connectonion.rem.codex_schedule.app_installed", lambda: True)
    root = tmp_path / "notes"
    assert isinstance(default_scheduler(root, for_start=True), CodexNative)
    config = default_config()
    config["runner"] = "coai"
    atomic_write(root / "config.yaml", yaml.safe_dump(config))
    assert isinstance(default_scheduler(root, for_start=True), Launchd)
    native = CodexNative()
    native._write(root, native.render(root, config, active=False))
    assert isinstance(default_scheduler(root), CodexNative)


def test_different_desktop_timezone_retains_the_existing_os_scheduler(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setattr("connectonion.rem.codex_schedule.app_installed", lambda: True)
    monkeypatch.setattr("connectonion.rem.codex_schedule.desktop_timezone", lambda: "Asia/Kathmandu")
    assert isinstance(default_scheduler(tmp_path / "notes", for_start=True), Launchd)


@pytest.mark.parametrize("moment,expected", [
    ("2026-10-04T03:10:00+11:00", "2026-10-03T02:30:00+10:00"),
    ("2026-10-04T03:40:00+11:00", "2026-10-04T03:30:00+11:00"),
    ("2026-04-05T02:45:00+11:00", "2026-04-05T02:30:00+11:00"),
    ("2026-04-05T02:15:00+10:00", "2026-04-05T02:30:00+11:00")])
def test_dst_slot_is_never_in_the_future_and_repeated_hour_is_served_once(moment, expected):
    from datetime import datetime, timezone
    from connectonion.rem.service import latest_slot
    config = default_config()
    config["schedule"]["times"] = ["02:30"]
    now = datetime.fromisoformat(moment)
    slot = latest_slot(config, now)
    assert slot.isoformat() == expected
    assert slot.astimezone(timezone.utc) <= now.astimezone(timezone.utc)


@pytest.mark.parametrize("state,fragment", [({}, "waiting for Codex"),
    ({"app_running": False}, "open Codex desktop"),
    ({"loaded": True, "active": True, "next_run_at": 1900000000000}, "first execution not yet verified"),
    ({"loaded": True, "active": True, "next_run_at": 1}, "has not triggered")])
def test_status_distinguishes_saved_registered_and_triggered(tmp_path, monkeypatch, state, fragment):
    from connectonion.rem.service import _state_line
    from zoneinfo import ZoneInfo
    root = tmp_path / "notes"
    write_json(state_path(root, "consent.json"), {})
    write_json(state_path(root, "worker.json"), {"enabled": True, "scheduler": "codex-native"})
    native_state = {"installed": True, "loaded": False, "active": False, "app_running": True, **state}
    monkeypatch.setattr(CodexNative, "describe", lambda self, root: native_state)
    text, slot = _state_line(root, default_config(), ZoneInfo("Australia/Sydney"))
    assert fragment in text
