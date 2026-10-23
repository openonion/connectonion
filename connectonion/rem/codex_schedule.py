"""Codex desktop owns the timer and archives its completed REM conversations.

This is the desktop's local automation-file format, not an App Server RPC.
The desktop rebuilds its own index; REM never writes its database.
"""

import json
import os
import shlex
import sqlite3
import subprocess
import time
import tomllib
from contextlib import closing
from pathlib import Path

from .files import RemError, atomic_write, maintenance_lock
from .schedule import Launchd, _checkout_path, label_for


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().resolve()


def app_installed() -> bool:
    return any(path.is_dir() for path in (Path("/Applications/Codex.app"),
                                         Path.home() / "Applications/Codex.app"))


def automation_id(root: Path) -> str:
    return "co-rem-" + label_for(root).rsplit(".", 1)[1]


def desktop_timezone() -> str:
    local = Path("/etc/localtime")
    target = os.readlink(local) if local.is_symlink() else str(local.resolve())
    return target.split("/zoneinfo/")[-1] if "/zoneinfo/" in target else ""


def recurrence(config: dict) -> str:
    """Select the exact pairs on Codex's local wall clock, including DST.

    The installed native TZID path misinterprets offsets. Use its local-clock
    path, and retain launchd when the saved timezone differs from the desktop.
    BYSETPOS selects pairs rather than the Cartesian product of hours/minutes.
    """
    schedule = config["schedule"]
    if not desktop_timezone() or schedule["timezone"] != desktop_timezone():
        raise RemError("Codex native scheduling uses this computer's timezone; use the macOS "
                       "scheduler to keep a different saved timezone")
    pairs = {tuple(map(int, value.split(":"))) for value in schedule["times"]}
    hours, minutes = sorted({h for h, m in pairs}), sorted({m for h, m in pairs})
    rule = ("FREQ=DAILY;BYHOUR=" + ",".join(map(str, hours)) + ";BYMINUTE="
            + ",".join(map(str, minutes)) + ";BYSECOND=0")
    grid = [(h, m) for h in hours for m in minutes]
    if len(grid) != len(pairs):
        positions = [i for i, pair in enumerate(grid, 1) if pair in pairs]
        if max(positions) > 366:
            raise RemError("These time pairs exceed Codex's rule limits; the existing clock was kept. "
                           "Reduce the saved times or use an OS scheduler")
        rule += ";BYSETPOS=" + ",".join(map(str, positions))
    return rule


