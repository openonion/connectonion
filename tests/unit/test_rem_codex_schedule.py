"""Native registration, ownership and migration contracts; no real user tasks."""

import json
import plistlib
import sqlite3
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

from connectonion.rem.codex_schedule import CodexNative, automation_id, recurrence
from connectonion.rem.config import default_config
from connectonion.rem.files import RemError, atomic_write, state_path, write_json
from connectonion.rem.schedule import Launchd, default_scheduler, label_for, wake_command


class Launcher:
    def __init__(self, *, state="waiting", installed=True):
        self.state, self.present, self.removed = state, installed, False
        self.wake = False

    def installed(self, root):
        return self.present

    def describe(self, root):
        return {"installed": self.present, "loaded": self.present, "state": self.state}

    def uninstall(self, root):
        self.present, self.removed = False, True
        return True

    def unload_for_migration(self, root):
        return self.uninstall(root)

    def install_wake(self, root, config, app):
        self.wake = True
        return root / "wake.plist"

    def uninstall_wake(self, root):
        removed, self.wake = self.wake, False
        return removed

    def describe_wake(self, root):
        return {"installed": self.wake, "loaded": self.wake}


def running(command, **kwargs):
    return subprocess.CompletedProcess(command, 0, stdout="123\n")


@pytest.fixture(autouse=True)
def known_timezone(monkeypatch):
    monkeypatch.setattr("connectonion.rem.config.local_timezone", lambda: "Australia/Sydney")
    monkeypatch.setattr("connectonion.rem.codex_schedule.desktop_timezone", lambda: "Australia/Sydney")
    initialize = CodexNative.__init__

    def isolated_native(self, *args, **kwargs):
        kwargs.setdefault("run", running)
        initialize(self, *args, **kwargs)

    monkeypatch.setattr(CodexNative, "__init__", isolated_native)


@pytest.fixture
def native(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.rem.codex_schedule._checkout_path", lambda: "")
    monkeypatch.setattr("connectonion.rem.codex_schedule.desktop_app", lambda: Path("/Applications/Codex.app"))
    return CodexNative(tmp_path / "codex", launcher=Launcher(),
                       command=["/venv with spaces/bin/python", "-m", "connectonion.cli.main"],
                       run=running, wait_seconds=0)


def adopt(native, root, database_name="codex.db"):
    """A private test index, standing in for desktop file adoption."""
    definition = native.definition(root)
    database = native.home / "sqlite" / database_name
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS automations "
                           "(id TEXT PRIMARY KEY, rrule TEXT, status TEXT, cwds TEXT, "
                           "updated_at INTEGER, next_run_at INTEGER, last_run_at INTEGER)")
        connection.execute("INSERT OR REPLACE INTO automations VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (definition["id"], definition["rrule"], definition["status"],
                            json.dumps(definition["cwds"]), definition["updated_at"],
                            1900000000000 if definition["status"] == "ACTIVE" else None, None))


@pytest.mark.parametrize("desktop_table", ["active", "empty", "missing", "absent"])
def test_desktop_index_is_authoritative_unless_its_table_is_missing(native, tmp_path, desktop_table):
    root = tmp_path / "notes"
    native._write(root, native.render(root, default_config()))
    adopt(native, root, "codex-dev.db")
    database = native.home / "sqlite" / "codex.db"
    if desktop_table != "absent":
        with sqlite3.connect(database) as connection:
            if desktop_table != "missing":
                connection.execute("ATTACH DATABASE ? AS old", (str(database.with_name("codex-dev.db")),))
                connection.execute("CREATE TABLE automations AS SELECT * FROM old.automations")
                connection.execute("UPDATE automations SET next_run_at = 1900000060000")
                if desktop_table == "empty":
                    connection.execute("DELETE FROM automations")
    before = {path: path.read_bytes() for path in database.parent.glob("*.db")}
    row = native._indexed(root)
    if desktop_table == "empty":
        assert row == {}, "a stale dev row must not resurrect a removed desktop task"
    else:
        expected = 1900000060000 if desktop_table == "active" else 1900000000000
        assert row["next_run_at"] == expected
    assert {path: path.read_bytes() for path in database.parent.glob("*.db")} == before


