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
import time
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
    if channel not in ("stable", "preview"):
        raise RemError(f"Unsupported ConnectOnion release channel: {channel!r}")
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


def _wait_for_idle_notebook(root: Path, *, scheduled: bool) -> bool:
    deadline = time.monotonic() + (15 * 60 if scheduled else 0)
    while rem_turn_active(root):
        if time.monotonic() >= deadline:
            return False
        time.sleep(5)
    return True


def _prewarm_installed_reader(root: Path, directory: Path | None) -> str:
    """Prepare the reader with the installed release before considering Host replacement."""
    from . import live_host, reader

    if not reader.refresh(root):
        return "build_busy"
    if directory is not None:
        return live_host.renew_idle(directory=directory)
    return "ready"


def prewarm_reader(root: Path, python_bin: Path, *, directory: Path | None, run) -> str:
    """Wait for the installed worker and propagate preparation or restart failures."""
    if not (root / "config.yaml").is_file():
        return "no_notebook"
    cmd = [
        str(python_bin), "-I", "-c",
        "import sys; from pathlib import Path; "
        "from connectonion.rem.auto_upgrade import _prewarm_installed_reader; "
        "print(_prewarm_installed_reader(Path(sys.argv[1]), Path(sys.argv[2]) if sys.argv[2] else None))",
        str(root.resolve()), str(directory) if directory is not None else "",
    ]
    result = run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900)
    if result.returncode:
        error = (result.stderr or result.stdout).strip().splitlines()
        raise RemError(error[-1] if error else f"reader worker exited with status {result.returncode}")
    status = result.stdout.strip().splitlines()
    if not status or status[-1] not in {"ready", "build_busy", "busy", "restarted", "unchanged", "kept"}:
        raise RemError("reader worker returned no recognized result")
    return status[-1]


def _finish_reader_upgrade(home: Path, root: Path, python: Path, upgrade: dict, *, run) -> dict:
    directory = _co_dir(home)
    try:
        status = prewarm_reader(root, python, directory=directory if root.resolve() == directory / "rem" else None, run=run)
    except (OSError, RemError, subprocess.SubprocessError) as error:
        return {**upgrade, "outcome": "failed", "phase": "reader", "prewarmed": False,
                "error": f"Installed {upgrade['to']}; reader preparation or restart failed: {error}"}
    if status == "build_busy":
        return {**upgrade, "outcome": "deferred_reader", "phase": "reader", "prewarmed": False,
                "reason": "Another reader build holds the lock; the existing build or the next check will retry."}
    return {**upgrade, "prewarmed": status != "no_notebook", "reader": status,
            **({"phase": "reader"} if status == "busy" else {})}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _install_spec(target: str) -> str:
    return f"connectonion=={target}"


def _uv_install_args(uv: str, target: str, *, force: bool = False, offline: bool = False) -> list[str]:
    args = [uv, "tool", "install", "--no-config", "--default-index", "https://pypi.org/simple",
            "--python", sys._base_executable]
    if force:
        args.append("--force")
    if offline:
        args.append("--offline")
    else:
        args.append("--refresh")
    if Version(target).is_prerelease:
        args.append("--prerelease=allow")
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
    scheduled: bool = False,
) -> dict[str, Any]:
    """Check and atomically upgrade a uv-tool ConnectOnion install, preserving the old binary on any failure."""
    home_dir = _home_dir(home)
    rem_root = Path(root) if root is not None else home_dir / ".co" / "rem"
    config = read_upgrade_config(home_dir)
    installed = current_version()

    if scheduled and not config["enabled"]:
        return {"outcome": "disabled", "current": installed, "at": _now_iso()}

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
            prior = read_upgrade_state(home_dir)
            if (prewarm and not dry_run and prior.get("phase") == "reader"
                    and prior.get("root") == str(rem_root.resolve()) and prior.get("to") == installed):
                upgrade = _upgrade_result(prior.get("from", installed), installed, config["channel"], rem_root)
                result = _finish_reader_upgrade(home_dir, rem_root, _tool_python(Path(install_info["uv_tool_dir"])),
                                                upgrade, run=run)
                return write_upgrade_state(result, home_dir)
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

    if not _wait_for_idle_notebook(rem_root, scheduled=scheduled and not dry_run):
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

    if scheduled and not read_upgrade_config(home_dir)["enabled"]:
        return {"outcome": "disabled", "current": installed, "at": _now_iso()}

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
    # The scheduler is authorized to install the official package only. Ignore uv
    # environment overrides (indexes, constraints, find-links) and Python imports
    # supplied by the caller. Set the two tool paths explicitly in each phase.
    base_env = {key: value for key, value in os.environ.items()
                if not key.startswith(("UV_", "PYTHON"))}

    # Phase 1: Stage into an isolated UV_TOOL_DIR and verify import + CLI before touching live `co`.
    try:
        _install_upgrade(uv, target, live_tools, live_bin, base_env, run)
    except (OSError, RemError, subprocess.SubprocessError) as error:
        return write_upgrade_state({
            "outcome": "failed", "current": installed, "target": target,
            "error": str(error)[:500], "at": _now_iso(),
        }, home_dir)

    upgrade = _upgrade_result(installed, target, config["channel"], rem_root)
    if prewarm:
        write_upgrade_state({**upgrade, "outcome": "preparing_reader", "phase": "reader"}, home_dir)
        upgrade = _finish_reader_upgrade(home_dir, rem_root, _tool_python(live_tools), upgrade, run=run)
    return write_upgrade_state(upgrade, home_dir)


