"""Codex desktop owns the timer and archives its completed REM conversations.

This is the desktop's local automation-file format, not an App Server RPC.
The desktop rebuilds its own index; REM never writes its database.
Account-managed registrations are detected but cannot be changed through files.
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


def desktop_app() -> Path | None:
    return next((path for path in (Path("/Applications/Codex.app"),
                                  Path.home() / "Applications/Codex.app") if path.is_dir()), None)


def app_installed() -> bool:
    return desktop_app() is not None


ACCOUNT_STORAGE = ("Codex moved this REM task to account storage. Manage this task in Codex Scheduled; "
                   "this REM version cannot yet change its native account registration")
INDEX_FIELDS = ("id", "rrule", "status", "cwds", "updated_at", "next_run_at", "last_run_at")


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
    def __init__(self, home=None, *, launcher=None, command=None, run=subprocess.run, wait_seconds=90):
        self.home = Path(home) if home is not None else codex_home()
        self.launcher = launcher or Launchd()
        self.command = command
        self.run = run
        self.wait_seconds = wait_seconds

    def _indexed(self, root: Path) -> dict:
        database = self.home / "sqlite" / "codex-dev.db"
        if not database.is_file():
            return {}
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=2)) as connection:
            connection.row_factory = sqlite3.Row
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(automations)")}
            if not columns:
                return {}
            needed = set(INDEX_FIELDS)
            if not needed.issubset(columns):
                raise RemError("Unrecognized native automation index; open Codex Scheduled before changing timers")
            selected = sorted(needed | (columns & {"account_id", "user_id", "installation_id", "legacy_automation_id"}))
            clause, arguments = "id = ?", [automation_id(root)]
            if "legacy_automation_id" in columns:
                clause += " OR legacy_automation_id = ?"
                arguments.append(automation_id(root))
            rows = connection.execute("SELECT " + ", ".join(selected) + " FROM automations WHERE " + clause,
                                      arguments).fetchall()
        if len(rows) > 1:
            raise RemError("Multiple native REM registrations exist; resolve them in Codex Scheduled before changing timers")
        if not rows:
            return {}
        row = dict(rows[0])
        if json.loads(row["cwds"] or "[]") != [str(Path(root).resolve())]:
            raise RemError("The Codex automation ID belongs to another notebook; nothing was changed")
        return row

    @staticmethod
    def _account_record(row: dict) -> bool:
        owned = any(row.get(key) for key in ("account_id", "user_id", "installation_id"))
        return bool(row and (owned or row.get("legacy_automation_id") not in (None, "", row["id"])))

    def _account_task(self, root: Path) -> dict:
        row = self._indexed(root)
        return row if self._account_record(row) else {}

    @staticmethod
    def _adopted(row: dict, definition: dict) -> bool:
        return bool(row and all(row[key] == definition[key] for key in ("id", "rrule", "status", "updated_at"))
                    and json.loads(row["cwds"] or "[]") == definition["cwds"])

    def _require_file_storage(self, root: Path) -> None:
        if self._account_task(root):
            raise RemError(ACCOUNT_STORAGE)

    def _app_running(self) -> bool:
        return self.run(["pgrep", "-f", r"^.+/Codex[.]app/Contents/MacOS/(ChatGPT|Codex)( |$)"],
                        capture_output=True, text=True, timeout=10).returncode == 0

    def _open_desktop(self) -> None:
        app = desktop_app()
        if app is None:
            raise RemError("Install Codex desktop before using its native schedule")
        # A running App Server does not mean the primary renderer has published
        # automations.local. Opening Scheduled wakes that native capability.
        result = self.run(["/usr/bin/open", "-a", str(app), "codex://automations"],
                          capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise RemError("Codex Scheduled could not open; run co rem status before changing timers")

    def _wait_for_definition(self, root: Path, expected: dict) -> bool:
        expected = dict(expected)
        deadline = time.monotonic() + self.wait_seconds
        while True:
            row = self._indexed(root)
            if self._account_record(row):
                raise RemError(ACCOUNT_STORAGE)
            if self.definition(root) != expected:
                raise RemError("The native REM definition changed while waiting for confirmation; retry the desired action")
            if self._adopted(row, expected) and (expected["status"] != "ACTIVE" or row.get("next_run_at") is not None):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(1)

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
        self._require_file_storage(root)
        text = "\n".join(f"{key} = {json.dumps(value, ensure_ascii=False)}" for key, value in data.items())
        atomic_write(self.definition_path(root), text + "\n")

    def install(self, root: Path, config: dict) -> dict:
        root = Path(root).resolve()
        self._require_file_storage(root)
        previous = self.definition(root)
        legacy = self.launcher.describe(root)
        active_update = previous.get("status") == "ACTIVE" and not legacy.get("loaded") and not legacy.get("installed")
        definition = self.render(root, config, active=active_update)
        if legacy.get("loaded") and legacy.get("state") == "running":
            raise RemError("The existing REM batch is still running. Let it finish, then run `co rem start` "
                           "to move its timer to Codex; the current schedule has been kept")
        if not self._app_running():
            self._open_desktop()
        self._write(root, definition)
        if not self._wait_for_definition(root, definition):
            if previous:
                self._write(root, previous)
            raise RemError("Codex has not registered the paused REM task. Open Codex desktop and its "
                           "Scheduled page, let initialization finish, then run `co rem start` again. "
                           "The previous clock and definition have been kept; a new task stays paused")
        # Cold startup can hydrate the index before the primary renderer is
        # ready. Deliver Scheduled after adoption, before removing any old clock.
        self._open_desktop()
        with maintenance_lock(root):
            if self.launcher.describe(root).get("state") == "running":
                if previous:
                    self._write(root, previous)
                raise RemError("An existing REM batch started during registration. Let it finish, then "
                               "run `co rem start` again; the previous clock has been kept")
            # Opening Scheduled can migrate the task or change its definition.
            if not self._wait_for_definition(root, definition):
                raise RemError("Codex registration changed while opening Scheduled; the previous clock "
                               "has been kept. Check Codex Scheduled before retrying co rem start")
            if (legacy.get("installed") or legacy.get("loaded")) and not self.launcher.unload_for_migration(root):
                if previous:
                    self._write(root, previous)
                raise RemError("launchd did not unload the previous REM timer; its plist was kept "
                               "and native activation was cancelled. Run co rem doctor")
            definition["status"] = "ACTIVE"
            self._write(root, definition)
        if not self._wait_for_definition(root, definition):
            raise RemError("Codex native activation was not confirmed. The task is saved, but its clock "
                           "is not verified. Open Codex Scheduled and run `co rem status`; do not enable "
                           "another timer until this registration is resolved")
        return {"scheduler": "codex-native", "automation_id": definition["id"],
                "definition": str(self.definition_path(root)), "times": list(config["schedule"]["times"]),
                "note": "Keep Codex desktop open and this computer awake. Run co rem status to check native registration."}

    def uninstall(self, root: Path) -> bool:
        account = self._account_task(root)
        if account:
            raise RemError(ACCOUNT_STORAGE + "; its pause has not been confirmed")
        definition = self.definition(root)
        indexed = self._indexed(root)
        if not definition and indexed.get("status") == "ACTIVE":
            raise RemError("Codex still reports an active REM task without its definition; pause it in Scheduled")
        if definition:
            if definition["status"] == "PAUSED" and indexed.get("status") in (None, "PAUSED"):
                return True
            definition.update(status="PAUSED", updated_at=int(time.time() * 1000))
            self._write(root, definition)
            if indexed and not self._wait_for_definition(root, definition):
                raise RemError("Codex native pause was not confirmed. Open Codex Scheduled and pause the REM "
                               "task there before enabling another timer. A running batch may still finish")
        return bool(definition)

    def installed(self, root: Path) -> bool:
        return bool(self.definition(root) or self._indexed(root))

    def describe(self, root: Path) -> dict:
        definition = self.definition(root)
        info = {"scheduler": "codex-native", "automation_id": automation_id(root),
                "installed": bool(definition), "loaded": False, "active": False,
                "observed_active": False, "desired_status": definition.get("status"),
                "storage": "file", "app_running": self._app_running()}
        row = self._indexed(root)
        if self._account_record(row):
            return {**info, **{key: row[key] for key in INDEX_FIELDS},
                    "automation_id": row["id"], "installed": True, "loaded": True,
                    "storage": "account", "active": row["status"] == "ACTIVE",
                    "observed_active": row["status"] == "ACTIVE", "reason": ACCOUNT_STORAGE}
        if not definition:
            return {**info, **row, "installed": bool(row), "observed_active": row.get("status") == "ACTIVE",
                    **({"reason": "Native REM definition is missing; check this task in Codex Scheduled"} if row else {})}
        if row:
            info.update({key: row[key] for key in INDEX_FIELDS})
            info["observed_active"] = row["status"] == "ACTIVE"
            info["loaded"] = self._adopted(row, definition)
            info["active"] = info["loaded"] and row["status"] == "ACTIVE"
        from .config import read_config
        config = read_config(root)
        if config["schedule"]["timezone"] != desktop_timezone():
            info.update(active=False, reason="The notebook timezone differs from this computer; run co rem start to use launchd")
        elif config.get("runner") != "codex" or recurrence(config) != definition["rrule"]:
            info.update(active=False, reason="Saved schedule settings changed; run co rem start to apply them")
        return info
