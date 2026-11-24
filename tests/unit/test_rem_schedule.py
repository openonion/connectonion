"""The clock is the OS's; we only write one declarative job file and ask it to load it."""

import os
import plistlib
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from connectonion.rem.config import default_config
from connectonion.rem.files import RemError
from connectonion.rem.schedule import LABEL, Launchd, Unsupported, label_for


pytestmark = pytest.mark.usefixtures("rem_clock")


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
    root = tmp_path / "rem"
    config = default_config()
    config["schedule"]["timezone"] = "Australia/Sydney"
    plist = plistlib.loads(scheduler.render(root, config).encode())
    assert plist["Label"] == label_for(root)
    assert plist["ProgramArguments"] == ["/usr/bin/caffeinate", "-i", "/venv/bin/co",
                                         "rem", "--root", str(root), "sync", "--scheduled"]
    assert "/opt/codex/bin" in plist["EnvironmentVariables"]["PATH"]
    assert "/venv/bin" in plist["EnvironmentVariables"]["PATH"]
    assert plist["StandardErrorPath"].startswith(str(root / ".state"))


def test_the_job_holds_the_mac_awake_while_it_runs(tmp_path, monkeypatch):
    """2026-10-10: a one-page investigation started at 22:19 on a Mac that went
    to 'Maintenance Sleep' at 22:31; it advanced only in the 45-second dark
    wakes each hour, the monotonic deadlines (co ai --timeout, subprocess
    timeout) paused with the clock, and the run read 'running' 80 minutes
    later with three stages done. A 03:00 slot on a sleeping laptop is the
    same run. `caffeinate -i` keeps idle sleep off for exactly as long as the
    job's process lives, and nothing longer."""
    scheduler, _ = make(tmp_path, monkeypatch)
    plist = plistlib.loads(scheduler.render(tmp_path / "rem", default_config()).encode())
    assert plist["ProgramArguments"][:2] == ["/usr/bin/caffeinate", "-i"]
    assert "--scheduled" in plist["ProgramArguments"]


