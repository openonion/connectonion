"""Start the existing co ai Host when the owner explicitly opens live REM."""

import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from .files import RemError, read_json, write_json


def installed_version() -> str:
    """The connectonion version on disk: what a process started now would run.

    A Host started before an upgrade keeps the old `__version__` for as long as
    it lives, while the files under it are already the new release: the reader's
    Host served two days and two releases that way (#2937). Read from the file,
    because the installed distribution's metadata names the version at install
    time for an editable checkout.
    """
    import connectonion
    try:
        text = Path(connectonion.__file__).with_name("_version.py").read_text(encoding="utf-8")
    except OSError:
        return connectonion.__version__
    found = re.search(r"""^__version__\s*=\s*["']([^"']+)["']""", text, re.M)
    return found.group(1) if found else connectonion.__version__


def _alive(saved) -> bool:
    """A durable PID is reusable only while it still identifies our command."""
    pid, command = saved.get("pid"), saved.get("command")
    if not isinstance(pid, int) or pid <= 0 or not command:
        return False
    try:
        result = subprocess.run(["ps", "-ww", "-p", str(pid), "-o", "uid=", "-o", "command="],
                                capture_output=True, text=True, timeout=2)
    except subprocess.TimeoutExpired as error:
        raise OSError("could not verify the existing Host process; retry `co ai`") from error
    fields = result.stdout.strip().split(maxsplit=1)
    return (result.returncode == 0 and len(fields) == 2
            and fields[0] == str(os.getuid())
            and fields[1].endswith(command))


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


def ensure_online(address: str, *, timeout: float = 20.0, beside: bool = False) -> str | None:
    """Reuse one Host per identity; return an actionable reason on startup failure.

    Our own Host of another version is replaced. `beside` starts ours although
    the identity is online, when what is online is a co ai of another version
    that is not ours to stop (ensure_local).
    """
    from ..cli.co_ai.main import _owner_invite_lock
    from ..project import selected_identity_dir
    from .reader import host_online

    directory = selected_identity_dir()
    state = directory / "rem-live-host.json"
    log = directory / "rem-live-host.log"
    # ours_only: online is not enough, because the old Host is what was online.
    process, saved, ours_only = None, {}, beside
    with _owner_invite_lock(directory):
        saved = read_json(state, {})
        if _outdated(saved, address):
            process, ours_only = _renew(directory, saved, address), True
        elif not beside and host_online(address):
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
        if not ours_only and host_online(address, timeout=min(1.0, max(0.01, deadline - time.monotonic()))):
            return None
        time.sleep(0.2)
    if process is not None:
        _stop(process)
    return f"co ai did not become reachable within {timeout:g}s; see {log}. Retry with `co ai`"


def _launch(directory: Path, address: str, *, background: bool = False, port: int | None = None):
    """Start co ai and remember it, so the next open reuses it; the caller holds the lock."""
    process = _spawn(directory, port)
    try:
        write_json(directory / "rem-live-host.json", {"address": address, "pid": process.pid,
                                                      "port": _port(process.args),
                                                      "command": " ".join(process.args[1:]),
                                                      **({"started_at": time.time()} if background else {})})
    except (OSError, RemError):
        _stop(process)
        raise
    return process


def _retire(saved) -> None:
    """End the Host this record names: asked first, forced when it does not go.

    Only that process. Before each signal the pid must still be this user's
    process with the recorded command (_alive), so a pid the system has since
    given to something else is never signalled.
    """
    for sign, wait in ((signal.SIGTERM, 5.0), (getattr(signal, "SIGKILL", signal.SIGTERM), 2.0)):
        if not _alive(saved):
            return
        try:
            os.kill(saved["pid"], sign)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline and _alive(saved):
            time.sleep(0.1)
    if _alive(saved):
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