def _install_upgrade(uv, target, live_tools, live_bin, base_env, run) -> None:
    with tempfile.TemporaryDirectory(prefix="co-upgrade-stage-") as stage_raw:
        stage_tools = Path(stage_raw) / "tools"
        stage_bin = Path(stage_raw) / "bin"
        stage_env = {**base_env, "UV_TOOL_DIR": str(stage_tools), "UV_TOOL_BIN_DIR": str(stage_bin)}
        staged = run(_uv_install_args(uv, target, force=True, offline=False), capture_output=True, text=True, env=stage_env, timeout=300)
        if staged.returncode != 0:
            err = (staged.stderr or staged.stdout or "staging uv tool install failed").strip()
            raise RemError(f"Staged install failed (previous version kept): {err[:400]}")

        stage_co = _bin_co(stage_bin)
        stage_py = _tool_python(stage_tools)
        verify_cmd = [str(stage_py), "-I", "-c", f"import connectonion; assert connectonion.__version__ == {target!r}"]
        verified_py = run(verify_cmd, capture_output=True, text=True, env=stage_env, timeout=60)
        verified_cli = run([str(stage_co), "--version"], capture_output=True, text=True, env=stage_env, timeout=60)
        if verified_py.returncode != 0 or verified_cli.returncode != 0:
            err = (verified_py.stderr or verified_cli.stderr or "staged verification failed").strip()
            raise RemError(f"Staged verification failed (previous version kept): {err[:400]}")

        # Phase 2: Backup live tool dir, promote from warm cache, verify, or roll back immediately.
        live_pkg = live_tools / "connectonion"
        backup_pkg = live_tools / f".connectonion.backup-{os.getpid()}"
        live_co = _bin_co(live_bin)
        backup_co = Path(stage_raw) / "previous-co"
        had_backup = False
        try:
            if live_pkg.is_dir():
                if backup_pkg.exists():
                    shutil.rmtree(backup_pkg)
                shutil.copytree(live_pkg, backup_pkg, symlinks=True)
                if live_co.is_file() or live_co.is_symlink():
                    shutil.copy2(live_co, backup_co, follow_symlinks=False)
                had_backup = True

            live_env = {**base_env, "UV_TOOL_DIR": str(live_tools), "UV_TOOL_BIN_DIR": str(live_bin)}
            promoted = run(_uv_install_args(uv, target, force=True, offline=True), capture_output=True, text=True, env=live_env, timeout=300)
            if promoted.returncode != 0:
                promoted = run(_uv_install_args(uv, target, force=True, offline=False), capture_output=True, text=True, env=live_env, timeout=300)
            if promoted.returncode != 0:
                raise RemError((promoted.stderr or promoted.stdout or "live swap failed").strip())

            check_live = run([str(live_co), "--version"], capture_output=True, text=True, env=live_env, timeout=60)
            if check_live.returncode != 0:
                raise RemError((check_live.stderr or "post-swap co --version check failed").strip())
        except Exception as error:
            if had_backup and backup_pkg.is_dir():
                if live_pkg.exists():
                    shutil.rmtree(live_pkg, ignore_errors=True)
                shutil.move(str(backup_pkg), str(live_pkg))
                live_co.unlink(missing_ok=True)
                if backup_co.is_file() or backup_co.is_symlink():
                    shutil.copy2(backup_co, live_co, follow_symlinks=False)
            if had_backup:
                raise RemError(f"Swap failed and rolled back: {error}") from error
            raise RemError(f"Swap failed: {error}") from error
        else:
            if had_backup:
                shutil.rmtree(backup_pkg, ignore_errors=True)


def _upgrade_result(installed: str, target: str, channel: str, root: Path) -> dict:
    return {"outcome": "upgraded", "from": installed, "to": target, "target": target, "channel": channel,
            "root": str(root.resolve()), "prewarmed": False, "at": _now_iso()}


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

    def _co_cmd(self) -> list[str]:
        if self.command:
            return list(self.command)
        return [sys.executable, "-I", "-m", "connectonion.cli.main"]

    def describe(self) -> dict[str, Any]:
        job = super().describe()
        if not job["installed"]:
            return job
        if self.platform == "darwin":
            command = ["launchctl", "print", f"gui/{self.uid}/{self.label}"]
        else:
            command = ["systemctl", "--user", "is-active", "--quiet", f"{self.label}.timer"]
        try:
            result = self.run(command, capture_output=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return job
        return {**job, "loaded": result.returncode == 0}


class MorningReaderScheduler(_DailyCalendarJob):
    label = MORNING_LABEL
    description = "ConnectOnion morning REM reader open"
    subcommand = ["rem", "open", "--morning"]
