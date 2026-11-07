"""Background maintenance uses Codex Scheduled or the OS; no REM timer daemon.

Codex notebooks use the desktop's native file scheduler when the application
is installed on macOS. Other runners and headless Macs retain launchd;
Linux uses a systemd user timer with the same five-minute tick.

`co rem daily` uses sync's lock, attempt cap and incremental
checkpoint, so the only thing the background needs is something that survives a
closed terminal and a reboot and wakes us now and then. launchd is that on
macOS: one declarative job file. A worker process of ours would still need a
login launcher per OS and would add a process on top -- so the per-OS part is
kept to this one file, and everything else stays one implementation in `sync`.

The job is a tick, and it is set twice, because each trigger has been
measured dead on one macOS. 2026-09-07, macOS 26: a `StartCalendarInterval`
job -- array or dict form, plain /bin/sh, with or without ProcessType -- never
fired in three experiments, while `StartInterval` fired to the second.
2026-10-11, macOS 14.1: the installed job had runs = 0 a day after install, a
60 s `StartInterval` test job ran 0 times in four minutes, and a calendar job
bootstrapped the same way ran every minute. So the job carries both: every
TICK_SECONDS, and on every matching minute of the clock. So launchd runs `co rem sync --scheduled` (formerly `daily --scheduled`, which still works)
every TICK_SECONDS, and `sync` decides whether one of the saved times has come
due since the last scheduled batch, in the saved timezone rather than the
machine's. Missed slots (asleep, powered off) collapse into one catch-up at the
first tick after wake, and a tick that finds nothing due exits at once without
touching the notebook. RunAtLoad is off: the first tick is the catch-up, and
nothing races the foreground batch `start` just ran.

Known launchd behaviour (measured 2026-08-18): a job still running when its
interval elapses is skipped silently -- harmless here, the next tick catches up.
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
        dirs += ["/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
        env = {"PATH": ":".join(dict.fromkeys(dirs)), "HOME": str(Path.home())}
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
        result = self.run(["launchctl", *args], capture_output=True, text=True, timeout=30)
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
                          capture_output=True, text=True, timeout=30)
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
        return self.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=30)

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
                              capture_output=True, text=True, timeout=30)
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


class CodexExec(Launchd):
    """The OS wakes the existing native task loop through the Codex CLI."""

    def render(self, root, config):
        job = plistlib.loads(super().render(root, config).encode())
        job["ProgramArguments"][-2:] = ["exec", "--scheduled"]
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

    def describe(self, root):
        return {**super().describe(root), "scheduler": "codex-exec"}


def exec_round(root, *, scheduled=True):
    from . import native, runner
    from .codex_schedule import CodexNative
    from .config import read_config
    if scheduled and CodexNative().recent_desktop_fire(root):
        return {"outcome": "skipped", "reason": "desktop automation fired in the last 10 minutes"}
    task = native.next_task(root, scheduled=scheduled)
    while task.get("outcome") == "task":
        if scheduled and CodexNative().recent_desktop_fire(root):
            return {"outcome": "skipped", "reason": "desktop automation fired in the last 10 minutes"}
        result = runner.run_task(Path(task["material"]), task["instructions"], read_config(root), task["stage"])
        task = native.submit(root, task["id"], usage=result.get("usage"))
        if task.get("outcome") == "refused":
            return task
        if task.get("outcome") != "task":
            task = native.next_task(root, scheduled=scheduled)
    return task


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
        from .config import read_config
        from .service import worker_state
        if read_config(root).get("runner") == "codex" and (for_start or worker_state(root).get("scheduler") == "codex-exec"):
            return CodexExec()
        from .codex_schedule import CodexNative, app_installed, desktop_timezone
        from .config import read_config
        native = CodexNative()
        if not for_start:
            if native.installed(root) and (native.definition(root).get("status") == "ACTIVE"
                                           or native.describe(root).get("observed_active")):
                return native
            if Launchd().installed(root):
                return Launchd()
            if native.installed(root):
                return native
        config = read_config(root)
        if (config.get("runner") == "codex" and app_installed()
                and config["schedule"]["timezone"] == desktop_timezone()):
            return native
    return Launchd()
