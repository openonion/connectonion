"""Start the existing co ai Host when the owner explicitly opens live REM."""

import os
import plistlib
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .files import RemError, read_json, write_json

# Per-user macOS LaunchAgent label for REM live Host (#3317).
# Running the Host inside `gui/$UID` (`Aqua` GUI session) keeps Keychain / Touch ID
# prompts working even when upgrades or background agents restart it.
REM_HOST_LABEL = "ai.openonion.rem-host"


def version_on_disk() -> str:
    """The connectonion version in the installed files: what a process started now runs.

    A Host started before an upgrade keeps the old `__version__` for as long as
    it lives, while the files under it are already the new release: the reader's
    Host served two days and two releases that way (#2937). Not the installed
    distribution's metadata (cli/commands/listen_commands.py installed_version):
    for an editable checkout that names the version at install time, and /info
    reports `__version__`, which is this file.
    """
    import runpy
    import connectonion
    return runpy.run_path(str(Path(connectonion.__file__).with_name("_version.py")))["__version__"]


def _ps(*args):
    try:
        return subprocess.run(["ps", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2)
    except subprocess.TimeoutExpired as error:
        raise OSError("could not verify the existing Host process; retry `co ai`") from error


def _command_line(pid: int) -> str | None:
    """This user's process `pid` as `ps` prints its command line; None when there is none."""
    result = _ps("-ww", "-p", str(pid), "-o", "uid=", "-o", "command=")
    fields = result.stdout.strip().split(maxsplit=1)
    ours = result.returncode == 0 and len(fields) == 2 and fields[0] == str(os.getuid())
    return fields[1] if ours else None


def _alive(saved) -> bool:
    """A durable PID is reusable only while it still identifies our command."""
    pid, command = saved.get("pid"), saved.get("command")
    if not isinstance(pid, int) or pid <= 0 or not command:
        return False
    line = _command_line(pid)
    return line is not None and line.endswith(command)


# Windows has no ps: see _started_here.
NO_PS = os.name == "nt"


def _install() -> str:
    """This install: the connectonion package folder this process runs."""
    import connectonion
    return str(Path(connectonion.__file__).resolve().parent)


def _started_here(saved) -> bool:
    """The recorded Host is alive and is one this install started.

    "This install" is the package folder the record names (`install`, written by
    _launch), compared with this process's own; "alive and still that process" is
    _alive (our uid, the recorded command at the end of what ps prints). A record
    written before `install` existed (a 1.9.5 Host's, which is what an owner has
    right after the upgrade) is matched by what ps prints in full: this
    interpreter, then the command. That holds where ps shows sys.executable (a uv
    tool or a venv) and fails, reporting instead of replacing, on a macOS
    framework Python, whose ps shows the binary inside Python.app.

    Never on Windows: there is no ps to tell that a pid is still that Host, and a
    process is not signalled on a guess. There a Host of another version is only
    reported, never replaced.
    """
    pid, command = saved.get("pid"), saved.get("command")
    if NO_PS or not isinstance(pid, int) or pid <= 0 or not command:
        return False
    if "install" in saved:
        return saved["install"] == _install() and _alive(saved)
    return _command_line(pid) == f"{sys.executable} {command}"


def _spawn(directory: Path, port: int | None = None):
    from ..environment import explicit_env_file

    command = [sys.executable, "-m", "connectonion.cli.main"]
    if selected := explicit_env_file():
        command += ["--env-file", str(selected)]
    if port is None:
        port = _preferred_port({})
    if port is None:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
    command += ["ai", "--port", str(port), "--no-listen", "--no-launch"]
    log = directory / "rem-live-host.log"
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "ab") as output:
        return subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output,
                                stderr=subprocess.STDOUT, start_new_session=True)


