"""OS clocks for REM: launchd exec or Codex desktop on macOS, systemd on Linux.

Exec uses exact saved fire times and follow-ups. Legacy child-runner jobs use
five-minute ticks so sync can coalesce due slots in the saved timezone.
launchd skips a job still running at its next fire; exec also holds a process
lock so a manual fire or replacement job cannot overlap the previous turn.
"""

import hashlib
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .files import RemError

LABEL = "ai.openonion.co-rem"
OLD_LABEL = "ai.openonion.co-wiki"  # jobs installed by `co wiki start`, 1.8.8-1.8.9 (#1932)
TICK_SECONDS = 300  # a slot is served within five minutes of its time; a no-op tick is cheap


def default_root() -> Path:
    return (Path.home() / ".co" / "rem").resolve()


def label_for(root: Path) -> str:
    # Every root, the default one included, is named by its resolved path.
    # launchd's domain is the uid, not HOME: when the default root's label was
    # the bare LABEL, `co rem stop` under a test HOME booted out the real
    # user's job (1.8.8b11). Jobs installed under the bare label are still found
    # and stopped through Launchd._legacy.
    root = Path(root).resolve()
    return LABEL + "." + hashlib.sha256(str(root).encode()).hexdigest()[:12]


def _checkout_path() -> str:
    """The source checkout running now, or '' for an installed package.

    Not the installing shell's PYTHONPATH: the live job carried a scratch
    folder from an old session (2026-10-15), harmless only because it had no
    connectonion/__init__.py -- with one it would have shadowed the installed
    package every five minutes."""
    if getattr(sys, "frozen", False):
        return ""
    import connectonion
    checkout = Path(connectonion.__file__).resolve().parent.parent
    return "" if {"site-packages", "dist-packages"} & set(checkout.parts) else str(checkout)


# Codex fires a slot a few minutes either side of it: on 2026-11-03 the 19:00
# slot was due at 18:55:51 and the 03:00 one ran at 02:57. A wake job at the
# slot itself opened a closed app after that moment, and the slot was missed.
WAKE_LEAD_MINUTES = 15


def wake_time(value: str) -> dict:
    """The launchd time that opens Codex WAKE_LEAD_MINUTES before a "HH:MM" slot."""
    hour, minute = map(int, value.split(":"))
    hour, minute = divmod((hour * 60 + minute - WAKE_LEAD_MINUTES) % (24 * 60), 60)
    return {"Hour": hour, "Minute": minute}


def wake_command(app: Path) -> list[str]:
    """Open Codex only when it is closed.

    Opening an app that is already running sends it a reopen event, which can
    bring up a window in the middle of whatever the user is doing. The pattern
    is anchored so it matches Codex's own executable, not this shell.
    A hidden launch (-j) gets no automation ticks; -g keeps the window visible
    without bringing it to the foreground.
    """
    # pgrep reads POSIX extended regex: re.escape's "\-" and "\ " are not valid there.
    literal = re.sub(r"([.\[\]()*+?{}|^$\\])", r"\\\1", str(app))
    running = shlex.quote("^" + literal + "/Contents/MacOS/")
    return ["/bin/sh", "-c",
            f"/usr/bin/pgrep -qf {running} || /usr/bin/open -g -a {shlex.quote(str(app))}"]