def test_unknown_desktop_schema_is_not_replaced_by_a_stale_dev_index(native, tmp_path):
    root = tmp_path / "notes"
    native._write(root, native.render(root, default_config()))
    adopt(native, root, "codex-dev.db")
    with sqlite3.connect(native.home / "sqlite" / "codex.db") as connection:
        connection.execute("CREATE TABLE automations (id TEXT)")
    with pytest.raises(RemError, match="Unrecognized native automation index"):
        native._indexed(root)


def test_index_connections_are_read_only(native, tmp_path, monkeypatch):
    root = tmp_path / "notes"
    native._write(root, native.render(root, default_config()))
    adopt(native, root)
    connect, calls = sqlite3.connect, []

    def read_only(database, **kwargs):
        calls.append((database, kwargs))
        return connect(database, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", read_only)
    assert native._indexed(root)
    assert all(database.endswith("codex.db?mode=ro") and kwargs["uri"] for database, kwargs in calls)


def test_native_runner_is_used_for_wake_job_operations(tmp_path):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="")

    native = CodexNative(tmp_path / "codex", run=run)
    native.launcher.install_wake(tmp_path / "notes", default_config(), Path("/Applications/Codex.app"))
    assert native.launcher.describe_wake(tmp_path / "notes")["loaded"]
    assert native.launcher.uninstall_wake(tmp_path / "notes")
    assert {command[1] for command in commands} == {"bootstrap", "bootout", "print"}


def test_launchd_migration_uses_its_injected_wake_job_runner(native, tmp_path, monkeypatch):
    root = tmp_path / "notes"
    monkeypatch.setenv("CODEX_HOME", str(native.home))
    native._write(root, native.render(root, default_config(), active=False))
    adopt(native, root)
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="")

    launcher = Launchd(tmp_path / "LaunchAgents", uid=501, run=run, command=["/venv/bin/co"])
    wake_path = launcher.install_wake(root, default_config(), Path("/Applications/Codex.app"))
    launcher.install(root, default_config())
    assert not wake_path.exists()
    assert ["launchctl", "bootout", f"gui/501/{label_for(root)}.wake"] in commands
    assert launcher.plist_path(root).is_file()


@pytest.mark.parametrize("action", ["stop", "migrate"])
def test_deleted_native_task_does_not_leave_an_orphan_wake_job(tmp_path, monkeypatch, action):
    from connectonion.rem.service import stop
    root = tmp_path / "notes"
    commands = []
    initialize = Launchd.__init__

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="")

    def isolated_launcher(self, **kwargs):
        initialize(self, agents_dir=tmp_path / "LaunchAgents", uid=501, run=run)

    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setattr(Launchd, "__init__", isolated_launcher)
    launcher = Launchd()
    native = CodexNative(launcher=launcher)
    wake_path = launcher.install_wake(root, default_config(), Path("/Applications/Codex.app"))
    assert not native.definition_path(root).exists() and not native._indexed(root)
    commands.clear()
    if action == "stop":
        stop(root, scheduler=launcher)
    else:
        launcher.install(root, default_config())
    assert not wake_path.exists()
    assert ["launchctl", "bootout", f"gui/501/{label_for(root)}.wake"] in commands


@pytest.mark.parametrize("storage", ["account", "orphan"])
def test_missed_index_rows_remain_visible_without_a_file_definition(native, tmp_path, storage):
    root = tmp_path / "notes"
    if storage == "account":
        migrate_index(native, root)
    else:
        native._write(root, native.render(root, default_config()))
        adopt(native, root)
        native.definition_path(root).unlink()
    with sqlite3.connect(native.home / "sqlite" / "codex.db") as connection:
        connection.execute("UPDATE automations SET next_run_at = 1")
    assert "Codex missed the " in native.describe(root)["reason"]


@pytest.mark.parametrize("worker", [{}, {"enabled": False, "scheduler": "codex-native"}])
def test_pending_worker_registration_keeps_the_missed_slot_diagnosis(native, tmp_path, monkeypatch, worker):
    from zoneinfo import ZoneInfo
    from connectonion.rem.service import _state_line
    from connectonion.cli.commands.rem_status import status_next
    root = tmp_path / "notes"
    native._write(root, native.render(root, default_config()))
    adopt(native, root)
    with sqlite3.connect(native.home / "sqlite" / "codex.db") as connection:
        connection.execute("UPDATE automations SET next_run_at = 1")
    info = native.describe(root)
    write_json(state_path(root, "consent.json"), {})
    write_json(state_path(root, "worker.json"), worker)
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(CodexNative, "installed", lambda self, root: True)
    monkeypatch.setattr(CodexNative, "describe", lambda self, root: info)
    text, slot = _state_line(root, default_config(), ZoneInfo("Australia/Sydney"))
    assert "Codex missed the " in text
    assert status_next({"configured": True, "state": text, "next_run": slot}) == (["stop"] if worker else ["start"])


