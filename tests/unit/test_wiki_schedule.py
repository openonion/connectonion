"""The clock is the OS's; we only write one declarative job file and ask it to load it."""

import plistlib
from pathlib import Path

import pytest

from connectonion.wiki.config import default_config
from connectonion.wiki.files import WikiError
from connectonion.wiki.schedule import LABEL, Launchd, Unsupported, label_for


class Calls:
    def __init__(self):
        self.commands = []

    def __call__(self, command, **kwargs):
        self.commands.append(list(command))

        class Done:
            returncode = 0
            stdout = ""
            stderr = ""
        return Done()


def make(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/opt/codex/bin/codex" if name == "codex" else None)
    calls = Calls()
    scheduler = Launchd(agents_dir=tmp_path / "LaunchAgents", uid=501, run=calls, python="/venv/bin/python")
    return scheduler, calls


def test_plist_runs_scheduled_sync_with_a_path_that_can_find_codex(tmp_path, monkeypatch):
    scheduler, _ = make(tmp_path, monkeypatch)
    root = tmp_path / "wiki"
    config = default_config()
    config["schedule"]["timezone"] = "Australia/Sydney"
    plist = plistlib.loads(scheduler.render(root, config).encode())
    assert plist["Label"] == label_for(root)
    assert plist["ProgramArguments"] == ["/venv/bin/python", "-m", "connectonion.cli.main",
                                         "wiki", "--root", str(root), "sync", "--scheduled"]
    assert "/opt/codex/bin" in plist["EnvironmentVariables"]["PATH"]
    assert "/venv/bin" in plist["EnvironmentVariables"]["PATH"]
    assert plist["StandardErrorPath"].startswith(str(root / ".state"))


def test_install_writes_a_private_plist_and_bootstraps_it_once(tmp_path, monkeypatch):
    scheduler, calls = make(tmp_path, monkeypatch)
    root = tmp_path / "wiki"
    result = scheduler.install(root, default_config())
    path = Path(result["plist"])
    assert path.is_file() and oct(path.stat().st_mode & 0o777) == "0o600"
    assert ["launchctl", "bootstrap", "gui/501", str(path)] in calls.commands
    scheduler.install(root, default_config())  # idempotent: still one file, reloaded not duplicated
    assert len(list(path.parent.glob("*.plist"))) == 1
    assert calls.commands.count(["launchctl", "bootout", f"gui/501/{label_for(root)}"]) >= 1


def test_uninstall_removes_the_job_and_the_file(tmp_path, monkeypatch):
    scheduler, calls = make(tmp_path, monkeypatch)
    root = tmp_path / "wiki"
    scheduler.install(root, default_config())
    assert scheduler.uninstall(root) is True
    assert not list((tmp_path / "LaunchAgents").glob("*.plist"))
    assert ["launchctl", "bootout", f"gui/501/{label_for(root)}"] in calls.commands
    assert scheduler.uninstall(root) is False


def test_custom_roots_get_their_own_label():
    assert label_for(Path.home() / ".co" / "wiki") == LABEL
    custom = label_for(Path("/elsewhere/notes"))
    assert custom.startswith(LABEL + ".") and custom != LABEL


def test_unsupported_platform_says_how_to_run_by_hand(tmp_path):
    with pytest.raises(WikiError, match="co wiki sync"):
        Unsupported().install(tmp_path, default_config())


def test_job_ticks_on_an_interval_and_never_relies_on_calendar_triggers(tmp_path, monkeypatch):
    """Measured 2026-09-07 on macOS 26: StartCalendarInterval (array or dict form) never fired
    in three experiments; StartInterval fired every time to the second. The clock is ours."""
    from connectonion.wiki.schedule import TICK_SECONDS
    scheduler, _ = make(tmp_path, monkeypatch)
    plist = plistlib.loads(scheduler.render(tmp_path / "wiki", default_config()).encode())
    assert plist["StartInterval"] == TICK_SECONDS and 60 <= TICK_SECONDS <= 600
    assert "StartCalendarInterval" not in plist
    assert plist["RunAtLoad"] is False  # the first tick catches up; no batch races the foreground one
    assert plist["ProgramArguments"][-2:] == ["sync", "--scheduled"]