def test_install_writes_a_private_plist_and_bootstraps_it_once(tmp_path, monkeypatch):
    scheduler, calls = make(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    result = scheduler.install(root, default_config())
    path = Path(result["plist"])
    assert path.is_file() and oct(path.stat().st_mode & 0o777) == "0o600"
    assert ["launchctl", "bootstrap", "gui/501", str(path)] in calls.commands
    scheduler.install(root, default_config())  # idempotent: still one file, reloaded not duplicated
    assert len(list(path.parent.glob("*.plist"))) == 1
    assert calls.commands.count(["launchctl", "bootout", f"gui/501/{label_for(root)}"]) >= 1


def test_uninstall_removes_the_job_and_the_file(tmp_path, monkeypatch):
    scheduler, calls = make(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    scheduler.install(root, default_config())
    assert scheduler.uninstall(root) is True
    assert not list((tmp_path / "LaunchAgents").glob("*.plist"))
    assert ["launchctl", "bootout", f"gui/501/{label_for(root)}"] in calls.commands
    assert scheduler.uninstall(root) is False


def test_custom_roots_get_their_own_label():
    custom = label_for(Path("/elsewhere/notes"))
    assert custom.startswith(LABEL + ".") and custom != LABEL


def test_the_default_root_under_another_home_is_another_job(tmp_path, monkeypatch):
    # 1.8.8b11: the default root's label was always ai.openonion.co-rem, and
    # launchd's domain is the uid, not HOME: `co rem stop` under a test HOME
    # booted out the real user's job.
    first = label_for(tmp_path / "a" / ".co" / "rem")
    second = label_for(Path.home() / ".co" / "rem")
    assert LABEL not in (first, second) and first != second
    assert first.startswith(LABEL + ".") and second.startswith(LABEL + ".")


def _legacy_job(agents: Path, root: Path) -> Path:
    """A job installed by 1.8.8b11 or earlier: the bare label, for the default root."""
    agents.mkdir(parents=True, exist_ok=True)
    path = agents / f"{LABEL}.plist"
    path.write_bytes(plistlib.dumps({"Label": LABEL, "ProgramArguments": [
        "/venv/bin/co", "rem", "--root", str(root), "sync", "--scheduled"]}))
    return path


def test_stop_still_removes_a_job_installed_under_the_old_label(tmp_path, monkeypatch):
    scheduler, calls = make(tmp_path, monkeypatch)
    root = Path.home() / ".co" / "rem"
    legacy = _legacy_job(tmp_path / "LaunchAgents", root.resolve())

    assert scheduler.describe(root)["installed"] is True, "an installed old job is still found"
    assert scheduler.uninstall(root) is True
    assert ["launchctl", "bootout", f"gui/501/{LABEL}"] in calls.commands
    assert not legacy.exists()


def test_the_old_label_of_another_root_is_left_alone(tmp_path, monkeypatch):
    scheduler, calls = make(tmp_path, monkeypatch)
    legacy = _legacy_job(tmp_path / "LaunchAgents", Path("/Users/someone-else/.co/rem"))

    scheduler.uninstall(Path.home() / ".co" / "rem")
    scheduler.install(Path.home() / ".co" / "rem", default_config())

    assert ["launchctl", "bootout", f"gui/501/{LABEL}"] not in calls.commands
    assert legacy.exists()


def test_start_replaces_the_old_label_rather_than_running_two_jobs(tmp_path, monkeypatch):
    scheduler, calls = make(tmp_path, monkeypatch)
    root = Path.home() / ".co" / "rem"
    legacy = _legacy_job(tmp_path / "LaunchAgents", root.resolve())

    scheduler.install(root, default_config())

    assert ["launchctl", "bootout", f"gui/501/{LABEL}"] in calls.commands
    assert not legacy.exists()
    assert [p.name for p in (tmp_path / "LaunchAgents").glob("*.plist")] == [f"{label_for(root)}.plist"]


def test_render_failure_keeps_the_old_clock(tmp_path, monkeypatch):
    scheduler, calls = make(tmp_path, monkeypatch)
    root = tmp_path / "notes"
    legacy = _legacy_job(tmp_path / "LaunchAgents", root)

    def invalid_schedule(*args):
        raise RemError("Invalid schedule")

    monkeypatch.setattr(scheduler, "render", invalid_schedule)
    with pytest.raises(RemError, match="Invalid schedule"):
        scheduler.install(root, default_config())
    assert legacy.exists()
    assert not calls.commands


def test_unsupported_platform_says_how_to_run_by_hand(tmp_path):
    with pytest.raises(RemError, match="co rem sync"):
        Unsupported().install(tmp_path, default_config())


def test_job_ticks_on_an_interval_and_on_the_clock(tmp_path, monkeypatch):
    """Each trigger was measured dead on one macOS. 2026-09-07, macOS 26:
    StartCalendarInterval never fired in three experiments, StartInterval to
    the second. 2026-10-11, macOS 14.1: the installed job showed runs = 0 a day
    after install, and a 60 s StartInterval test job ran 0 times in 4 minutes,
    while a calendar job bootstrapped the same way ran every minute. The job
    carries both; a tick that finds nothing due exits at once."""
    from connectonion.rem.schedule import TICK_SECONDS
    scheduler, _ = make(tmp_path, monkeypatch)
    plist = plistlib.loads(scheduler.render(tmp_path / "rem", default_config()).encode())
    assert plist["StartInterval"] == TICK_SECONDS and 60 <= TICK_SECONDS <= 600
    minutes = [entry["Minute"] for entry in plist["StartCalendarInterval"]]
    assert minutes == list(range(0, 60, TICK_SECONDS // 60))
    assert all(set(entry) == {"Minute"} for entry in plist["StartCalendarInterval"])
    assert plist["RunAtLoad"] is False  # the first tick catches up; no batch races the foreground one
    assert plist["ProgramArguments"][-2:] == ["sync", "--scheduled"]


def test_the_job_runs_the_installation_that_installed_it_not_the_first_co_on_path(tmp_path, monkeypatch):
    """A tester ran `venv/bin/co rem start --yes` from a non-activated venv with an
    older co (1.8.8b3) in ~/.local/bin earlier on PATH: the job ran the old one."""
    import sys
    monkeypatch.setattr("shutil.which", lambda name: "/Users/someone/.local/bin/co")
    monkeypatch.setattr(sys, "executable", "/work/venv/bin/python")
    scheduler = Launchd(agents_dir=tmp_path / "LaunchAgents", uid=501, run=Calls())
    root = tmp_path / "rem"
    plist = plistlib.loads(scheduler.render(root, default_config()).encode())
    assert plist["ProgramArguments"] == ["/usr/bin/caffeinate", "-i", "/work/venv/bin/python", "-m",
                                         "connectonion.cli.main", "rem", "--root", str(root), "sync", "--scheduled"]
    assert plist["EnvironmentVariables"]["PATH"].startswith("/work/venv/bin:")


def test_the_job_s_pythonpath_is_the_checkout_running_now_not_the_shell_s(tmp_path, monkeypatch):
    """The owner's job carried PYTHONPATH=".", which the model's co ai resolved
    against .state/tasks: an older installed connectonion (#1974). The live job
    later carried an old session's scratch folder (2026-10-15): with a
    connectonion/__init__.py there it would have shadowed the installed package."""
    import connectonion
    scheduler, _ = make(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", f".{os.pathsep}{tmp_path / 'scratchpad'}")
    plist = plistlib.loads(scheduler.render(tmp_path / "rem", default_config()).encode())
    checkout = str(Path(connectonion.__file__).resolve().parent.parent)
    assert plist["EnvironmentVariables"]["PYTHONPATH"] == checkout


def test_an_installed_package_s_job_has_no_pythonpath(tmp_path, monkeypatch):
    import connectonion
    scheduler, _ = make(tmp_path, monkeypatch)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "scratchpad"))
    monkeypatch.setattr(connectonion, "__file__", "/venv/lib/python3.12/site-packages/connectonion/__init__.py")
    plist = plistlib.loads(scheduler.render(tmp_path / "rem", default_config()).encode())
    assert "PYTHONPATH" not in plist["EnvironmentVariables"]


class SystemdCalls(Calls):
    def __init__(self, *, fail=None, active=True, linger="yes"):
        super().__init__()
        self.fail, self.active, self.linger = fail, active, linger

    def __call__(self, command, **kwargs):
        super().__call__(command, **kwargs)
        if command[0] == "loginctl":
            return CompletedProcess(command, 0, f"Linger={self.linger}\n", "")
        action = command[2]
        output = "NextElapseUSecRealtime=Thu 2026-11-05 03:05:00 UTC\n" if action == "show" else ""
        code = 1 if action == self.fail or action == "is-active" and not self.active else 0
        return CompletedProcess(command, code, output, "Failed to connect to bus" if code else "")


def make_systemd(tmp_path, monkeypatch, **kwargs):
    from connectonion.rem.schedule import Systemd
    monkeypatch.setattr("shutil.which", lambda name: f"/opt/{name}/bin/{name}")
    calls = SystemdCalls(**kwargs)
    return Systemd(units_dir=tmp_path / "units", run=calls, command=["/venv/bin/co"]), calls


def test_systemd_render_runs_the_saved_installation_every_tick(tmp_path, monkeypatch):
    from connectonion.rem.schedule import TICK_SECONDS
    scheduler, _ = make_systemd(tmp_path, monkeypatch)
    root = tmp_path / "my notebook"
    monkeypatch.setattr("connectonion.rem.schedule._checkout_path", lambda: "/work/checkout")
    units = scheduler.render(root, default_config())
    service, timer = units["service"], units["timer"]
    assert f'ExecStart="/venv/bin/co" "rem" "--root" "{root}" "sync" "--scheduled"' in service
    assert "Type=oneshot" in service
    assert 'Environment="PATH=/venv/bin:/opt/codex/bin:/opt/claude/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"' in service
    assert f'Environment="HOME={Path.home()}"' in service
    assert 'Environment="PYTHONPATH=/work/checkout"' in service
    for stream in ("StandardOutput", "StandardError"):
        assert f'{stream}=append:{root}/.state/scheduler.log' in service
    assert f"OnCalendar=*:00/{TICK_SECONDS // 60}" in timer
    assert "Persistent=true" in timer and "WantedBy=timers.target" in timer


def test_systemd_defaults_to_co_command_and_omits_installed_package_pythonpath(tmp_path, monkeypatch):
    scheduler, _ = make_systemd(tmp_path, monkeypatch)
    scheduler.command = None
    monkeypatch.setattr("connectonion.rem.runner.co_command", lambda: ["/venv/bin/python", "-m", "connectonion.cli.main"])
    monkeypatch.setattr("connectonion.rem.schedule._checkout_path", lambda: "")
    service = scheduler.render(tmp_path, default_config())["service"]
    assert 'ExecStart="/venv/bin/python" "-m" "connectonion.cli.main" "rem"' in service
    assert "PYTHONPATH" not in service


def test_systemd_escapes_systemd_specifiers_variables_and_quotes(tmp_path, monkeypatch):
    scheduler, _ = make_systemd(tmp_path, monkeypatch)
    root = tmp_path / 'notes %n $HOME "quoted" \\'
    scheduler.command.append("newline\nnext")
    service = scheduler.render(root, default_config())["service"]
    command = next(line for line in service.splitlines() if line.startswith("ExecStart="))
    assert 'notes %%n $$HOME \\"quoted\\" \\\\' in command
    assert '"newline\\nnext"' in command
    assert "$HOME" not in command.replace("$$HOME", "")


def test_systemd_install_writes_private_units_and_enables_timer(tmp_path, monkeypatch):
    scheduler, calls = make_systemd(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    result = scheduler.install(root, default_config())
    assert result["scheduler"] == "systemd" and result["label"] == label_for(root)
    assert "note" not in result
    paths = [tmp_path / "units" / f"{label_for(root)}.{suffix}" for suffix in ("service", "timer")]
    assert all(path.is_file() and path.stat().st_mode & 0o777 == 0o600 for path in paths)
    assert (root / ".state").is_dir()
    assert calls.commands[:2] == [["systemctl", "--user", "daemon-reload"],
                                 ["systemctl", "--user", "enable", "--now", f"{label_for(root)}.timer"]]
    scheduler.install(root, default_config())
    assert len(list((tmp_path / "units").iterdir())) == 2


def test_systemd_install_holds_the_maintenance_lock(tmp_path, monkeypatch):
    from connectonion.rem.files import maintenance_lock
    scheduler, _ = make_systemd(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    with maintenance_lock(root):
        with pytest.raises(RemError, match="busy"):
            scheduler.install(root, default_config())
    assert not (tmp_path / "units").exists()


@pytest.mark.parametrize("action", ["daemon-reload", "enable"])
def test_systemd_install_failure_explains_how_to_restore_the_user_bus(tmp_path, monkeypatch, action):
    scheduler, _ = make_systemd(tmp_path, monkeypatch, fail=action)
    with pytest.raises(RemError, match="systemctl --user") as error:
        scheduler.install(tmp_path / "rem", default_config())
    assert "loginctl enable-linger" in str(error.value) and "bus" in str(error.value)


def test_systemd_install_notes_when_linger_is_off(tmp_path, monkeypatch):
    scheduler, _ = make_systemd(tmp_path, monkeypatch, linger="no")
    result = scheduler.install(tmp_path / "rem", default_config())
    assert "loginctl enable-linger" in result["note"] and "logged out" in result["note"]


def test_systemd_uninstall_disables_and_removes_both_units(tmp_path, monkeypatch):
    scheduler, calls = make_systemd(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    scheduler.install(root, default_config())
    assert scheduler.installed(root)
    assert scheduler.uninstall(root) is True
    assert not scheduler.installed(root) and not list((tmp_path / "units").iterdir())
    assert calls.commands[-2:] == [["systemctl", "--user", "disable", "--now", f"{label_for(root)}.timer"],
                                  ["systemctl", "--user", "daemon-reload"]]
    assert scheduler.uninstall(root) is False


@pytest.mark.parametrize("active", [True, False])
def test_systemd_describe_reports_timer_health_and_next_tick(tmp_path, monkeypatch, active):
    scheduler, _ = make_systemd(tmp_path, monkeypatch, active=active)
    root = tmp_path / "rem"
    scheduler.install(root, default_config())
    info = scheduler.describe(root)
    assert info["scheduler"] == "systemd" and info["label"] == label_for(root)
    assert info["installed"] and info["loaded"] is active and info["active"] is active
    assert info["next_run"] == "Thu 2026-11-05 03:05:00 UTC"
    assert info["log"] == str(root / ".state/scheduler.log")


def test_default_scheduler_selects_systemd_only_on_linux_with_systemctl(monkeypatch):
    from connectonion.rem.schedule import default_scheduler
    monkeypatch.setattr("connectonion.rem.schedule.sys.platform", "linux")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/systemctl" if name == "systemctl" else None)
    assert type(default_scheduler()).__name__ == "Systemd"
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert isinstance(default_scheduler(), Unsupported)
    monkeypatch.setattr("connectonion.rem.schedule.sys.platform", "win32")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/systemctl")
    assert isinstance(default_scheduler(), Unsupported)


def test_unsupported_scheduler_no_longer_claims_scheduling_is_macos_only(tmp_path):
    with pytest.raises(RemError) as error:
        Unsupported().install(tmp_path, default_config())
    assert "macOS-only" not in str(error.value) and "cron" in str(error.value)