class Launchd:
    """macOS LaunchAgent for the current user; no root, survives logout/login."""

    def __init__(self, agents_dir=None, uid=None, run=subprocess.run, command=None):
        self.agents_dir = Path(agents_dir or Path.home() / "Library" / "LaunchAgents")
        self.uid = os.getuid() if uid is None else uid
        self.run = run
        self.command = command

    def plist_path(self, root: Path) -> Path:
        return self.agents_dir / f"{label_for(root)}.plist"

    def _legacy(self, root: Path):
        """The plist of a job 1.8.8b11 or earlier installed under the bare LABEL
        for this root, or None. Only when its own --root is this root: under
        another HOME the bare label is someone else's job."""
        path = self.agents_dir / f"{LABEL}.plist"
        try:
            arguments = plistlib.loads(path.read_bytes()).get("ProgramArguments") or []
        except (OSError, plistlib.InvalidFileException, ValueError):
            return None
        for index, argument in enumerate(arguments[:-1]):
            if argument == "--root" and Path(arguments[index + 1]).resolve() == Path(root).resolve():
                return path
        return None

    def _remove_legacy(self, root: Path) -> bool:
        path = self._legacy(root)
        if path is None:
            return False
        self._launchctl("bootout", f"gui/{self.uid}/{LABEL}")
        path.unlink()
        return True

    def remove_old(self, root: Path) -> bool:
        """Stop and delete any job `co wiki start` installed for this notebook.

        It runs `co wiki ... sync`, which only prints the new name from 1.9.0
        on, so left alone the daily update would fail every night (#1932).
        """
        removed = False
        for path in sorted(self.agents_dir.glob(f"{OLD_LABEL}*.plist")):
            try:
                job = plistlib.loads(path.read_bytes())
            except (OSError, plistlib.InvalidFileException, ValueError):
                continue
            arguments = job.get("ProgramArguments") or []
            roots = [arguments[i + 1] for i, a in enumerate(arguments[:-1]) if a == "--root"]
            if roots and Path(roots[0]).resolve() == Path(root).resolve():
                self._launchctl("bootout", f"gui/{self.uid}/{job.get('Label', path.stem)}")
                path.unlink()
                removed = True
        return removed

    def render(self, root: Path, config: dict) -> str:
        from .runner import co_command
        root = Path(root).resolve()
        # The installation running `co rem start`, not the first co on PATH:
        # a non-activated venv with an older co in ~/.local/bin installed a
        # job that ran the older one every day (seen on 1.8.8b7).
        command = self.command or co_command()
        # Resolve the CLI and delegate binaries when installing, before launchd's sparse PATH.
        dirs = [str(Path(command[0]).parent)]
        for name in ("codex", "claude"):
            binary = shutil.which(name)
            if binary:
                dirs.append(str(Path(binary).parent))
        dirs += os.environ.get("PATH", "").split(os.pathsep)
        dirs += ["/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
        env = {"PATH": ":".join(dict.fromkeys(dirs)), "HOME": str(Path.home())}
        env.update({key: os.environ[key] for key in ("CODEX_HOME", "CODEX_CMD") if os.environ.get(key)})
        pythonpath = _checkout_path()
        if pythonpath:
            # The job must run the same connectonion the user is running now; a
            # development checkout only exists on PYTHONPATH. Absolute: the
            # owner's job carried ".", and the model's co ai, run from
            # .state/tasks, imported an older connectonion (#1974).
            env["PYTHONPATH"] = pythonpath
        job = {
            "Label": label_for(root),
            # caffeinate -i: no idle sleep while this process lives. A sleeping
            # laptop runs a slot only in its 45-second dark wakes, and every
            # monotonic deadline pauses with it (2026-10-10, one page, 80 min).
            "ProgramArguments": ["/usr/bin/caffeinate", "-i", *command,
                                 "rem", "--root", str(root), "sync", "--scheduled"],
            "StartInterval": TICK_SECONDS,
            "StartCalendarInterval": [{"Minute": minute} for minute in range(0, 60, TICK_SECONDS // 60)],
            "RunAtLoad": False,
            "ProcessType": "Background",
            "EnvironmentVariables": env,
            "StandardOutPath": str(root / ".state" / "launchd.log"),
            "StandardErrorPath": str(root / ".state" / "launchd.log"),
        }
        return plistlib.dumps(job, sort_keys=False).decode()

    def _launchctl(self, *args) -> bool:
        result = self.run(["launchctl", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        return result.returncode == 0

    def install(self, root: Path, config: dict) -> dict:
        from .files import maintenance_lock
        root = Path(root).resolve()
        with maintenance_lock(root):
            return self._install(root, config)

    def _install(self, root: Path, config: dict) -> dict:
        from .codex_schedule import CodexNative
        native = CodexNative(launcher=self, run=self.run)
        if native.installed(root):
            native.uninstall(root)
            if config['schedule']['runner'] == 'codex-exec':
                native.definition_path(root).unlink(missing_ok=True)
        path = self.plist_path(root)
        self._write_plist(path, self.render(root, config))
        self._remove_legacy(root)  # one job per root, not the old label beside the new
        self._load(path)
        from .codex_schedule import app_installed, desktop_timezone
        note = ("The saved timezone differs from Codex's local clock; launchd keeps the saved timezone."
                if config.get("runner") == "codex" and app_installed()
                and config["schedule"]["timezone"] != desktop_timezone() else "")
        return {"scheduler": "launchd", "label": label_for(root), "plist": str(path),
                "times": list(config["schedule"]["times"]), **({"note": note} if note else {})}

    def _write_plist(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".co-rem-", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(text)
        os.chmod(name, 0o600)
        os.replace(name, path)

    def _load(self, path: Path) -> None:
        # bootout first so a changed schedule is reloaded rather than ignored.
        self._launchctl("bootout", f"gui/{self.uid}/{path.stem}")
        if not self._launchctl("bootstrap", f"gui/{self.uid}", str(path)):
            raise RemError("launchctl could not load the job; check ~/Library/LaunchAgents and run `co rem doctor`")

    def wake_path(self, root: Path) -> Path:
        return self.agents_dir / f"{label_for(root)}.wake.plist"

    def install_wake(self, root: Path, config: dict, app: Path) -> Path:
        """Open Codex shortly before each saved local time; only Codex executes REM."""
        path = self.wake_path(root)
        from .codex_schedule import fire_times
        times = [wake_time(value) for value in fire_times(config)]
        job = {"Label": path.stem, "ProgramArguments": wake_command(app),
               "StartCalendarInterval": times, "RunAtLoad": False, "ProcessType": "Background"}
        self._write_plist(path, plistlib.dumps(job, sort_keys=False).decode())
        self._load(path)
        return path

    def uninstall_wake(self, root: Path) -> bool:
        return self._unload(self.wake_path(root))

    def describe_wake(self, root: Path) -> dict:
        path = self.wake_path(root)
        return self._describe(path, path.stem)

    def unload_for_migration(self, root: Path) -> bool:
        """Keep the plist as ownership/recovery evidence if launchctl cannot unload."""
        path = self.plist_path(root)
        if path.is_file():
            arguments = plistlib.loads(path.read_bytes()).get("ProgramArguments") or []
            roots = [arguments[i + 1] for i, item in enumerate(arguments[:-1]) if item == "--root"]
            if path.is_symlink() or roots != [str(Path(root).resolve())]:
                raise RemError("The existing launchd definition belongs to another notebook; nothing was unloaded")
        info = self.describe(root)
        if info.get("loaded"):
            self._launchctl("bootout", f"gui/{self.uid}/{info['label']}")
            if self.describe(root).get("loaded"):
                return False
        self.uninstall(root)
        return True

    def uninstall(self, root: Path) -> bool:
        root = Path(root).resolve()
        removed_legacy = self._remove_legacy(root)
        return self._unload(self.plist_path(root)) or removed_legacy

    def _unload(self, path: Path) -> bool:
        self._launchctl("bootout", f"gui/{self.uid}/{path.stem}")
        if not path.exists():
            return False
        path.unlink()
        return True

    def installed(self, root: Path) -> bool:
        """Is a job for this root, and not another, on disk? No launchctl call."""
        return self.plist_path(root).is_file() or self._legacy(root) is not None

    def describe(self, root: Path) -> dict:
        """What launchd itself says -- the plist being present is not the job being alive."""
        root = Path(root).resolve()
        label = label_for(root)
        if not self.plist_path(root).is_file() and self._legacy(root) is not None:
            label = LABEL  # installed before labels named the root; stop still removes it
        path = self.agents_dir / f"{label}.plist"
        return self._describe(path, label)

    def _describe(self, path: Path, label: str) -> dict:
        info = {"scheduler": "launchd", "label": label, "installed": path.is_file()}
        result = self.run(["launchctl", "print", f"gui/{self.uid}/{label}"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        info["loaded"] = result.returncode == 0
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("state = "):
                info["state"] = line.split("=", 1)[1].strip()
            elif line.startswith("last exit code = "):
                info["last_exit_code"] = line.split("=", 1)[1].strip()
            elif line.startswith("runs = "):
                info["runs"] = int(line.split("=", 1)[1])
        return info


class CodexExec(Launchd):
    """launchd owns the clock; a separate lock spans the whole Codex turn."""

    def render(self, root: Path, config: dict) -> str:
        from .codex_schedule import desktop_timezone, fire_times
        from .codex_exec import _codex_command
        if config['schedule']['timezone'] != desktop_timezone():
            raise RemError('codex-exec fire times use this computer’s timezone; set schedule.timezone to the local timezone')
        root = Path(root).resolve()
        job = plistlib.loads(super().render(root, config).encode())
        job['ProgramArguments'] = ['/usr/bin/caffeinate', '-i', sys.executable,
                                   '-m', 'connectonion.rem.codex_exec', '--root', str(root)]
        job.pop('StartInterval')
        job['StartCalendarInterval'] = [dict(zip(('Hour', 'Minute'), map(int, t.split(':'))))
                                        for t in fire_times(config)]
        if os.environ.get('CODEX_HOME'):
            job['EnvironmentVariables']['CODEX_HOME'] = os.environ['CODEX_HOME']
        # Pin the delegate, not only PATH: login-shell overrides and launchd's
        # later environment must never redirect this job back to its launcher.
        delegate = _codex_command()
        job['EnvironmentVariables']['CODEX_CMD'] = delegate[0] if len(delegate) == 1 else shlex.join(delegate)
        return plistlib.dumps(job, sort_keys=False).decode()

    def _install(self, root, config):
        from .codex_schedule import CodexNative
        lagging = CodexNative(launcher=self, run=self.run).pause_for_exec(root)
        path = self.plist_path(root)
        self._write_plist(path, self.render(root, config))
        self._remove_legacy(root)
        self._load(path)
        note = ("Desktop task paused in its definition; Codex will pick it up." if lagging else "")
        return {"scheduler": "codex-exec", "label": label_for(root), "plist": str(path),
                "times": list(config["schedule"]["times"]), **({"note": note} if note else {})}

    def install(self, root: Path, config: dict) -> dict:
        from .runner import ready
        problem, fix = ready({**config, 'runner': 'codex'})
        if problem:
            raise RemError(f'{problem}; {fix}')
        # Validate before pausing the other clock.
        self.render(root, config)
        result = super().install(root, config)
        return {**result, 'runner': 'codex-exec',
                'note': ' '.join(filter(None, [result.get('note'),
                    'Codex exec keeps working across tasks in one turn; desktop automation turns can end early. Keep this computer awake.']))}

    def describe(self, root: Path) -> dict:
        from .files import read_json, state_path
        return {**super().describe(root), 'runner': 'codex-exec',
                'last_turn': read_json(state_path(root, 'last-turn.json'), None)}


class Systemd:
    """Linux user timer; no root, with linger needed to run while logged out."""

    def __init__(self, units_dir=None, run=subprocess.run, command=None):
        self.units_dir = Path(units_dir or Path.home() / ".config/systemd/user")
        self.run = run
        self.command = command

    def unit_path(self, root: Path, suffix: str) -> Path:
        return self.units_dir / f"{label_for(root)}.{suffix}"

    @staticmethod
    def _quote(value: str) -> str:
        # Unit specifiers expand even inside quotes. ExecStart also expands $
        # (escaped separately below); Environment does not.
        escaped = value.replace("%", "%%").translate(str.maketrans({
            "\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t",
        }))
        return '"' + escaped + '"'

    def _environment(self, command: list[str]) -> dict:
        dirs = [str(Path(command[0]).parent)]
        for name in ("codex", "claude"):
            binary = shutil.which(name)
            if binary:
                dirs.append(str(Path(binary).parent))
        dirs += ["/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
        env = {"PATH": ":".join(dict.fromkeys(dirs)), "HOME": str(Path.home())}
        env.update({key: os.environ[key] for key in ("CODEX_HOME", "CODEX_CMD") if os.environ.get(key)})
        pythonpath = _checkout_path()
        if pythonpath:
            env["PYTHONPATH"] = pythonpath
        return env

    def render(self, root: Path, config: dict) -> dict:
        from .runner import co_command
        root = Path(root).resolve()
        command = self.command or co_command()
        arguments = [*command, "rem", "--root", str(root), "sync", "--scheduled"]
        execute = " ".join(self._quote(arg.replace("$", "$$")) for arg in arguments)
        env = ["Environment=" + self._quote(f"{key}={value}")
               for key, value in self._environment(command).items()]
        # StandardOutput/StandardError take raw paths, not quoted words.
        log = str(root / ".state/scheduler.log").replace("%", "%%")
        if "\n" in log or "\r" in log:
            raise RemError("systemd scheduling requires a notebook path without line breaks")
        service = "\n".join([
            "[Unit]", "Description=ConnectOnion REM maintenance", "", "[Service]",
            "Type=oneshot", f"ExecStart={execute}", *env,
            f"StandardOutput=append:{log}", f"StandardError=append:{log}", "",
        ])
        timer = "\n".join([
            "[Unit]", "Description=ConnectOnion REM tick", "", "[Timer]",
            f"OnCalendar=*:00/{TICK_SECONDS // 60}", "Persistent=true", "",
            "[Install]", "WantedBy=timers.target", "",
        ])
        return {"service": service, "timer": timer}

    def _systemctl(self, *args):
        return self.run(["systemctl", "--user", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)

    def _check(self, *args) -> None:
        result = self._systemctl(*args)
        if result.returncode:
            raise RemError(f"systemctl --user {' '.join(args)} failed: {result.stderr.strip()}. "
                           "Log into a systemd user session and check `systemctl --user status`; "
                           "for a missing user bus or logged-out operation, run `loginctl enable-linger` "
                           "for your user, then retry `co rem start`")

    def _write_unit(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".co-rem-", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(text)
        os.chmod(name, 0o600)
        os.replace(name, path)

    def install(self, root: Path, config: dict) -> dict:
        from .files import maintenance_lock
        root = Path(root).resolve()
        with maintenance_lock(root):
            for suffix, content in self.render(root, config).items():
                self._write_unit(self.unit_path(root, suffix), content)
            self._check("daemon-reload")
            self._check("enable", "--now", f"{label_for(root)}.timer")
        info = {"scheduler": "systemd", "label": label_for(root),
                "service": str(self.unit_path(root, "service")), "timer": str(self.unit_path(root, "timer")),
                "times": list(config["schedule"]["times"])}
        if shutil.which("loginctl"):
            linger = self.run(["loginctl", "show-user", str(os.getuid()), "-p", "Linger"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
            if linger.returncode == 0 and linger.stdout.strip() != "Linger=yes":
                info["note"] = "Run `loginctl enable-linger` to keep the systemd user timer running while logged out."
        return info

    def uninstall(self, root: Path) -> bool:
        paths = [self.unit_path(root, suffix) for suffix in ("service", "timer")]
        removed = any(path.exists() for path in paths)
        # Do not mark a live timer stopped if the user manager cannot disable it.
        if removed:
            self._check("disable", "--now", f"{label_for(root)}.timer")
        else:
            self._systemctl("disable", "--now", f"{label_for(root)}.timer")
        for path in paths:
            path.unlink(missing_ok=True)
        self._check("daemon-reload")
        return removed

    def installed(self, root: Path) -> bool:
        return all(self.unit_path(root, suffix).is_file() for suffix in ("service", "timer"))

    def describe(self, root: Path) -> dict:
        label = label_for(root)
        active = self._systemctl("is-active", f"{label}.timer").returncode == 0
        info = {"scheduler": "systemd", "label": label, "installed": self.installed(root),
                "loaded": active, "active": active, "log": str(Path(root).resolve() / ".state/scheduler.log")}
        result = self._systemctl("show", f"{label}.timer", "-p", "NextElapseUSecRealtime")
        if result.returncode == 0:
            value = result.stdout.strip().removeprefix("NextElapseUSecRealtime=")
            if value and value != "n/a":
                info["next_run"] = value
        return info


def exec_round(root, *, scheduled=True, stage=None, say=None):
    """One round under the notebook's turn lock; `busy`, with nothing started, when another run holds it."""
    from .catchup import resume
    from .codex_exec import BUSY, NotebookBusy, round_lock
    try:
        with round_lock(root), resume(root, scheduled=scheduled):
            result = _exec_round(root, scheduled=scheduled, stage=stage, say=say)
            return finish_exec(root, result, stage=stage, say=say)
    except NotebookBusy:
        return {"outcome": "busy", "reason": BUSY}


def deepen_round(root, *, stage=None, say=None, **choice):
    """The one round-driven caller of the unchanged deepen slot, with run logs."""
    from . import depth
    from ..cli.commands.rem_commands import _depth_stage
    return depth.slot(root, stage=stage or _depth_stage, say=say, **choice)


def calendar_round(root, *, native=False):
    """Save Agenda then the day plan; native tasks share one save per round."""
    import traceback
    from .calendar import save_upcoming
    from .config import read_config
    from .daily import _log_calendar_faults
    from .files import WRITE_WAIT_SECONDS, maintenance_lock, read_json, state_path, write_json
    from .service import notebook_zone, now
    path = state_path(root, 'round.json')
    if native:
        with maintenance_lock(root, wait=WRITE_WAIT_SECONDS):
            cursor = read_json(path, {})
            if not cursor:
                return None
            if 'calendar' in cursor:
                return cursor['calendar']
            cursor['calendar'] = {'stopped': 'calendar read interrupted'}
            write_json(path, cursor)
    moment = now()
    try:
        result = save_upcoming(root, moment, notebook_zone(read_config(root)))
    except Exception as error:  # A failed snapshot must never stop the round, including a save fault.
        result = {'events': 0, 'read': [], 'capped': [], 'errors': {'rem': {
            'reason': 'bug', 'at': now().isoformat(), 'error': type(error).__name__,
            'traceback': traceback.format_exc()}}}
    _log_calendar_faults(root, result)
    result['day_plan'] = _day_plan_round(root, moment)
    result['todos'] = _todos_round(root, moment)
    from .weather import night as weather_night
    result['weather'] = weather_night(root, moment)  # the week's forecast for Agenda; never stops the round
    if native:
        with maintenance_lock(root, wait=WRITE_WAIT_SECONDS):
            current = read_json(path, {})
            if _round_identity(current) == _round_identity(cursor):
                current['calendar'] = result
                write_json(path, current)
    return result


def _todos_round(root, moment):
    """His open to-dos, saved beside the calendar (#3087). A fault in REM is a failed run with its traceback
    in `co rem logs`, out of the round's result; no failure stops the rest of the night."""
    import traceback
    from .config import read_config
    from .daily import _reserve
    from .files import write_json
    from .service import notebook_zone
    from .todos import save
    try:
        result = save(root, moment, notebook_zone(read_config(root)))
    except Exception as error:  # same background isolation as the calendar snapshot
        result = {'tasks': 0, 'error': {'reason': 'bug', 'at': moment.isoformat(), 'error': type(error).__name__},
                  'traceback': traceback.format_exc()}
    if 'traceback' in result:
        record, path = _reserve(root, 'todos', 0, {})
        record.update(outcome='failed', error='to-dos: ' + result.pop('traceback'), finished_at=moment.isoformat())
        write_json(path, record)
    return result


def _day_plan_round(root, moment):
    """A plan save fault is logged by name and never stops the rest of the night."""
    import traceback
    from .day_plan import save
    from .daily import _reserve
    from .files import write_json
    try:
        return save(root, moment)
    except Exception as error:  # same background isolation as the calendar snapshot
        record, path = _reserve(root, 'day-plan', 0, {})
        record.update(outcome='failed', error=traceback.format_exc(), finished_at=moment.isoformat())
        write_json(path, record)
        return {'stopped': f'day plan save failed: {type(error).__name__}'}


def _depth_due(root, cursor):
    if not cursor.get('done') or cursor.get('phase') == 'daily-translation':
        return False
    return _night_produced(root)


def _night_produced(root):
    """A catchup night has written, translated or drafted something; the schedule's night is not asked."""
    from .catchup import _counts, number
    night = number(root)
    if night is None:
        return True
    counts = _counts(root, night)
    return any(counts[name] for name in ('written', 'translated', 'drafts'))


def _depth_early(root, cursor):
    """The round has served its first portion of investigation and is still going.

    2026-11-16: the slot started only after a completed round, and at 20 to 60 minutes
    an investigation turn a night was cut short long before that, so nothing was deepened.
    `_depth_due`'s question (did the night write, translate or draft anything) is not
    asked here: a night that served a portion is working, and its first page may be an
    hour from written. A night with nothing to investigate has no portion and still
    meets that question after its round. Not due once the slot is claimed: only the
    call that ran it reports it here; the completed round reports it once more.

    2026-11-17: the closing translation goes on until no page waits, which is hours. A
    round with no portion (nothing to investigate, or investigation held by its weekly
    budget) starts the slot once that pass has begun (`closing`), and there it is asked
    `_depth_due`'s question, since no portion has shown the night to be working."""
    started = cursor.get('portions') or (cursor.get('closing') and _night_produced(root))
    return (bool(started) and 'depth' not in cursor and not cursor.get('done')
            and cursor.get('phase') != 'daily-translation')


def _open_pages(root, cursor):
    """The pages the round is in the middle of: deepening one would change it under its own draft."""
    from .files import read_json, state_path
    jobs, index = cursor.get('jobs') or [], cursor.get('job_index', 0)
    opened = cursor.get('current') or cursor.get('project_quote')
    pending = read_json(state_path(root, f"tasks/{cursor['pending']}/task.json"), {}) if cursor.get('pending') else {}
    records = [jobs[index]['record'] if opened and index < len(jobs) else '', pending.get('record') or '']
    return sorted({record for record in records if record})


def _depth_slot(root, due, *, stage=None, say=None):
    """Claim the round's one deepen slot when `due`, run it and save it; None when it is not due.

    The writer lock is not held across the worker calls. A slot that already ran, or was
    interrupted, is not run again: its saved result is returned."""
    from .config import read_config
    from .files import WRITE_WAIT_SECONDS, maintenance_lock, read_json, state_path, write_json
    from .native_round import overnight_wave_policy
    if overnight_wave_policy(read_config(root)) != "full":
        return None
    path = state_path(root, 'round.json')
    with maintenance_lock(root, wait=WRITE_WAIT_SECONDS):
        cursor = read_json(path, {})
        if not due(root, cursor):
            return None
        if 'depth' in cursor:
            return cursor['depth']
        cursor['depth'] = {'stopped': 'deepening interrupted'}
        write_json(path, cursor)
    skip = _open_pages(root, cursor)
    depth = deepen_round(root, stage=stage, say=say, **({'skip': skip} if skip else {}))
    with maintenance_lock(root, wait=WRITE_WAIT_SECONDS):
        current = read_json(path, {})
        if _round_identity(current) == _round_identity(cursor):
            current['depth'] = depth
            write_json(path, current)
    return depth


def early_depth(root, *, stage=None, say=None):
    """The round's deepen slot, between two tasks, once its first portion of investigation is done."""
    return _depth_slot(root, _depth_early, stage=stage, say=say)


def _round_identity(cursor):
    return (cursor.get('run', {}).get('id'), cursor.get('started_at'), cursor.get('catchup_night'))


def finish_exec(root, result, *, stage=None, say=None):
    """Save the calendar, then give a completed round its deepen slot unless it ran early."""
    if result.get('outcome') != 'skipped' and result.get('reason') != 'not due':
        calendar = calendar_round(root, native=True)
        if calendar is not None:
            result = {**result, 'calendar': calendar}
    if result.get('outcome') != 'done' or result.get('reason') != 'round done':
        return result
    depth = _depth_slot(root, _depth_due, stage=stage, say=say)
    return result if depth is None else {**result, 'depth': depth}


def _exec_round(root, *, scheduled, stage=None, say=None):
    from . import native, runner
    from .codex_schedule import CodexNative
    from .config import read_config
    if scheduled and CodexNative().recent_desktop_fire(root):
        return {"outcome": "skipped", "reason": "desktop automation fired in the last 10 minutes"}
    parked, refused, faults, depth = [], {}, 0, None
    task = _prepare(root, native, scheduled=scheduled)
    while task.get("outcome") == "task" or task.get("fault"):
        if task["outcome"] == "task":
            if scheduled and CodexNative().recent_desktop_fire(root):
                return {"outcome": "skipped", "reason": "desktop automation fired in the last 10 minutes"}
            from .inquiry import stage_config
            config = stage_config(root, read_config(root), task["stage"].removesuffix(" (repair)"))
            task = _run_one(root, native, runner, task, config, refused)
        faults = faults + 1 if task.get("fault") else 0
        if task.get("outcome") == "parked":
            parked.append({key: task.get(key) for key in ("record", "reason", "candidate")})
        if faults == TASK_FAULTS_IN_A_ROW:
            task = {"outcome": "stopped", "reason": f"{faults} tasks in a row could not be run, so the round stopped; "
                    f"the last: {task['reason'].removeprefix('parked: ')}"}
        elif task.get("outcome") != "task":
            # After a refusal this offers the same task again with its required
            # corrections first, as `co rem next` does for the scheduled agent. The
            # task a worker's own `co rem next` prepared is this round's to take too.
            own = task.get("outcome") == "refused" or task.get("settled_by") == "worker"
            if not own:
                # Between two tasks, never inside one that is being repaired.
                depth = early_depth(root, stage=stage, say=say) or depth
            task = _prepare(root, native, scheduled=scheduled, own=own)
    return {**task, **({"parked": parked} if parked else {}), **({"depth": depth} if depth else {})}


def _prepare(root, native, *, scheduled, own=False):
    """The next task; a preparation past its deadline is that one page's fault, as a turn past its own is.

    2026-11-16: ten minutes "searching project documents" for one person's page
    ended a catchup night with exit 75 and no totals. The page is parked by
    name when the stall is raised, so the next call prepares other work; a wait
    that was not a page's (new mail) is counted and gone past the same way."""
    try:
        return native.next_task(root, scheduled=scheduled, own=own, in_round=True)
    except native.PreparationStalled as error:
        reason = "parked: " + str(error) if error.record else str(error)
        return {"outcome": "parked" if error.record else "stalled", "record": error.record, "reason": reason,
                "candidate": None, "fault": True}


# One task's fault is parked and the round goes on. Two in a row is no longer about
# the pages (the network is down, every turn times out): stopping keeps the rest of
# the round's pages from being parked one by one for a day each.
TASK_FAULTS_IN_A_ROW = 2


def _run_one(root, native, runner, task, config, refused):
    """Run one task and settle it; what is wrong with this one task alone parks it.

    2026-11-16: any error from one task's submit ended the night. Only the two kinds
    that name one task are caught: a submit that cannot settle it (`TaskFault`: it is
    no longer pending, or its inputs changed while the worker ran) and a turn past
    its deadline (`TimedOut`). A runner that cannot start or does not complete, a
    lock held elsewhere, an unreadable notebook and a refused model are about the
    round: they are raised, and catchup reports them and starts no further night."""
    used = None
    try:
        used = runner.run_task(Path(task["material"]), native.driven_prompt(task), config, task["stage"]).get("usage")
        return _settle(root, native, task["id"], native.settle(root, task["id"], usage=used), refused)
    except (native.TaskFault, runner.TimedOut) as error:
        # A turn closed at its deadline is still paid for: the adapter reports what it used.
        # So is a turn that finished and whose submit then could not settle the task
        # (2026-11-17: "Task input changed" after 253 seconds, parked with no tokens).
        return {**native.park(root, task["id"], native.in_words(str(error)), record=task.get("record"),
                              usage=getattr(error, "usage", None) or used), "fault": True}


def _settle(root, native, task_id, outcome, refused):
    """A refusal is one more try, never the end of the round.

    2026-11-16: exec returned at the first refusal, so one page that dropped a
    source id ended a catchup night before mail, abstract or translation, and its
    pending task refused every later catchup. Submit already parks a task refused
    twice for one reason or three times in all; a refusal it does not count (a
    claim audit told to continue) is bounded here by the same total."""
    if outcome.get("outcome") != "refused":
        return outcome
    refused[task_id] = refused.get(task_id, 0) + 1
    if refused[task_id] < native.PARK_TOTAL:
        return outcome
    return native.park(root, task_id, f"refused {refused[task_id]} times: {native.in_words(outcome.get('reason', ''))}")


class Unsupported:
    """Platforms without a supported OS scheduler still work by hand."""

    def install(self, root, config):
        raise RemError("No supported background scheduler is available; "
                       "run `co rem sync` yourself or schedule it with cron")

    def uninstall(self, root):
        return False

    def installed(self, root):
        return False

    def describe(self, root):
        return {"scheduler": "none", "installed": False}


def default_scheduler(root=None, *, for_start=False):
    if sys.platform == "linux" and shutil.which("systemctl"):
        return Systemd()
    if sys.platform != "darwin":
        return Unsupported()
    if root is not None:
        from .codex_schedule import CodexNative, app_installed, desktop_timezone
        from .config import read_config
        native = CodexNative()
        if not for_start:
            if native.installed(root) and (native.definition(root).get("status") == "ACTIVE"
                                           or native.describe(root).get("observed_active")):
                return native
            if Launchd().installed(root):
                path = Launchd().plist_path(root)
                if path.is_file() and 'connectonion.rem.codex_exec' in plistlib.loads(path.read_bytes()).get('ProgramArguments', []):
                    return CodexExec()
                return Launchd()
            if native.installed(root):
                return native
        config = read_config(root)
        if config.get("runner") == "codex" and config["schedule"]["runner"] == "codex-exec":
            return CodexExec()
        if (config.get("runner") == "codex" and app_installed()
                and config["schedule"]["timezone"] == desktop_timezone()):
            return native
    return Launchd()