class CodexNative:
    def __init__(self, home=None, *, launcher=None, command=None, run=subprocess.run, wait_seconds=45):
        self.home = Path(home) if home is not None else codex_home()
        self.launcher = launcher or Launchd()
        self.command = command
        self.run = run
        self.wait_seconds = wait_seconds

    def definition_path(self, root: Path) -> Path:
        return self.home / "automations" / automation_id(root) / "automation.toml"

    def definition(self, root: Path) -> dict:
        path = self.definition_path(root)
        if path.is_symlink() or path.parent.is_symlink():
            raise RemError("Refusing a linked Codex automation definition")
        if not path.is_file():
            return {}
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        if data.get("id") != automation_id(root) or data.get("cwds") != [str(Path(root).resolve())]:
            raise RemError("The Codex automation ID belongs to another notebook; nothing was changed")
        return data

    def render(self, root: Path, config: dict, *, active=True) -> dict:
        from .runner import co_command
        root = Path(root).resolve()
        command = self.command or co_command()
        checkout = _checkout_path()
        if checkout:
            command = ["/usr/bin/env", f"PYTHONPATH={checkout}", *command]
        command = [*command, "rem", "--root", str(root), "sync", "--scheduled"]
        previous = self.definition(root)
        stamp = int(time.time() * 1000)
        data = {"version": 1, "id": automation_id(root), "kind": "cron",
                "name": "REM notebook upkeep", "status": "ACTIVE" if active else "PAUSED",
                "prompt": "Run this exact command once and report its result:\n" + shlex.join(command)
                          + "\nWait for its final exit status before ending your turn. REM can run for over "
                          "an hour: keep polling the same execution session with long waits. A running "
                          "process is not completion. Do not finish, archive, or report merely that it "
                          "started while the process is still running. Never kill it to finish the task."
                          + "\nLet the REM CLI handle source access, locks, quotas and missed slots. "
                          "Do not edit notebook pages yourself or start another update.",
                "rrule": recurrence(config), "execution_environment": "local",
                "reasoning_effort": "low", "auto_archive": True, "cwds": [str(root)],
                "created_at": previous.get("created_at", stamp), "updated_at": stamp}
        if config.get("model") and config["model"] != "default":
            data["model"] = config["model"]
        return data

    def _write(self, root: Path, data: dict) -> None:
        text = "\n".join(f"{key} = {json.dumps(value, ensure_ascii=False)}" for key, value in data.items())
        atomic_write(self.definition_path(root), text + "\n")

    def install(self, root: Path, config: dict) -> dict:
        root = Path(root).resolve()
        previous = self.definition(root)
        legacy = self.launcher.describe(root)
        active_update = previous.get("status") == "ACTIVE" and not legacy.get("loaded") and not legacy.get("installed")
        definition = self.render(root, config, active=active_update)
        if legacy.get("loaded") and legacy.get("state") == "running":
            raise RemError("The existing REM batch is still running. Let it finish, then run `co rem start` "
                           "to move its timer to Codex; the current schedule has been kept")
        self._write(root, definition)
        deadline = time.monotonic() + self.wait_seconds
        while not self.describe(root)["loaded"] and time.monotonic() < deadline:
            time.sleep(1)
        if not self.describe(root)["loaded"]:
            if previous:
                self._write(root, previous)
            raise RemError("Codex has not registered the paused REM task. Open Codex desktop and its "
                           "Scheduled page, let initialization finish, then run `co rem start` again. "
                           "The previous clock and definition have been kept; a new task stays paused")
        with maintenance_lock(root):
            if self.launcher.describe(root).get("state") == "running":
                if previous:
                    self._write(root, previous)
                raise RemError("An existing REM batch started during registration. Let it finish, then "
                               "run `co rem start` again; the previous clock has been kept")
            if (legacy.get("installed") or legacy.get("loaded")) and not self.launcher.unload_for_migration(root):
                if previous:
                    self._write(root, previous)
                raise RemError("launchd did not unload the previous REM timer; its plist was kept "
                               "and native activation was cancelled. Run co rem doctor")
            definition["status"] = "ACTIVE"
            self._write(root, definition)
        return {"scheduler": "codex-native", "automation_id": definition["id"],
                "definition": str(self.definition_path(root)), "times": list(config["schedule"]["times"]),
                "note": "Keep Codex desktop open and this computer awake. Run co rem status to check native registration."}

    def uninstall(self, root: Path) -> bool:
        definition = self.definition(root)
        if definition:
            definition.update(status="PAUSED", updated_at=int(time.time() * 1000))
            self._write(root, definition)
        return bool(definition)

    def installed(self, root: Path) -> bool:
        return bool(self.definition(root))

    def describe(self, root: Path) -> dict:
        definition = self.definition(root)
        info = {"scheduler": "codex-native", "automation_id": automation_id(root),
                "installed": bool(definition), "loaded": False, "active": False,
                "app_running": self.run(["pgrep", "-f", r"^.+/Codex[.]app/Contents/MacOS/(ChatGPT|Codex)( |$)"], capture_output=True,
                                        text=True, timeout=10).returncode == 0}
        database = self.home / "sqlite" / "codex-dev.db"
        if not definition or not database.is_file():
            return info
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=2)) as connection:
            connection.row_factory = sqlite3.Row
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(automations)")}
            needed = {"id", "rrule", "status", "cwds", "updated_at", "next_run_at", "last_run_at"}
            if not needed.issubset(columns):
                return {**info, "reason": "Unrecognized native automation index; open Codex Scheduled"}
            row = connection.execute("SELECT id, rrule, status, cwds, updated_at, next_run_at, last_run_at "
                                     "FROM automations WHERE id = ?", (automation_id(root),)).fetchone()
        if row is not None:
            info.update(dict(row))
            info["loaded"] = (row["rrule"] == definition["rrule"]
                              and json.loads(row["cwds"] or "[]") == definition["cwds"]
                              and row["status"] == definition["status"]
                              and row["updated_at"] == definition["updated_at"])
            info["active"] = info["loaded"] and row["status"] == "ACTIVE"
        from .config import read_config
        config = read_config(root)
        if config["schedule"]["timezone"] != desktop_timezone():
            info.update(active=False, reason="The notebook timezone differs from this computer; run co rem start to use launchd")
        elif config.get("runner") != "codex" or recurrence(config) != definition["rrule"]:
            info.update(active=False, reason="Saved schedule settings changed; run co rem start to apply them")
        return info
