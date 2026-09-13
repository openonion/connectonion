"""Background maintenance rides the OS scheduler; there is no daemon of our own.

`co wiki sync` already carries the lock, the attempt cap and the incremental
checkpoint, so the only thing the background needs is something that survives a
closed terminal and a reboot and wakes us now and then. launchd is that on
macOS: one declarative job file. A worker process of ours would still need a
login launcher per OS and would add a process on top -- so the per-OS part is
kept to this one file, and everything else stays one implementation in `sync`.

The job is a tick, not a calendar. Measured 2026-09-07 on macOS 26: a
`StartCalendarInterval` job -- array or dict form, plain /bin/sh, with or
without ProcessType -- never fired in three experiments, while `StartInterval`
fired to the second every time. So launchd runs `co wiki sync --scheduled`
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
    root = Path(root).resolve()
    if root == default_root():
        return LABEL
    return LABEL + "." + hashlib.sha256(str(root).encode()).hexdigest()[:12]


class Launchd:
    """macOS LaunchAgent for the current user; no root, survives logout/login."""

    def __init__(self, agents_dir=None, uid=None, run=subprocess.run, python=None):
        self.agents_dir = Path(agents_dir or Path.home() / "Library" / "LaunchAgents")
        self.uid = os.getuid() if uid is None else uid
        self.run = run
        self.python = python or sys.executable

    def plist_path(self, root: Path) -> Path:
        return self.agents_dir / f"{label_for(root)}.plist"

    def render(self, root: Path, config: dict) -> str:
        root = Path(root).resolve()
        # launchd starts jobs with an almost empty PATH, so the job must be told
        # where this Python and the codex binary live at install time.
        codex = shutil.which("codex")
        dirs = [str(Path(self.python).parent)]
        if codex:
            dirs.append(str(Path(codex).parent))
        dirs += ["/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
        env = {"PATH": ":".join(dict.fromkeys(dirs)), "HOME": str(Path.home())}
        if os.environ.get("PYTHONPATH"):
            # The job must run the same connectonion the user is running now; a
            # development checkout only exists on PYTHONPATH.
            env["PYTHONPATH"] = os.environ["PYTHONPATH"]
        job = {
            "Label": label_for(root),
            "ProgramArguments": [self.python, "-m", "connectonion.cli.main",
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
        if not self._launchctl("bootstrap", f"gui/{self.uid}", str(path)):
            raise WikiError("launchctl could not load the job; check ~/Library/LaunchAgents and run `co wiki doctor`")
        return {"scheduler": "launchd", "label": label_for(root), "plist": str(path),
                "times": list(config["schedule"]["times"])}

    def uninstall(self, root: Path) -> bool:
        root = Path(root).resolve()
        path = self.plist_path(root)
        self._launchctl("bootout", f"gui/{self.uid}/{label_for(root)}")
        if not path.exists():
            return False
        path.unlink()
        return True

    def describe(self, root: Path) -> dict:
        """What launchd itself says -- the plist being present is not the job being alive."""
        root = Path(root).resolve()
        info = {"scheduler": "launchd", "label": label_for(root), "installed": self.plist_path(root).is_file()}
        result = self.run(["launchctl", "print", f"gui/{self.uid}/{label_for(root)}"],
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
