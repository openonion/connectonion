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
    scheduler = Launchd(agents_dir=tmp_path / "LaunchAgents", uid=501, run=calls, command=["/venv/bin/co"])
    return scheduler, calls


def test_plist_runs_scheduled_daily_with_a_path_that_can_find_codex(tmp_path, monkeypatch):
    scheduler, _ = make(tmp_path, monkeypatch)
    root = tmp_path / "wiki"
    config = default_config()
    config["schedule"]["timezone"] = "Australia/Sydney"
    plist = plistlib.loads(scheduler.render(root, config).encode())
    assert plist["Label"] == label_for(root)
    assert plist["ProgramArguments"] == ["/venv/bin/co",
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
    custom = label_for(Path("/elsewhere/notes"))
    assert custom.startswith(LABEL + ".") and custom != LABEL


def test_the_default_root_under_another_home_is_another_job(tmp_path, monkeypatch):
    # 1.8.8b11: the default root's label was always ai.openonion.co-wiki, and
    # launchd's domain is the uid, not HOME: `co wiki stop` under a test HOME
    # booted out the real user's job.
    first = label_for(tmp_path / "a" / ".co" / "wiki")
    second = label_for(Path.home() / ".co" / "wiki")
    assert LABEL not in (first, second) and first != second
    assert first.startswith(LABEL + ".") and second.startswith(LABEL + ".")


def _legacy_job(agents: Path, root: Path) -> Path:
    """A job installed by 1.8.8b11 or earlier: the bare label, for the default root."""
    agents.mkdir(parents=True, exist_ok=True)
    path = agents / f"{LABEL}.plist"
    path.write_bytes(plistlib.dumps({"Label": LABEL, "ProgramArguments": [
        "/venv/bin/co", "wiki", "--root", str(root), "sync", "--scheduled"]}))
    return path


def test_stop_still_removes_a_job_installed_under_the_old_label(tmp_path, monkeypatch):
    scheduler, calls = make(tmp_path, monkeypatch)
    root = Path.home() / ".co" / "wiki"
    legacy = _legacy_job(tmp_path / "LaunchAgents", root.resolve())

    assert scheduler.describe(root)["installed"] is True, "an installed old job is still found"
    assert scheduler.uninstall(root) is True
    assert ["launchctl", "bootout", f"gui/501/{LABEL}"] in calls.commands
    assert not legacy.exists()


def test_the_old_label_of_another_root_is_left_alone(tmp_path, monkeypatch):
    scheduler, calls = make(tmp_path, monkeypatch)
    legacy = _legacy_job(tmp_path / "LaunchAgents", Path("/Users/someone-else/.co/wiki"))

    scheduler.uninstall(Path.home() / ".co" / "wiki")
    scheduler.install(Path.home() / ".co" / "wiki", default_config())

    assert ["launchctl", "bootout", f"gui/501/{LABEL}"] not in calls.commands
    assert legacy.exists()


def test_start_replaces_the_old_label_rather_than_running_two_jobs(tmp_path, monkeypatch):
    scheduler, calls = make(tmp_path, monkeypatch)
    root = Path.home() / ".co" / "wiki"
    legacy = _legacy_job(tmp_path / "LaunchAgents", root.resolve())

    scheduler.install(root, default_config())

    assert ["launchctl", "bootout", f"gui/501/{LABEL}"] in calls.commands
    assert not legacy.exists()
    assert [p.name for p in (tmp_path / "LaunchAgents").glob("*.plist")] == [f"{label_for(root)}.plist"]


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


def test_the_job_runs_the_installation_that_installed_it_not_the_first_co_on_path(tmp_path, monkeypatch):
    """A tester ran `venv/bin/co wiki start --yes` from a non-activated venv with an
    older co (1.8.8b3) in ~/.local/bin earlier on PATH: the job ran the old one."""
    import sys
    monkeypatch.setattr("shutil.which", lambda name: "/Users/someone/.local/bin/co")
    monkeypatch.setattr(sys, "executable", "/work/venv/bin/python")
    scheduler = Launchd(agents_dir=tmp_path / "LaunchAgents", uid=501, run=Calls())
    root = tmp_path / "wiki"
    plist = plistlib.loads(scheduler.render(root, default_config()).encode())
    assert plist["ProgramArguments"] == ["/work/venv/bin/python", "-m", "connectonion.cli.main",
                                         "wiki", "--root", str(root), "sync", "--scheduled"]
    assert plist["EnvironmentVariables"]["PATH"].startswith("/work/venv/bin:")