def _renew(directory: Path, saved, address: str, *, background: bool = False):
    """Stop our own Host of another version and start the installed one, on the
    same port when it is free again: a reader tab that was open keeps its address
    (its token is a file beside the key, so it is still good). The caller holds
    the lock and has just had _alive confirm the pid is that Host."""
    _retire(saved)
    port = saved.get("port")
    return _launch(directory, address, background=background,
                   port=port if isinstance(port, int) and _free(port) else None)


def _busy(directory: Path) -> bool:
    """A turn is in flight in the Host that keeps its sessions here: a conversation,
    an approval being waited for, or a scheduled run (they share this record)."""
    from ..network.host.session.storage import SessionStorage
    path = directory / "session_results.jsonl"
    return path.exists() and any(session.status in SessionStorage.UNFINISHED
                                 for session in SessionStorage(path).list())


def renew_idle() -> None:
    """Replace our own Host of another version when no turn is in flight.

    Called by the detached page build, which is the one piece of installed code
    a Host started before an upgrade still runs (a new Python each time). So a
    reader tab that was open before the upgrade works again on a reload with no
    command typed (D-60): its request starts a build, and the build ends here.
    A task started from the reader runs in its own process and is not touched;
    a busy Host is left for a later build or the next `co rem open`.
    """
    from ..project import selected_identity_dir
    directory = selected_identity_dir()

    def due():
        saved = read_json(directory / "rem-live-host.json", {})
        return saved if _outdated(saved, saved.get("address")) and not _busy(directory) else None
    if not due():  # without the lock: nearly every build ends here
        return
    from ..cli.co_ai.main import _owner_invite_lock
    with _owner_invite_lock(directory):
        if saved := due():  # again: another build, or an open, may have replaced it meanwhile
            _renew(directory, saved, saved["address"], background=True)


def _outdated(saved, address) -> bool:
    """The Host this record names is ours, alive, and says it is another version
    than the installed one: the only process co rem ever stops."""
    return bool(address) and saved.get("address") == address and _alive(saved) and _other_version(saved.get("port"), address)


def outdated(address: str) -> bool:
    """This identity's Host that co rem started is still the one from before an upgrade."""
    from ..project import selected_identity_dir
    return _outdated(read_json(selected_identity_dir() / "rem-live-host.json", {}), address)


def saved_host_dead(address: str) -> bool:
    """This identity's Host was started before and cannot serve the reader: its
    process is gone, or it is another version's, which the next start replaces."""
    from ..project import selected_identity_dir
    saved = read_json(selected_identity_dir() / "rem-live-host.json", {})
    return saved.get("address") == address and (not _alive(saved) or _outdated(saved, address))


# A Host co rem open started in the background and found dead this soon after
# most likely never came up: say so, with its log, instead of "starting" again.
STARTUP_WINDOW = 600


def start(address: str) -> str | None:
    """Start this identity's Host unless ours is alive at the installed version, and
    return without waiting: `co rem open` shows the saved page meanwhile. Returns
    what to tell the owner when the Host it started last time exited soon after."""
    from ..cli.co_ai.main import _owner_invite_lock
    from ..project import selected_identity_dir
    directory = selected_identity_dir()
    with _owner_invite_lock(directory):
        saved = read_json(directory / "rem-live-host.json", {})
        if _outdated(saved, address):
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
    return bool(info) and info.get("address") == address and info.get("version") == installed_version()


def _other_version(port, address: str) -> bool:
    """A server on this port says it is this identity's Host at a version that is
    not the installed one. No answer is not that: a Host still starting is current."""
    info = _info(port) if isinstance(port, int) else None
    return bool(info) and info.get("address") == address and info.get("version") != installed_version()


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
    runs; (None, reason) when there is no Host here to read through."""
    from ..project import selected_identity_dir
    if not (base := local_reader(address)):
        # A co ai of another version answers as this identity (#2937). It is why
        # the identity reads as online, and it is not used: ours is started beside
        # it. One that is not ours is never stopped; the owner may be using it.
        beside = any(_other_version(port, address) for port in _known_ports())
        if failure := (ensure_online(address, beside=True) if beside else ensure_online(address)):
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
