"""Atomic overnight ConnectOnion upgrades and morning REM reader scheduling (#3363, #3474).

Upgrades never delete the live `co` tool environment before the new release is
staged and verified importable. When an upgrade succeeds, the newly installed
Python immediately prewarms the REM reader cache (`live.html` + `data.json`)
and triggers idle live-Host replacement on the same stable port so the morning
open lands on the fresh release with zero wait.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

from .files import RemError, read_json, state_path, write_json

UPGRADE_LABEL = "ai.openonion.co-upgrade"
MORNING_LABEL = "ai.openonion.co-rem-morning"
PYPI_URL = "https://pypi.org/pypi/connectonion/json"
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _home_dir(home: Path | None = None) -> Path:
    return (Path(home) if home is not None else Path.home()).expanduser().resolve()


def _co_dir(home: Path | None = None) -> Path:
    return _home_dir(home) / ".co"


def upgrade_config_path(home: Path | None = None) -> Path:
    return _co_dir(home) / "auto-upgrade.json"


def upgrade_state_path(home: Path | None = None) -> Path:
    return _co_dir(home) / "auto-upgrade-state.json"


def current_version() -> str:
    from .live_host import version_on_disk
    return version_on_disk()


def find_uv() -> str | None:
    return shutil.which("uv")


def _default_channel(version: str | None = None) -> str:
    try:
        parsed = Version(version or current_version())
        return "preview" if parsed.is_prerelease else "stable"
    except InvalidVersion:
        return "stable"


def default_upgrade_config(version: str | None = None) -> dict[str, Any]:
    from .config import local_timezone
    return {
        "version": 1,
        "enabled": True,
        "channel": _default_channel(version),
        "pinned_version": None,
        "time": "01:00",
        "timezone": local_timezone(),
        # Never present a default time as a learned user habit (#3474).
        "morning_open": {
            "enabled": False,
            "time": None,
            "source": "none",
        },
    }


def read_upgrade_config(home: Path | None = None) -> dict[str, Any]:
    defaults = default_upgrade_config()
    saved = read_json(upgrade_config_path(home), {})
    if not isinstance(saved, dict):
        return defaults
    morning = {**defaults["morning_open"], **(saved.get("morning_open") if isinstance(saved.get("morning_open"), dict) else {})}
    return {**defaults, **saved, "morning_open": morning}


def write_upgrade_config(config: dict[str, Any], home: Path | None = None) -> dict[str, Any]:
    channel = config.get("channel")
    if channel not in ("stable", "preview", "pinned"):
        raise RemError("upgrade channel must be stable, preview or pinned")
    time_value = str(config.get("time") or "01:00")
    if not TIME_PATTERN.fullmatch(time_value):
        raise RemError("upgrade time must be HH:MM (24-hour local time)")
    morning = config.get("morning_open") or {}
    mtime = morning.get("time")
    if mtime is not None and not TIME_PATTERN.fullmatch(str(mtime)):
        raise RemError("morning_open.time must be HH:MM or null")
    if morning.get("source", "none") not in ("none", "explicit", "learned"):
        raise RemError("morning_open.source must be none, explicit or learned")
    merged = {**default_upgrade_config(), **config, "morning_open": {**default_upgrade_config()["morning_open"], **morning}}
    write_json(upgrade_config_path(home), merged)
    return merged


def read_upgrade_state(home: Path | None = None) -> dict[str, Any]:
    saved = read_json(upgrade_state_path(home), {})
    return saved if isinstance(saved, dict) else {}


def write_upgrade_state(state: dict[str, Any], home: Path | None = None) -> dict[str, Any]:
    write_json(upgrade_state_path(home), state)
    return state


def _default_uv_tool_dir() -> Path:
    if env := os.environ.get("UV_TOOL_DIR"):
        return Path(env).expanduser().resolve()
    xdg_data = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data).expanduser() if xdg_data else Path.home() / ".local" / "share"
    return (base / "uv" / "tools").resolve()


def _default_uv_bin_dir() -> Path:
    if env := os.environ.get("UV_TOOL_BIN_DIR"):
        return Path(env).expanduser().resolve()
    return (Path.home() / ".local" / "bin").resolve()


def detect_install_method(
    *,
    executable: str | None = None,
    package_file: str | None = None,
    uv_tool_dir: Path | None = None,
) -> dict[str, Any]:
    """Identify how ConnectOnion is installed so auto-upgrade never mutates dev or system envs."""
    import connectonion

    exe = Path(executable or sys.executable).expanduser().resolve()
    pkg = Path(package_file or connectonion.__file__).expanduser().resolve()
    tools = Path(uv_tool_dir).expanduser().resolve() if uv_tool_dir is not None else _default_uv_tool_dir()

    if not ({"site-packages", "dist-packages"} & set(pkg.parts)):
        return {
            "method": "editable",
            "supported": False,
            "reason": "ConnectOnion is running from a source checkout; pull and reinstall manually.",
        }
    try:
        pkg.relative_to(tools / "connectonion")
        return {
            "method": "uv_tool",
            "supported": True,
            "uv_tool_dir": str(tools),
            "uv_bin_dir": str(_default_uv_bin_dir()),
            "reason": "Installed via uv tool; eligible for atomic self-upgrade.",
        }
    except ValueError:
        pass

    lower_parts = {p.lower() for p in exe.parts}
    if any(p in lower_parts for p in (".venv", "venv", "virtualenv", "conda", "envs")):
        return {
            "method": "project_venv",
            "supported": False,
            "reason": "ConnectOnion is inside a virtual environment; upgrade this environment explicitly.",
        }
    return {
        "method": "system",
        "supported": False,
        "reason": "ConnectOnion is installed in a system-managed Python; upgrade with your package manager.",
    }


def _fetch_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "connectonion-auto-upgrade"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def latest_pypi_version(channel: str, *, fetch=None) -> str:
    """Return the newest non-yanked PyPI version matching `stable` or `preview`."""
    data = (fetch or _fetch_json)(PYPI_URL)
    releases = data.get("releases") if isinstance(data, dict) else {}
    candidates: list[Version] = []
    for raw, files in (releases or {}).items():
        if not files or all(bool(item.get("yanked")) for item in files if isinstance(item, dict)):
            continue
        try:
            parsed = Version(raw)
        except InvalidVersion:
            continue
        if channel == "stable" and (parsed.is_prerelease or parsed.is_devrelease):
            continue
        if parsed.is_devrelease:
            continue
        candidates.append(parsed)
    if not candidates:
        raise RemError(f"No installable ConnectOnion release found on PyPI for channel {channel!r}")
    return str(max(candidates))


def rem_turn_active(root: Path | None) -> bool:
    """Non-blocking probe of REM's exec-turn.lock so upgrades defer rather than collide with a live turn."""
    if root is None or os.name == "nt":
        return False
    lock = state_path(Path(root), "exec-turn.lock")
    if not lock.is_file():
        return False
    import fcntl
    try:
        with lock.open("a", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(handle, fcntl.LOCK_UN)
    except OSError:
        return False
    return False


def prewarm_reader(root: Path, python_bin: Path) -> bool:
    """Rebuild live.html + data.json and trigger idle Host replacement using the newly installed Python."""
    if not (root / "config.yaml").is_file() or not python_bin.is_file():
        return False
    try:
        subprocess.Popen(
            [str(python_bin), "-m", "connectonion.rem.reader", str(root.resolve()), "live", "full"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except OSError:
        return False


def refresh_host_agent_after_upgrade(
    home_dir: Path,
    python_bin: Path,
    *,
    agents_dir: Path | None = None,
    uid: int | None = None,
    run=subprocess.run,
    platform: str | None = None,
) -> dict[str, Any]:
    """On macOS, refresh `ai.openonion.rem-host` plist to the new binary and kickstart it in `gui/$UID` (#3317)."""
    plat = platform or sys.platform
    if plat != "darwin":
        return {"refreshed": False, "reason": "non-macOS"}
    from . import live_host

    resolved_agents = Path(agents_dir) if agents_dir is not None else home_dir / "Library" / "LaunchAgents"
    if not live_host.host_agent_installed(agents_dir=resolved_agents):
        return {"refreshed": False, "reason": "not installed"}
    co_dir = _co_dir(home_dir)
    saved = read_json(co_dir / "rem-live-host.json", {})
    port = saved.get("port") if isinstance(saved, dict) and isinstance(saved.get("port"), int) else None
    installed = live_host.install_host_agent(
        co_dir,
        port=port,
        python_bin=python_bin,
        agents_dir=resolved_agents,
        uid=uid,
        run=run,
        platform=plat,
    )
    if not installed.get("installed"):
        return {"refreshed": False, "reason": installed.get("error") or "install failed"}
    kicked = live_host.kickstart_host_agent(
        uid=uid,
        agents_dir=resolved_agents,
        run=run,
        platform=plat,
    )
    if kicked.get("ok") and isinstance(saved, dict) and saved.get("address"):
        updated = {
            **saved,
            "port": installed["port"],
            "command": " ".join(installed["command"][1:]),
            "session": "Aqua",
            "via_launch_agent": True,
            "label": live_host.REM_HOST_LABEL,
        }
        if kicked.get("pid"):
            updated["pid"] = kicked["pid"]
        write_json(co_dir / "rem-live-host.json", updated)
    return {
        "refreshed": bool(kicked.get("ok")),
        "label": live_host.REM_HOST_LABEL,
        "plist": installed.get("plist"),
        "port": installed.get("port"),
        "pid": kicked.get("pid"),
        **({"error": kicked["error"]} if kicked.get("error") else {}),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _install_spec(target: str) -> str:
    return f"connectonion=={target}"


def _uv_install_args(uv: str, target: str, *, force: bool = False, offline: bool = False) -> list[str]:
    args = [uv, "tool", "install"]
    if force:
        args.append("--force")
    if offline:
        args.append("--offline")
    else:
        args.append("--refresh")
    try:
        if Version(target).is_prerelease:
            args.append("--prerelease=allow")
    except InvalidVersion:
        pass
    args.append(_install_spec(target))
    return args


def _tool_python(tool_root: Path) -> Path:
    if os.name == "nt":
        return tool_root / "connectonion" / "Scripts" / "python.exe"
    return tool_root / "connectonion" / "bin" / "python"


def _bin_co(bin_dir: Path) -> Path:
    return bin_dir / ("co.exe" if os.name == "nt" else "co")


def run_atomic_upgrade(
    *,
    home: Path | None = None,
    root: Path | None = None,
    dry_run: bool = False,
    prewarm: bool = True,
    run=subprocess.run,
    fetch=None,
) -> dict[str, Any]:
    """Check and atomically upgrade a uv-tool ConnectOnion install, preserving the old binary on any failure."""
    home_dir = _home_dir(home)
    rem_root = Path(root) if root is not None else home_dir / ".co" / "rem"
    config = read_upgrade_config(home_dir)
    installed = current_version()

    install_info = detect_install_method()
    if not install_info.get("supported"):
        result = {
            "outcome": "unsupported",
            "method": install_info.get("method"),
            "current": installed,
            "reason": install_info.get("reason"),
            "at": _now_iso(),
        }
        return write_upgrade_state(result, home_dir)

    if config.get("channel") == "pinned" or config.get("pinned_version"):
        result = {
            "outcome": "pinned",
            "current": installed,
            "pinned_version": config.get("pinned_version") or installed,
            "at": _now_iso(),
        }
        return write_upgrade_state(result, home_dir)

    try:
        target = latest_pypi_version(config["channel"], fetch=fetch)
    except Exception as error:
        result = {
            "outcome": "failed",
            "current": installed,
            "target": None,
            "error": f"PyPI check failed: {error}",
            "at": _now_iso(),
        }
        return write_upgrade_state(result, home_dir)

    try:
        if Version(target) <= Version(installed):
            result = {
                "outcome": "up_to_date",
                "current": installed,
                "target": target,
                "channel": config["channel"],
                "at": _now_iso(),
            }
            return write_upgrade_state(result, home_dir)
    except InvalidVersion:
        if target == installed:
            return write_upgrade_state({"outcome": "up_to_date", "current": installed, "target": target, "at": _now_iso()}, home_dir)

    if rem_turn_active(rem_root):
        result = {
            "outcome": "deferred_busy",
            "current": installed,
            "target": target,
            "reason": "A REM maintenance turn is currently running; upgrade deferred until idle.",
            "at": _now_iso(),
        }
        return write_upgrade_state(result, home_dir)

    if dry_run:
        return {"outcome": "dry_run", "from": installed, "to": target, "channel": config["channel"], "at": _now_iso()}

    uv = find_uv()
    if not uv:
        result = {
            "outcome": "failed",
            "current": installed,
            "target": target,
            "error": "uv binary not found on PATH; install uv or upgrade manually.",
            "at": _now_iso(),
        }
        return write_upgrade_state(result, home_dir)

    live_tools = Path(install_info["uv_tool_dir"])
    live_bin = Path(install_info["uv_bin_dir"])
    base_env = os.environ.copy()

    # Phase 1: Stage into an isolated UV_TOOL_DIR and verify import + CLI before touching live `co`.
    with tempfile.TemporaryDirectory(prefix="co-upgrade-stage-") as stage_raw:
        stage_tools = Path(stage_raw) / "tools"
        stage_bin = Path(stage_raw) / "bin"
        stage_env = {**base_env, "UV_TOOL_DIR": str(stage_tools), "UV_TOOL_BIN_DIR": str(stage_bin)}
        staged = run(_uv_install_args(uv, target, force=True, offline=False), capture_output=True, text=True, env=stage_env, timeout=300)
        if staged.returncode != 0:
            err = (staged.stderr or staged.stdout or "staging uv tool install failed").strip()
            return write_upgrade_state({
                "outcome": "failed",
                "current": installed,
                "target": target,
                "error": f"Staged install failed (previous version kept): {err[:400]}",
                "at": _now_iso(),
            }, home_dir)

        stage_co = _bin_co(stage_bin)
        stage_py = _tool_python(stage_tools)
        verify_cmd = [str(stage_py), "-c", f"import connectonion; assert connectonion.__version__ == {target!r}"]
        verified_py = run(verify_cmd, capture_output=True, text=True, env=stage_env, timeout=60)
        verified_cli = run([str(stage_co), "--version"], capture_output=True, text=True, env=stage_env, timeout=60)
        if verified_py.returncode != 0 or verified_cli.returncode != 0:
            err = (verified_py.stderr or verified_cli.stderr or "staged verification failed").strip()
            return write_upgrade_state({
                "outcome": "failed",
                "current": installed,
                "target": target,
                "error": f"Staged verification failed (previous version kept): {err[:400]}",
                "at": _now_iso(),
            }, home_dir)

        # Phase 2: Backup live tool dir, promote from warm cache, verify, or roll back immediately.
        live_pkg = live_tools / "connectonion"
        backup_pkg = live_tools / f".connectonion.backup-{os.getpid()}"
        had_backup = False
        try:
            if live_pkg.is_dir():
                if backup_pkg.exists():
                    shutil.rmtree(backup_pkg)
                shutil.copytree(live_pkg, backup_pkg, symlinks=True)
                had_backup = True

            live_env = {**base_env, "UV_TOOL_DIR": str(live_tools), "UV_TOOL_BIN_DIR": str(live_bin)}
            promoted = run(_uv_install_args(uv, target, force=True, offline=True), capture_output=True, text=True, env=live_env, timeout=300)
            if promoted.returncode != 0:
                promoted = run(_uv_install_args(uv, target, force=True, offline=False), capture_output=True, text=True, env=live_env, timeout=300)
            if promoted.returncode != 0:
                raise RemError((promoted.stderr or promoted.stdout or "live swap failed").strip())

            live_co = _bin_co(live_bin)
            check_live = run([str(live_co), "--version"], capture_output=True, text=True, env=live_env, timeout=60)
            if check_live.returncode != 0:
                raise RemError((check_live.stderr or "post-swap co --version check failed").strip())
        except Exception as error:
            if had_backup and backup_pkg.is_dir():
                if live_pkg.exists():
                    shutil.rmtree(live_pkg, ignore_errors=True)
                shutil.move(str(backup_pkg), str(live_pkg))
            return write_upgrade_state({
                "outcome": "failed",
                "current": installed,
                "target": target,
                "rolled_back": had_backup,
                "error": f"Swap failed and rolled back to {installed}: {str(error)[:400]}",
                "at": _now_iso(),
            }, home_dir)
        finally:
            if backup_pkg.exists():
                shutil.rmtree(backup_pkg, ignore_errors=True)

    new_python = _tool_python(live_tools)
    did_prewarm = prewarm_reader(rem_root, new_python) if prewarm else False
    host_agent = refresh_host_agent_after_upgrade(home_dir, new_python, run=run)
    return write_upgrade_state({
        "outcome": "upgraded",
        "from": installed,
        "to": target,
        "channel": config["channel"],
        "prewarmed": did_prewarm,
        **({"host_agent_restarted": True} if host_agent.get("refreshed") else {}),
        "at": _now_iso(),
    }, home_dir)


def resilient_shell_command(command: list[str], *, log_path: Path | None = None) -> list[str]:
    """Wrap a scheduled CLI command so a transient missing binary/module skips cleanly without a traceback (#3363)."""
    binary = command[0]
    joined = shlex.join(command)
    log_redirect = f" >> {shlex.quote(str(log_path))} 2>&1" if log_path is not None else ""
    msg = "co is upgrading or unavailable; skipping this turn and retrying later."
    script = (
        f"if [ ! -x {shlex.quote(binary)} ]; then "
        f"printf '%s %s\\n' \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\" {shlex.quote(msg)}{log_redirect}; "
        f"exit 0; fi; "
        f"exec {joined}"
    )
    return ["/bin/sh", "-c", script]


class _DailyCalendarJob:
    """Idempotent daily macOS LaunchAgent / Linux systemd user timer for background ConnectOnion upkeep."""

    label: str = ""
    description: str = ""
    subcommand: list[str] = []

    def __init__(
        self,
        *,
        agents_dir: Path | None = None,
        units_dir: Path | None = None,
        uid: int | None = None,
        run=subprocess.run,
        command: list[str] | None = None,
        platform: str | None = None,
    ):
        self.platform = platform or sys.platform
        self.agents_dir = Path(agents_dir or Path.home() / "Library" / "LaunchAgents")
        self.units_dir = Path(units_dir or Path.home() / ".config" / "systemd" / "user")
        self.uid = os.getuid() if uid is None and hasattr(os, "getuid") else (uid or 0)
        self.run = run
        self.command = command

    def _co_cmd(self) -> list[str]:
        if self.command:
            return list(self.command)
        from .runner import co_command
        return co_command()

    def plist_path(self) -> Path:
        return self.agents_dir / f"{self.label}.plist"

    def unit_path(self, suffix: str) -> Path:
        return self.units_dir / f"{self.label}.{suffix}"

    def _write_private(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{self.label}-", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(text)
        os.chmod(name, 0o600)
        os.replace(name, path)

    def install(self, *, hour: int, minute: int, log_path: Path | None = None) -> dict[str, Any]:
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise RemError("hour must be 0..23 and minute must be 0..59")
        time_str = f"{hour:02d}:{minute:02d}"
        cmd = resilient_shell_command([*self._co_cmd(), *self.subcommand], log_path=log_path)

        if self.platform == "darwin":
            path = self.plist_path()
            log_file = str(log_path or (_co_dir() / f"{self.label}.log"))
            job = {
                "Label": self.label,
                "ProgramArguments": cmd,
                "StartCalendarInterval": {"Hour": hour, "Minute": minute},
                "RunAtLoad": False,
                "ProcessType": "Background",
                "EnvironmentVariables": {
                    "HOME": str(Path.home()),
                    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                },
                "StandardOutPath": log_file,
                "StandardErrorPath": log_file,
            }
            self._write_private(path, plistlib.dumps(job, sort_keys=False).decode("utf-8"))
            self.run(["launchctl", "bootout", f"gui/{self.uid}/{self.label}"], capture_output=True, text=True, timeout=30)
            boot = self.run(["launchctl", "bootstrap", f"gui/{self.uid}", str(path)], capture_output=True, text=True, timeout=30)
            if boot.returncode != 0:
                raise RemError(f"launchctl bootstrap failed for {self.label}: {boot.stderr.strip()}")
            return {"scheduler": "launchd", "label": self.label, "installed": True, "time": time_str, "plist": str(path)}

        if self.platform.startswith("linux"):
            execute = " ".join(f'"{arg.replace(chr(34), chr(92) + chr(34))}"' for arg in cmd)
            service = "\n".join([
                "[Unit]", f"Description={self.description}", "",
                "[Service]", "Type=oneshot", f"ExecStart={execute}", "",
            ])
            timer = "\n".join([
                "[Unit]", f"Description={self.description} timer", "",
                "[Timer]", f"OnCalendar=*-*-* {time_str}:00", "Persistent=true", "",
                "[Install]", "WantedBy=timers.target", "",
            ])
            self._write_private(self.unit_path("service"), service)
            self._write_private(self.unit_path("timer"), timer)
            self.run(["systemctl", "--user", "daemon-reload"], capture_output=True, text=True, timeout=30)
            en = self.run(["systemctl", "--user", "enable", "--now", f"{self.label}.timer"], capture_output=True, text=True, timeout=30)
            if en.returncode != 0:
                raise RemError(f"systemctl enable failed for {self.label}: {en.stderr.strip()}")
            return {
                "scheduler": "systemd",
                "label": self.label,
                "installed": True,
                "time": time_str,
                "service": str(self.unit_path("service")),
                "timer": str(self.unit_path("timer")),
            }

        raise RemError(f"No supported background scheduler on platform {self.platform!r}")

    def uninstall(self) -> bool:
        if self.platform == "darwin":
            path = self.plist_path()
            self.run(["launchctl", "bootout", f"gui/{self.uid}/{self.label}"], capture_output=True, text=True, timeout=30)
            if path.exists():
                path.unlink()
                return True
            return False
        if self.platform.startswith("linux"):
            paths = [self.unit_path("service"), self.unit_path("timer")]
            removed = any(p.exists() for p in paths)
            self.run(["systemctl", "--user", "disable", "--now", f"{self.label}.timer"], capture_output=True, text=True, timeout=30)
            for p in paths:
                p.unlink(missing_ok=True)
            if removed:
                self.run(["systemctl", "--user", "daemon-reload"], capture_output=True, text=True, timeout=30)
            return removed
        return False

    def describe(self) -> dict[str, Any]:
        if self.platform == "darwin":
            path = self.plist_path()
            return {"scheduler": "launchd", "label": self.label, "installed": path.is_file(), "plist": str(path)}
        if self.platform.startswith("linux"):
            installed = self.unit_path("service").is_file() and self.unit_path("timer").is_file()
            return {"scheduler": "systemd", "label": self.label, "installed": installed, "timer": str(self.unit_path("timer"))}
        return {"scheduler": "none", "label": self.label, "installed": False}


class DailyUpgradeScheduler(_DailyCalendarJob):
    label = UPGRADE_LABEL
    description = "ConnectOnion daily atomic auto-upgrade"
    subcommand = ["rem", "upgrade", "run", "--scheduled"]


class MorningReaderScheduler(_DailyCalendarJob):
    label = MORNING_LABEL
    description = "ConnectOnion morning REM reader open"
    subcommand = ["rem", "open", "--morning"]
