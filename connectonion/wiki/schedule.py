"""Background maintenance rides the OS scheduler; there is no daemon of our own.

`co wiki daily` uses sync's lock, attempt cap and incremental
checkpoint, so the only thing the background needs is something that survives a
closed terminal and a reboot and wakes us now and then. launchd is that on
macOS: one declarative job file. A worker process of ours would still need a
login launcher per OS and would add a process on top -- so the per-OS part is
kept to this one file, and everything else stays one implementation in `sync`.

The job is a tick, not a calendar. Measured 2026-09-07 on macOS 26: a
`StartCalendarInterval` job -- array or dict form, plain /bin/sh, with or
without ProcessType -- never fired in three experiments, while `StartInterval`
fired to the second every time. So launchd runs `co wiki sync --scheduled` (formerly `daily --scheduled`, which still works)
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
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .files import WikiError

LABEL = "ai.openonion.co-wiki"
TICK_SECONDS = 300  # a slot is served within five minutes of its time; a no-op tick is cheap


def default_root() -> Path:
    return (Path.home() / ".co" / "wiki").resolve()


def label_for(root: Path) -> str:
    # Every root, the default one included, is named by its resolved path.
    # launchd's domain is the uid, not HOME: when the default root's label was
    # the bare LABEL, `co wiki stop` under a test HOME booted out the real
    # user's job (1.8.8b11). Jobs installed under the bare label are still found
    # and stopped through Launchd._legacy.
    root = Path(root).resolve()
    return LABEL + "." + hashlib.sha256(str(root).encode()).hexdigest()[:12]


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

    def render(self, root: Path, config: dict) -> str:
        from .runner import co_command
        root = Path(root).resolve()
        # The installation running `co wiki start`, not the first co on PATH:
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
        if os.environ.get("PYTHONPATH"):
            # The job must run the same connectonion the user is running now; a
            # development checkout only exists on PYTHONPATH.
            env["PYTHONPATH"] = os.environ["PYTHONPATH"]
        job = {
            "Label": label_for(root),
            "ProgramArguments": [*command,
                                 "wiki", "--root", str(root), "sync", "--scheduled"],
            "StartInterval": TICK_SECONDS,
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
        root = Path(root).resolve()
        path = self.plist_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".co-wiki-", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(self.render(root, config))
        os.chmod(name, 0o600)
        os.replace(name, path)
        # bootout first so a changed schedule is reloaded rather than ignored.
        self._launchctl("bootout", f"gui/{self.uid}/{label_for(root)}")
        self._remove_legacy(root)  # one job per root, not the old label beside the new
        if not self._launchctl("bootstrap", f"gui/{self.uid}", str(path)):
            raise WikiError("launchctl could not load the job; check ~/Library/LaunchAgents and run `co wiki doctor`")
        return {"scheduler": "launchd", "label": label_for(root), "plist": str(path),
                "times": list(config["schedule"]["times"])}

    def uninstall(self, root: Path) -> bool:
        root = Path(root).resolve()
        path = self.plist_path(root)
        self._launchctl("bootout", f"gui/{self.uid}/{label_for(root)}")
        removed_legacy = self._remove_legacy(root)
        if not path.exists():
            return removed_legacy
        path.unlink()
        return True

    def describe(self, root: Path) -> dict:
        """What launchd itself says -- the plist being present is not the job being alive."""
        root = Path(root).resolve()
        label = label_for(root)
        if not self.plist_path(root).is_file() and self._legacy(root) is not None:
            label = LABEL  # installed before labels named the root; stop still removes it
        installed = self.plist_path(root).is_file() or label == LABEL
        info = {"scheduler": "launchd", "label": label, "installed": installed}
        result = self.run(["launchctl", "print", f"gui/{self.uid}/{label}"],
                          capture_output=True, text=True, timeout=30)
        info["loaded"] = result.returncode == 0
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("state = "):
                info["state"] = line.split("=", 1)[1].strip()
            elif line.startswith("last exit code = "):
                info["last_exit_code"] = line.split("=", 1)[1].strip()
        return info


class Unsupported:
    """Everything but macOS in this milestone: the notebook still works by hand."""

    def install(self, root, config):
        raise WikiError("Background scheduling is macOS-only in this milestone; "
                        "run `co wiki sync` yourself or schedule it with cron/systemd")

    def uninstall(self, root):
        return False

    def describe(self, root):
        return {"scheduler": "none", "installed": False}


def default_scheduler():
    return Launchd() if sys.platform == "darwin" else Unsupported()