def _stop(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


class Notice(str):
    """One sentence for the owner, shown beside the snapshot as it is: not a failure.
    A server of another version keeps the reader, and this says which and why."""


def ensure_online(address: str, *, timeout: float = 20.0) -> str | None:
    """Reuse one Host per identity; return an actionable reason on startup failure,
    or a Notice when a server of another version keeps the reader (_upgrade).

    Our own idle Host of another version is replaced.
    """
    from ..cli.co_ai.main import _owner_invite_lock
    from ..project import selected_identity_dir
    from .reader import host_online

    directory = selected_identity_dir()
    state = directory / "rem-live-host.json"
    log = directory / "rem-live-host.log"
    # renewed: online is not enough, because the old Host is what was online.
    process, saved, renewed = None, {}, False
    with _owner_invite_lock(directory):
        saved = read_json(state, {})
        held = _upgrade(directory, saved, address)
        if isinstance(held, Notice):
            return held
        if held is REPLACE:
            process, renewed = _renew(directory, saved, address, wait=timeout / 2), True
        elif _moves_to_session(directory, saved, address):
            _retire(saved)
            port = saved.get("port")
            process, renewed = _launch(directory, address, port=port if isinstance(port, int) and _free(port) else None), True
        elif host_online(address) and not _gone(saved, address):
            return None
        elif saved.get("address") != address or not _alive(saved):
            process = _launch(directory, address, port=_saved_port(saved))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and getattr(process, "poll", lambda: None)() is not None:
            return f"co ai exited during startup; see {log}. Retry with `co ai` to see the error"
        port = _port(process.args) if process is not None else saved.get("port")
        if port and answers(port, address):
            return None
        if not renewed and host_online(address, timeout=min(1.0, max(0.01, deadline - time.monotonic()))):
            return None
        time.sleep(0.2)
    if process is not None:
        _stop(process)
    return f"co ai did not become reachable within {timeout:g}s; see {log}. Retry with `co ai`"


def launch_session() -> str:
    """launchd's manager for this process on macOS, "" elsewhere (#3305).

    "Aqua" is the owner's GUI login session; "Background" is a process an agent, ssh or a detached shell
    started. A Host inherits the session of whoever launched it, and only an Aqua Host can raise system
    prompts such as the Keychain's 允许: from a Background Host, `security … -w` fails at once.
    """
    if sys.platform != "darwin":
        return ""
    try:
        done = subprocess.run(["launchctl", "managername"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip()


def _moves_to_session(directory: Path, saved, address: str) -> bool:
    """Our idle Host runs outside the owner's login session, and this open can move it into Aqua (#3305, #3317).

    Agents restart the Host after an upgrade from a Background session, which leaves it unable to show the
    Keychain prompt. When the owner opens REM from Terminal (Aqua) or when the macOS `gui/$UID` LaunchAgent
    domain is available, the Host moves into Aqua once: the new record says Aqua. A record from before this
    field is treated as outside.
    """
    can_enter_aqua = launch_session() == "Aqua" or _use_host_agent()
    return (can_enter_aqua and saved.get("session") != "Aqua" and saved.get("address") == address
            and _started_here(saved) and not _busy(directory) and not _inside(saved["pid"]))


def _current_uid(uid: int | None = None) -> int:
    return uid if uid is not None else (os.getuid() if hasattr(os, "getuid") else 0)


def host_agent_plist_path(agents_dir: Path | None = None) -> Path:
    """Path to the per-user macOS LaunchAgent plist for REM live Host (#3317)."""
    base = Path(agents_dir) if agents_dir is not None else Path.home() / "Library" / "LaunchAgents"
    return base / f"{REM_HOST_LABEL}.plist"


def host_agent_installed(agents_dir: Path | None = None) -> bool:
    """True when the REM live Host LaunchAgent plist is present on disk."""
    return host_agent_plist_path(agents_dir).is_file()


def gui_domain_available(*, uid: int | None = None, run=subprocess.run, platform: str | None = None) -> bool:
    """True on macOS when the user's `gui/$UID` launchd session is reachable (#3317)."""
    if (platform or sys.platform) != "darwin":
        return False
    try:
        done = run(["launchctl", "print", f"gui/{_current_uid(uid)}"],
                   capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def _use_host_agent() -> bool:
    """Use the per-user macOS `gui/$UID` LaunchAgent when available outside unit test stubs."""
    if sys.platform != "darwin" or os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return gui_domain_available()


def _host_command(port: int, *, python_bin: str | Path | None = None, env_file: str | Path | None = None) -> list[str]:
    from ..environment import explicit_env_file

    exe = str(python_bin or sys.executable)
    command = [exe, "-m", "connectonion.cli.main"]
    selected = env_file if env_file is not None else explicit_env_file()
    if selected:
        command += ["--env-file", str(selected)]
    command += ["ai", "--port", str(port), "--no-listen", "--no-launch"]
    return command


def _write_private_plist(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = plistlib.dumps(data, sort_keys=False).decode("utf-8")
    fd, name = tempfile.mkstemp(prefix=f".{REM_HOST_LABEL}-", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write(text)
    os.chmod(name, 0o600)
    os.replace(name, path)


def _parse_launchctl_print(stdout: str) -> dict:
    info: dict = {}
    for raw_line in (stdout or "").splitlines():
        line = raw_line.strip()
        if line.startswith("pid = "):
            value = line.split("=", 1)[1].strip()
            if value.isdigit():
                info["pid"] = int(value)
        elif line.startswith("state = "):
            info["state"] = line.split("=", 1)[1].strip()
        elif line.startswith("session = "):
            info["session"] = line.split("=", 1)[1].strip()
    return info


def install_host_agent(
    directory: Path,
    port: int | None = None,
    *,
    python_bin: str | Path | None = None,
    env_file: str | Path | None = None,
    agents_dir: Path | None = None,
    uid: int | None = None,
    run=subprocess.run,
    platform: str | None = None,
    bootstrap: bool = True,
) -> dict:
    """Install/refresh `~/Library/LaunchAgents/ai.openonion.rem-host.plist` in `gui/$UID` (#3317).

    Sets `LimitLoadToSessionType = Aqua` and `ProcessType = Interactive` so any restart
    (including automated overnight upgrades or background agent shells) runs the REM live
    Host inside the owner's Aqua GUI session where Keychain / Touch ID prompts work.
    """
    plat = platform or sys.platform
    if plat != "darwin":
        return {"installed": False, "bootstrapped": False, "label": REM_HOST_LABEL,
                "platform": plat, "reason": "macOS only"}

    directory = Path(directory).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    resolved_port = port
    if resolved_port is None:
        saved = read_json(directory / "rem-live-host.json", {})
        resolved_port = _preferred_port(saved)
    if resolved_port is None:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            resolved_port = int(reservation.getsockname()[1])
    command = _host_command(resolved_port, python_bin=python_bin, env_file=env_file)
    env = {
        "HOME": str(Path.home()),
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    }
    if python_bin is None:
        from .schedule import _checkout_path
        if checkout := _checkout_path():
            env["PYTHONPATH"] = checkout

    log_file = str(directory / "rem-live-host.log")
    job = {
        "Label": REM_HOST_LABEL,
        "ProgramArguments": command,
        "LimitLoadToSessionType": "Aqua",
        "ProcessType": "Interactive",
        "RunAtLoad": False,
        "KeepAlive": False,
        "WorkingDirectory": str(directory),
        "EnvironmentVariables": env,
        "StandardOutPath": log_file,
        "StandardErrorPath": log_file,
    }
    path = host_agent_plist_path(agents_dir)
    _write_private_plist(path, job)

    resolved_uid = _current_uid(uid)
    domain = f"gui/{resolved_uid}"
    bootstrapped = False
    error = ""
    if bootstrap:
        try:
            run(["launchctl", "bootout", f"{domain}/{REM_HOST_LABEL}"],
                capture_output=True, text=True, timeout=30)
            boot = run(["launchctl", "bootstrap", domain, str(path)],
                       capture_output=True, text=True, timeout=30)
            bootstrapped = boot.returncode == 0
            if not bootstrapped:
                error = (boot.stderr or boot.stdout or "launchctl bootstrap failed").strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            error = str(exc)

    return {
        "installed": True,
        "bootstrapped": bootstrapped,
        "label": REM_HOST_LABEL,
        "domain": domain,
        "plist": str(path),
        "port": resolved_port,
        "command": command,
        **({"error": error} if error else {}),
    }


def kickstart_host_agent(
    *,
    uid: int | None = None,
    agents_dir: Path | None = None,
    run=subprocess.run,
    platform: str | None = None,
) -> dict:
    """Start or restart `ai.openonion.rem-host` inside the owner's `gui/$UID` Aqua session (#3317)."""
    plat = platform or sys.platform
    if plat != "darwin":
        return {"ok": False, "label": REM_HOST_LABEL, "platform": plat, "error": "macOS only"}

    resolved_uid = _current_uid(uid)
    domain = f"gui/{resolved_uid}"
    target = f"{domain}/{REM_HOST_LABEL}"
    error = ""
    ok = False
    try:
        res = run(["launchctl", "kickstart", "-k", target], capture_output=True, text=True, timeout=30)
        ok = res.returncode == 0
        if not ok:
            path = host_agent_plist_path(agents_dir)
            if path.is_file():
                boot = run(["launchctl", "bootstrap", domain, str(path)],
                           capture_output=True, text=True, timeout=30)
                if boot.returncode == 0:
                    res = run(["launchctl", "kickstart", "-k", target],
                              capture_output=True, text=True, timeout=30)
                    ok = res.returncode == 0
            if not ok:
                error = (res.stderr or res.stdout or "launchctl kickstart failed").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        error = str(exc)

    pid = None
    if ok:
        try:
            printed = run(["launchctl", "print", target], capture_output=True, text=True, timeout=10)
            if printed.returncode == 0:
                pid = _parse_launchctl_print(printed.stdout).get("pid")
        except (OSError, subprocess.TimeoutExpired):
            pass

    return {
        "ok": ok,
        "label": REM_HOST_LABEL,
        "domain": domain,
        "target": target,
        "pid": pid,
        **({"error": error} if not ok and error else {}),
    }


def uninstall_host_agent(
    *,
    uid: int | None = None,
    agents_dir: Path | None = None,
    run=subprocess.run,
    platform: str | None = None,
) -> bool:
    """Cleanly bootout and remove the `ai.openonion.rem-host` LaunchAgent plist (#3317; reversible)."""
    if (platform or sys.platform) != "darwin":
        return False
    resolved_uid = _current_uid(uid)
    target = f"gui/{resolved_uid}/{REM_HOST_LABEL}"
    bootout_ok = False
    try:
        res = run(["launchctl", "bootout", target], capture_output=True, text=True, timeout=30)
        bootout_ok = res.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        pass
    path = host_agent_plist_path(agents_dir)
    existed = path.exists()
    if existed:
        path.unlink(missing_ok=True)
    return existed or bootout_ok


def host_session_info(
    directory: Path | None = None,
    *,
    uid: int | None = None,
    agents_dir: Path | None = None,
    run=subprocess.run,
    platform: str | None = None,
) -> dict:
    """Report which macOS launchd session (`Aqua` vs `Background` / `non-macOS`) the REM live Host is in (#3317)."""
    plat = platform or sys.platform
    resolved_uid = _current_uid(uid)
    if directory is None:
        from ..project import selected_identity_dir
        directory = selected_identity_dir()
    directory = Path(directory)
    saved = read_json(directory / "rem-live-host.json", {})
    saved = saved if isinstance(saved, dict) else {}
    running = False if NO_PS else _alive(saved)
    pid = saved.get("pid") if running else None
    port = saved.get("port") if isinstance(saved.get("port"), int) else None

    agent_installed = plat == "darwin" and host_agent_plist_path(agents_dir).is_file()
    agent_loaded = False
    agent_pid = None
    if plat == "darwin":
        try:
            printed = run(["launchctl", "print", f"gui/{resolved_uid}/{REM_HOST_LABEL}"],
                          capture_output=True, text=True, timeout=10)
            if printed.returncode == 0:
                agent_loaded = True
                agent_pid = _parse_launchctl_print(printed.stdout).get("pid")
        except (OSError, subprocess.TimeoutExpired):
            pass
        if not running and agent_loaded and agent_pid:
            running = True
            pid = agent_pid

    if plat != "darwin":
        session = "non-macOS"
    elif not running:
        session = "stopped"
    elif agent_loaded and (agent_pid == pid or saved.get("via_launch_agent")):
        session = "Aqua"
    elif saved.get("session") in ("Aqua", "Background"):
        session = saved["session"]
    else:
        session = "Background"
        if isinstance(pid, int) and pid > 0:
            try:
                proc = run(["launchctl", "procinfo", str(pid)], capture_output=True, text=True, timeout=5)
                if proc.returncode == 0:
                    parsed = _parse_launchctl_print(proc.stdout)
                    if parsed.get("session") in ("Aqua", "Background"):
                        session = parsed["session"]
            except (OSError, subprocess.TimeoutExpired):
                pass

    stuck_in_background = plat == "darwin" and running and session != "Aqua"
    recovery_command = ""
    if stuck_in_background:
        if agent_installed:
            recovery_command = f"launchctl kickstart -k gui/{resolved_uid}/{REM_HOST_LABEL}"
        else:
            recovery_command = "co rem open --live"

    return {
        "platform": plat,
        "running": bool(running),
        "pid": pid,
        "port": port,
        "session": session,
        "launch_agent_label": REM_HOST_LABEL,
        "launch_agent_installed": agent_installed,
        "launch_agent_loaded": agent_loaded,
        "launch_agent_pid": agent_pid,
        "stuck_in_background": stuck_in_background,
        "ok": not stuck_in_background,
        "recovery_command": recovery_command,
    }


class _AgentProcess:
    """Process handle for a REM live Host started via macOS `gui/$UID` LaunchAgent (#3317)."""

    def __init__(self, pid: int, args: list[str], *, uid: int | None = None, run=subprocess.run):
        self.pid = pid
        self.args = list(args)
        self._command = " ".join(self.args[1:])
        self._uid = _current_uid(uid)
        self._run = run

    def poll(self):
        if self.pid <= 0:
            return None
        return None if _alive({"pid": self.pid, "command": self._command}) else 0

    def terminate(self):
        try:
            self._run(["launchctl", "bootout", f"gui/{self._uid}/{REM_HOST_LABEL}"],
                      capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if self.pid > 0:
            try:
                os.kill(self.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def kill(self):
        if self.pid > 0:
            try:
                os.kill(self.pid, getattr(signal, "SIGKILL", signal.SIGTERM))
            except ProcessLookupError:
                pass

    def wait(self, timeout=None):
        return 0


def _launch(directory: Path, address: str, *, background: bool = False, port: int | None = None,
            renewed_for: str | None = None):
    """Start co ai and remember it, so the next open reuses it; the caller holds the lock."""
    via_agent = False
    process = None
    if _use_host_agent():
        chosen_port = port if port is not None else _preferred_port({})
        installed = install_host_agent(directory, port=chosen_port)
        if installed.get("installed") and installed.get("bootstrapped"):
            kicked = kickstart_host_agent()
            if kicked.get("ok"):
                via_agent = True
                process = _AgentProcess(kicked.get("pid") or 0, installed["command"])
    if process is None:
        process = _spawn(directory, port)
    try:
        write_json(directory / "rem-live-host.json", {"address": address, "pid": process.pid,
                                                      "port": _port(process.args),
                                                      "command": " ".join(process.args[1:]),
                                                      "install": _install(),
                                                      "session": "Aqua" if via_agent else launch_session(),
                                                      **({"via_launch_agent": True, "label": REM_HOST_LABEL} if via_agent else {}),
                                                      **({"renewed_for": renewed_for} if renewed_for else {}),
                                                      **({"started_at": time.time()} if background else {})})
    except (OSError, RemError):
        _stop(process)
        raise
    return process


# How long each signal is given: SIGTERM first, then SIGKILL.
STOP_SECONDS = 5.0


def _retire(saved) -> None:
    """End the Host this record names: asked first, forced when it does not go.

    Only that process. Before each signal the pid must still be the Host this
    install started (_started_here), so a pid the system has since given to
    something else is never signalled.
    """
    for sign in (signal.SIGTERM, getattr(signal, "SIGKILL", signal.SIGTERM)):
        if not _started_here(saved):
            return
        try:
            os.kill(saved["pid"], sign)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + STOP_SECONDS
        while time.monotonic() < deadline and _started_here(saved):
            time.sleep(0.1)
    if _started_here(saved):
        raise OSError(f"the co ai started before the upgrade (pid {saved['pid']}) did not stop")


def _free(port: int) -> bool:
    """Would co ai's bind on this port succeed? The same check as its own (server._port_in_use)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def _renew(directory: Path, saved, address: str, *, background: bool = False, wait: float | None = None):
    """Stop our own Host of another version and start the installed one, on the
    same port when it is free again: a reader tab that was open keeps its address
    (its token is a file beside the key, so it is still good). The caller holds
    the lock and has had _upgrade decide.

    The new record says `renewed_for` the installed version, and only it: a stop
    that failed raises before it is written, and every other launch writes a
    record without it. It is read only while the Host that record names answers,
    so it never speaks of a replacement that did not come up.

    With `wait`, a new Host that exits within it (the port was taken between the
    check and its bind, or it failed to start) is started once more on a free
    port, which the record then names. One still starting is left to start: moving
    it would change an open tab's address.
    """
    _retire(saved)
    port = saved.get("port")
    renewed = version_on_disk()
    process = _launch(directory, address, background=background, renewed_for=renewed,
                      port=port if isinstance(port, int) and _free(port) else None)
    if wait is None or not _exits(process, address, wait):
        return process
    return _launch(directory, address, background=background, renewed_for=renewed)


def _exits(process, address: str, wait: float) -> bool:
    """The new Host exited before it answered, within `wait`."""
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline and process.poll() is None:
        if answers(_port(process.args), address):
            return False
        time.sleep(0.2)
    return process.poll() is not None


BUSY = Notice("The server from before the upgrade is finishing a task; the page switches by itself afterwards.")


def _busy(directory: Path) -> bool:
    """The Host that keeps its records here has unfinished work, of any age.

    Read: session_results.jsonl rows still `running` or `waiting_approval` (a
    conversation, an approval being waited for, or a scheduled `run:` turn, which
    takes the same path), and schedule-state.json entries marked `running` (a
    scheduled `exec:` command, which writes no session row). No age makes one
    stale: a Host marks every earlier Host's unfinished rows interrupted and
    running entries failed when it starts (SessionStorage.reconcile_interrupted,
    schedule.py on_startup), so what is unfinished is the running Host's, an
    approval waiting overnight included.
    """
    from ..network.host.schedule import load_state
    from ..network.host.session.storage import SessionStorage
    path = directory / "session_results.jsonl"
    if path.exists() and any(s.status in SessionStorage.UNFINISHED for s in SessionStorage(path).list()):
        return True
    return any(isinstance(entry, dict) and entry.get("status") == "running"
               for entry in load_state(directory).values())


def _inside(pid: int) -> bool:
    """This process descends from `pid`. Parents are walked, because a turn's shell
    runs in a session of its own (useful_tools/bash.py), so the session id differs."""
    current = os.getppid()
    while current > 1:
        if current == pid:
            return True
        result = _ps("-o", "ppid=", "-p", str(current))
        if result.returncode != 0 or not result.stdout.strip().isdigit():
            raise OSError(f"could not read the parent of process {current}, so co ai was left as it is")
        current = int(result.stdout.strip())
    return False


def _named(version) -> str:
    return f"version {version}" if version else "a version that does not say which"


def _upgrade(directory: Path, saved, address, *, build: bool = False):
    """What to do about servers of another version answering as this identity on
    the ports co rem knows. None: there are none. A Notice: one stays, and why;
    nothing is signalled and nothing is started beside it. A list: the Host this
    install started is idle and is replaced; the list names stale work stopping with it.

    An open run inside that Host (a turn running `co rem open`) is that Host's own
    work, whatever its age. The page `build` is a child of that Host too, started
    for this, so for it that is not work in flight.
    """
    installed = version_on_disk()
    others = [(port, info.get("version")) for port in _known_ports()
              if (info := _info(port)) and info.get("address") == address and info.get("version") != installed]
    if not others:
        return None
    ours = saved.get("address") == address and _started_here(saved)
    for port, version in others:
        if not (ours and port == saved.get("port")):
            return Notice(_kept(port, version, pid=saved.get("pid") if port == saved.get("port") else None))
    port, version = others[0]
    if saved.get("renewed_for") == installed:
        return Notice(f"The server co rem started on port {port} to replace the one from before the upgrade "
                      f"runs {_named(version)}, not {installed}; it is not replaced again.")
    return BUSY if _busy(directory) or not build and _inside(saved["pid"]) else REPLACE


# _upgrade's answer when the Host this install started is idle: replace it.
REPLACE = "replace"


def _kept(port: int, version, *, pid) -> str:
    """Why a co ai of another version on `port` is not stopped, in words that are true.
    `pid` is the record's, when the record names that port: the process to close."""
    recorded = pid is not None
    if NO_PS and recorded:
        why = "on Windows co rem cannot check that the process is still the one it started, so it is not stopped"
    elif recorded:
        why = "this install cannot confirm it started it, so it is not stopped"
    else:
        why = "co rem did not start it, so it is not stopped"
    which = f"port {port} (pid {pid})" if recorded else f"port {port}"
    return (f"A co ai of {_named(version)} answers as you on {which}; {why}, "
            "and live actions return when that co ai is closed.")


# How long the build waits for the new Host to answer or exit.
RENEW_WAIT = 30.0


def renew_idle() -> None:
    """Replace our own idle Host of another version, from the detached page build.

    The build is the one piece of installed code a Host started before an upgrade
    still runs (a new Python each time). So a reader tab that was open before the
    upgrade works again on a reload with no command typed (D-60): its request
    starts a build, and the build ends here. A busy Host, or one this install did
    not start, is left as it is (_upgrade). Nothing on Windows (_started_here).
    """
    if NO_PS:
        return
    from ..project import selected_identity_dir
    directory = selected_identity_dir()

    def due():
        saved = read_json(directory / "rem-live-host.json", {})
        held = _upgrade(directory, saved, saved.get("address"), build=True) if saved.get("address") else None
        return saved if held is REPLACE else None
    if not due():  # without the lock: nearly every build ends here
        return
    from ..cli.co_ai.main import _owner_invite_lock
    with _owner_invite_lock(directory):
        if saved := due():  # again: another build, or an open, may have replaced it meanwhile
            process = _renew(directory, saved, saved["address"], background=True, wait=RENEW_WAIT)
            print(f"Replaced the server from before the upgrade: co ai pid {process.pid} on port {_port(process.args)}.")


# The Host watches for an upgrade itself (#3112): the build that replaces an idle old Host (renew_idle) used to run
# only when an open page polled, so with no tab open the old code was served until the next `co rem open`.
UPGRADE_CHECK = 60    # seconds between looks at the installed version
UPGRADE_RETRY = 600   # while still the old release (busy, or the build failed), start the build again this often


def notice_upgrade(root, kicked: dict, *, now=time.monotonic) -> bool:
    """When this process runs an older release than is installed, start the page build: it runs the installed code
    and replaces this Host on the same port once it is idle (renew_idle, _upgrade). Once per installed release, then
    every UPGRADE_RETRY while this Host is still the old one. `kicked` is the caller's memory of when."""
    from .._version import __version__ as running
    installed = version_on_disk()
    if installed == running or installed in kicked and now() - kicked[installed] < UPGRADE_RETRY:
        return False
    kicked[installed] = now()
    from .reader import owner_changed
    owner_changed(Path(root))
    return True


def _gone(saved, address: str) -> bool:
    """The record names this address's Host, that process is gone, and nothing answers locally as the address.

    Then the relay's listing is stale (it holds a dead Host's registration for a while) and is not trusted:
    after the owner's Host was killed, `co rem open --live` believed it and started nothing (#3112). A Host
    the owner started by hand answers on a known port, so it is still reused, never doubled.
    """
    return (saved.get("address") == address and not _alive(saved)
            and not any(answers(port, address) for port in _known_ports()))


def recorded_gone(address: str) -> bool:
    """_gone for this identity's record: the live open asks before trusting the relay."""
    from ..project import selected_identity_dir
    return _gone(read_json(selected_identity_dir() / "rem-live-host.json", {}), address)


def _preferred_port(saved) -> int | None:
    """Stable preferred local port for the REM live Host.

    Reuses `saved["port"]` when free (#3130); otherwise picks the first free
    port in REM's dedicated range (`REM_DEFAULT_PORT`..`REM_DEFAULT_PORT+19`)
    so fresh launches and restarts stay on a predictable local address instead
    of jumping to a random OS port. Returns None only if all 20 ports are busy.
    """
    port = saved.get("port") if isinstance(saved, dict) else None
    if isinstance(port, int) and _free(port):
        return port
    for candidate in range(REM_DEFAULT_PORT, REM_DEFAULT_PORT + REM_PORT_SPAN):
        if _free(candidate):
            return candidate
    return None


def _saved_port(saved):
    """The port the last Host had, when it is free, or REM's preferred stable port."""
    return _preferred_port(saved)


def outdated(address: str) -> bool:
    """A server of another version answers as this identity on a port co rem knows."""
    return any(_other_version(port, address) for port in _known_ports())


def saved_host_dead(address: str) -> bool:
    """This identity's Host was started before and cannot serve the reader: its
    process is gone, or another version answers on its port."""
    from ..project import selected_identity_dir
    saved = read_json(selected_identity_dir() / "rem-live-host.json", {})
    return saved.get("address") == address and (not _alive(saved) or _other_version(saved.get("port"), address))


# A Host co rem open started in the background and found dead this soon after
# most likely never came up: say so, with its log, instead of "starting" again.
STARTUP_WINDOW = 600


def start(address: str) -> str | None:
    """Start this identity's Host unless ours is alive at the installed version, and
    return without waiting: `co rem open` shows the saved page meanwhile. Returns
    what to tell the owner: the Host it started last time exited soon after, a
    server of another version keeps the reader (a Notice), or what stopped with
    the one replaced."""
    from ..cli.co_ai.main import _owner_invite_lock
    from ..project import selected_identity_dir
    directory = selected_identity_dir()
    with _owner_invite_lock(directory):
        saved = read_json(directory / "rem-live-host.json", {})
        held = _upgrade(directory, saved, address)
        if isinstance(held, Notice):
            return held
        if held is REPLACE:
            _renew(directory, saved, address, background=True)
            return None
        if saved.get("address") == address and _alive(saved):
            return None
        exited = (saved.get("address") == address and isinstance(saved.get("started_at"), (int, float))
                  and time.time() - saved["started_at"] < STARTUP_WINDOW)
        _launch(directory, address, background=True, port=_saved_port(saved))
    if exited:
        return (f"co ai exited during startup; see {directory / 'rem-live-host.log'}. "
                "Starting it again; retry with `co ai` to see the error")
    return None


# `co ai`'s own default port: a Host the owner started by hand is usually here.
DEFAULT_PORT = 8000
# Dedicated default port for REM's background live Host, keeping bookmarks and
# repeated `co rem open` calls stable without colliding with common dev ports.
REM_DEFAULT_PORT = 18765
REM_PORT_SPAN = 20


def _port(args) -> int | None:
    return int(args[args.index("--port") + 1]) if "--port" in args else None


def _info(port: int):
    """What the server on 127.0.0.1:port says it is (/info), or None. Works with no network."""
    import httpx
    try:
        response = httpx.get(f"http://127.0.0.1:{port}/info", timeout=1.0)
        info = response.json() if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError):  # ValueError: something else has the port and does not speak JSON
        return None
    return info if isinstance(info, dict) else None


def answers(port: int, address: str) -> bool:
    """Is this identity's Host serving on 127.0.0.1:port, at the installed version?

    The address alone was the test, and a co ai left running from fifty releases
    back on port 8000 passed it: `co rem open` sent the owner there and every
    page was "Internal Server Error" (#2937).
    """
    info = _info(port)
    return bool(info) and info.get("address") == address and info.get("version") == version_on_disk()


def _other_version(port, address: str) -> bool:
    """A server on this port says it is this identity's Host at a version that is
    not the installed one. No answer is not that: a Host still starting is current."""
    info = _info(port) if isinstance(port, int) else None
    return bool(info) and info.get("address") == address and info.get("version") != version_on_disk()


def _known_ports() -> list:
    """Where this identity's Host can be on this computer: the recorded port, REM's default port, then co ai's default."""
    from ..project import selected_identity_dir
    saved = read_json(selected_identity_dir() / "rem-live-host.json", {})
    return list(dict.fromkeys(p for p in (saved.get("port"), REM_DEFAULT_PORT, DEFAULT_PORT) if isinstance(p, int)))


def local_reader(address: str) -> str | None:
    """The base URL of this identity's Host on this computer, if one answers."""
    for port in _known_ports():
        if answers(port, address):
            return f"http://127.0.0.1:{port}"
    return None


# Said when this open started (or finds starting) the identity's own Host and
# its port does not answer yet. Plain words: there is nothing to run.
STARTING = "The live reader is starting; this time shows the saved page, and the next open is live."
# ensure_online returns once the relay sees the Host, which can be before its own
# port answers: wait this long for the port before saying it is starting.
LOCAL_WAIT = 5.0


def ensure_local(address: str) -> tuple[str | None, str | None]:
    """(url, None) for the live reader on this computer, starting co ai when none
    runs; (None, reason) when there is no Host here to read through, a Notice when
    a server of another version keeps it (#2937)."""
    from ..project import selected_identity_dir
    if not (base := local_reader(address)):
        if failure := ensure_online(address):
            return None, failure
        base = local_reader(address) or _ours_coming_up(address)
    if base is STARTING:
        return None, STARTING
    if not base:
        # Online (the relay or an endpoint answers as this identity), yet no Host
        # of ours runs here: then, and only then, it is another co ai.
        return None, ("co ai is running, but not on a port co rem knows (8000 or one it started); "
                      "use `co rem open --live`, or stop that co ai and open again")
    return f"{base}/rem?token={reader_token(selected_identity_dir())}", None


def _ours_coming_up(address: str):
    """The base URL once the Host co rem started answers on its port; STARTING while it
    is alive and not yet answering; None when no Host of ours is running."""
    from ..project import selected_identity_dir
    saved = read_json(selected_identity_dir() / "rem-live-host.json", {})
    if saved.get("address") != address or not isinstance(saved.get("port"), int) or not _alive(saved):
        return None
    deadline = time.monotonic() + LOCAL_WAIT
    while time.monotonic() < deadline:
        if answers(saved["port"], address):
            return f"http://127.0.0.1:{saved['port']}"
        time.sleep(0.2)
    return STARTING


def reader_token(directory: Path) -> str:
    """The local reader's secret, beside the Host's key and as private (rem_http.py)."""
    path = directory / "rem-reader-token"
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(secrets.token_urlsafe(32))
    return path.read_text(encoding="utf-8").strip()


def live_link() -> str:
    """The live reader on this computer, for a snapshot's one sentence (D-60: a link, never a
    command); "" without an identity. The file page that carries it is the owner's own (mode
    600), as private as the token beside the Host's key. Served by co ai, which `co rem open` starts."""
    from ..address import load
    from ..project import selected_identity_dir
    directory = selected_identity_dir()
    if not load(directory):
        return ""
    port = read_json(directory / "rem-live-host.json", {}).get("port") or DEFAULT_PORT
    return f"http://127.0.0.1:{port}/rem?token={reader_token(directory)}"