def test_native_install_saves_only_a_background_desktop_wake_job(native, tmp_path, monkeypatch):
    root = tmp_path / "notes"
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, int(command[1] == "print"), stdout="")

    native.launcher = Launchd(tmp_path / "LaunchAgents", uid=501, run=run)
    write = native._write

    def desktop_write(root, data):
        write(root, data)
        adopt(native, root)

    monkeypatch.setattr(native, "_write", desktop_write)
    config = default_config()
    config["schedule"]["times"] = ["03:15", "17:45"]
    native.install(root, config)
    path = tmp_path / "LaunchAgents" / f"{label_for(root)}.wake.plist"
    assert path.is_file(), "native tasks need a launchd job to reopen a closed desktop"
    job = plistlib.loads(path.read_bytes())
    assert job["Label"] == label_for(root) + ".wake"
    assert job["ProgramArguments"] == wake_command(Path("/Applications/Codex.app"))
    assert job["StartCalendarInterval"] == [{"Hour": 3, "Minute": 0}, {"Hour": 17, "Minute": 30}]
    assert not job.get("RunAtLoad") and "StartInterval" not in job
    assert path.stat().st_mode & 0o777 == 0o600
    assert ["launchctl", "bootstrap", "gui/501", str(path)] in commands
    assert not native.launcher.plist_path(root).exists()
    config["schedule"]["times"] = ["12:34"]
    native.install(root, config)
    assert plistlib.loads(path.read_bytes())["StartCalendarInterval"] == [{"Hour": 12, "Minute": 19}]
    assert len(list(path.parent.glob("*.plist"))) == 1
    assert native.uninstall(root)
    assert not path.exists()
    assert ["launchctl", "bootout", f"gui/501/{label_for(root)}.wake"] in commands


@pytest.mark.parametrize("app_running", [False, True])
@pytest.mark.parametrize("wake_loaded", [False, True])
@pytest.mark.parametrize("late_minutes", [30, 31])
def test_missed_slot_is_visible_in_describe_and_status(
        native, tmp_path, monkeypatch, app_running, wake_loaded, late_minutes):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from connectonion.rem.service import _state_line
    from connectonion.cli.commands.rem_status import _header, status_next

    root = tmp_path / "notes"
    slot = datetime.fromisoformat("2026-10-30T17:00:00+11:00")
    current = slot + timedelta(minutes=late_minutes)
    monkeypatch.setattr("connectonion.rem.codex_schedule.time.time", lambda: current.timestamp())
    monkeypatch.setattr("connectonion.rem.service.now", lambda: current)
    monkeypatch.setattr(native, "_app_running", lambda: app_running)
    native.launcher = Launchd(tmp_path / "LaunchAgents", run=lambda command, **kw:
                              subprocess.CompletedProcess(command, 0 if wake_loaded else 1, stdout=""))
    native._write(root, native.render(root, default_config()))
    adopt(native, root)
    with sqlite3.connect(native.home / "sqlite" / "codex.db") as connection:
        connection.execute("UPDATE automations SET next_run_at = ?", (int(slot.timestamp() * 1000),))
    info = native.describe(root)
    assert info["wake_loaded"] is wake_loaded
    missed = "Codex missed the 17:00 slot (was the desktop app closed?)"
    assert "Codex desktop was not running" not in info.get("reason", "")
    if late_minutes == 30:
        assert missed not in info.get("reason", "")
        return
    assert missed in info["reason"]
    assert ("wake job loaded" if wake_loaded else "wake job not loaded") in info["reason"]
    write_json(state_path(root, "consent.json"), {})
    write_json(state_path(root, "worker.json"), {"enabled": True, "scheduler": "codex-native"})
    monkeypatch.setattr(CodexNative, "describe", lambda self, root: info)
    text, next_run = _state_line(root, default_config(), ZoneInfo("Australia/Sydney"))
    assert missed in text
    value = {"configured": True, "state": text, "next_run": next_run}
    assert "Codex missed the 17:00 slot" in "\n".join(_header(value, "co rem"))
    assert status_next(value) == ["start"]


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
    assert "next --scheduled" in saved["prompt"] and "rem/SKILL.md" in saved["prompt"] and saved["cwds"] == [str(root.resolve())]
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
        with sqlite3.connect(native.home / "sqlite" / "codex.db") as connection:
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
    database = native.home / "sqlite" / "codex.db"
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


