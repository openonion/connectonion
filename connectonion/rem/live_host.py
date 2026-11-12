"""Start the existing co ai Host when the owner explicitly opens live REM."""

import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from .files import RemError, read_json, write_json


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
        return subprocess.run(["ps", *args], capture_output=True, text=True, timeout=2)
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
        elif host_online(address):
            return None
        elif saved.get("address") != address or not _alive(saved):
            process = _launch(directory, address)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
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


def _launch(directory: Path, address: str, *, background: bool = False, port: int | None = None,
            renewed_for: str | None = None):
    """Start co ai and remember it, so the next open reuses it; the caller holds the lock."""
    process = _spawn(directory, port)
    try:
        write_json(directory / "rem-live-host.json", {"address": address, "pid": process.pid,
                                                      "port": _port(process.args),
                                                      "command": " ".join(process.args[1:]),
                                                      "install": _install(),
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
            return Notice(_kept(port, version, recorded=port == saved.get("port")))
    port, version = others[0]
    if saved.get("renewed_for") == installed:
        return Notice(f"The server co rem started on port {port} to replace the one from before the upgrade "
                      f"runs {_named(version)}, not {installed}; it is not replaced again.")
    return BUSY if _busy(directory) or not build and _inside(saved["pid"]) else REPLACE


# _upgrade's answer when the Host this install started is idle: replace it.
REPLACE = "replace"


def _kept(port: int, version, *, recorded: bool) -> str:
    """Why a co ai of another version on `port` is not stopped, in words that are true."""
    if NO_PS and recorded:
        why = "on Windows co rem cannot check that the process is still the one it started, so it is not stopped"
    elif recorded:
        why = "this install cannot confirm it started it, so it is not stopped"
    else:
        why = "co rem did not start it, so it is not stopped"
    return (f"A co ai of {_named(version)} answers as you on port {port}; {why}, "
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
        _launch(directory, address, background=True)
    if exited:
        return (f"co ai exited during startup; see {directory / 'rem-live-host.log'}. "
                "Starting it again; retry with `co ai` to see the error")
    return None


# `co ai`'s own default port: a Host the owner started by hand is usually here.
DEFAULT_PORT = 8000


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
    """Where this identity's Host can be on this computer: the port co rem started it on, then co ai's default."""
    from ..project import selected_identity_dir
    saved = read_json(selected_identity_dir() / "rem-live-host.json", {})
    return list(dict.fromkeys(p for p in (saved.get("port"), DEFAULT_PORT) if isinstance(p, int)))


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
        with os.fdopen(fd, "w") as output:
            output.write(secrets.token_urlsafe(32))
    return path.read_text().strip()


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