def test_install_wakes_scheduled_after_native_adoption_before_handover(native, tmp_path, monkeypatch):
    root = tmp_path / "notes"
    wake_states = []
    write = native._write

    def run(command, **kwargs):
        if command[0] == "/usr/bin/open":
            wake_states.append((native.definition(root).get("status"), native.launcher.removed))
        return subprocess.CompletedProcess(command, 0)

    def desktop_write(root, data):
        write(root, data)
        adopt(native, root)

    native.run = run
    monkeypatch.setattr(native, "_write", desktop_write)
    native.install(root, default_config())
    assert wake_states == [("PAUSED", False)]


def test_migration_during_scheduled_open_keeps_the_previous_clock(native, tmp_path, monkeypatch):
    root = tmp_path / "notes"
    write = native._write

    def desktop_write(root, data):
        write(root, data)
        adopt(native, root)

    def open_and_migrate():
        migrate_index(native, root, status="PAUSED")

    monkeypatch.setattr(native, "_write", desktop_write)
    monkeypatch.setattr(native, "_open_desktop", open_and_migrate)
    with pytest.raises(RemError, match="Scheduled"):
        native.install(root, default_config())
    assert not native.launcher.removed
    assert native.launcher.present
    assert not native.definition_path(root).exists()
    assert native.describe(root)["storage"] == "account"


@pytest.mark.parametrize("definition_changed", [False, True])
def test_changed_registration_during_scheduled_open_keeps_previous_clock(native, tmp_path, monkeypatch, definition_changed):
    root = tmp_path / "notes"
    write = native._write

    def desktop_write(root, data):
        write(root, data)
        adopt(native, root)

    def change_registration():
        if definition_changed:
            changed = native.definition(root)
            changed["updated_at"] += 1
            write(root, changed)
        else:
            with sqlite3.connect(native.home / "sqlite" / "codex.db") as connection:
                connection.execute("UPDATE automations SET updated_at = updated_at + 1")

    monkeypatch.setattr(native, "_write", desktop_write)
    monkeypatch.setattr(native, "_open_desktop", change_registration)
    with pytest.raises(RemError, match="changed"):
        native.install(root, default_config())
    assert not native.launcher.removed
    assert native.launcher.present
    assert native.definition(root)["status"] == "PAUSED"


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
    ({"loaded": True, "active": True, "next_run_at": 1,
      "reason": "Codex missed the 17:00 slot (was the desktop app closed?); wake job loaded"}, "missed the 17:00 slot")])
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


@pytest.mark.skipif(sys.platform != "darwin", reason="the wake job is a macOS launchd job")
def test_the_wake_job_leaves_a_running_codex_alone_and_opens_a_closed_one(tmp_path):
    app = tmp_path / "Codex Test.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    # Not a real app: if the job reaches open, open fails, so its exit code shows which branch ran.
    closed = subprocess.run(wake_command(app), capture_output=True)
    assert closed.returncode != 0, "a closed app must be opened"

    # A process whose command line is the app's executable, as ps shows Codex's.
    running = subprocess.Popen([str(app / "Contents" / "MacOS" / "Codex"), "30"], executable="/bin/sleep")
    try:
        assert subprocess.run(wake_command(app), capture_output=True).returncode == 0
    finally:
        running.kill()
        running.wait()


def test_the_wake_job_opens_codex_before_the_slot_codex_may_fire_early(tmp_path):
    """2026-11-03: Codex scheduled the 19:00 slot for 18:55:51; a wake job at
    19:00 opened the closed app after it, and the slot was missed."""
    import plistlib
    config = default_config()
    config["schedule"]["times"] = ["00:05", "19:00"]
    launcher = Launchd(tmp_path / "LaunchAgents", uid=501,
                       run=lambda command, **kw: subprocess.CompletedProcess(command, 0, stdout=""))
    path = launcher.install_wake(tmp_path / "notes", config, Path("/Applications/Codex.app"))
    times = plistlib.loads(path.read_bytes())["StartCalendarInterval"]
    assert times == [{"Hour": 23, "Minute": 50}, {"Hour": 18, "Minute": 45}]
