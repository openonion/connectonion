"""Start the existing co ai Host when the owner explicitly opens live REM."""

import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

from .files import RemError, read_json, write_json


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


def _spawn(directory: Path):
    from ..environment import explicit_env_file

    command = [sys.executable, "-m", "connectonion.cli.main"]
    if selected := explicit_env_file():
        command += ["--env-file", str(selected)]
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


def ensure_online(address: str, *, timeout: float = 20.0) -> str | None:
    """Reuse one Host per identity; return an actionable reason on startup failure."""
    from ..cli.co_ai.main import _owner_invite_lock
    from ..project import selected_identity_dir
    from .reader import host_online

    directory = selected_identity_dir()
    state = directory / "rem-live-host.json"
    log = directory / "rem-live-host.log"
    process, saved = None, {}
    with _owner_invite_lock(directory):
        if host_online(address):
            return None
        saved = read_json(state, {})
        if saved.get("address") != address or not _alive(saved):
            process = _launch(directory, address)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return f"co ai exited during startup; see {log}. Retry with `co ai` to see the error"
        port = _port(process.args) if process is not None else saved.get("port")
        if port and answers(port, address):
            return None
        if host_online(address, timeout=min(1.0, max(0.01, deadline - time.monotonic()))):
            return None
        time.sleep(0.2)
    if process is not None:
        _stop(process)
    return f"co ai did not become reachable within {timeout:g}s; see {log}. Retry with `co ai`"


def _launch(directory: Path, address: str, *, background: bool = False):
    """Start co ai and remember it, so the next open reuses it; the caller holds the lock."""
    process = _spawn(directory)
    try:
        write_json(directory / "rem-live-host.json", {"address": address, "pid": process.pid,
                                                      "port": _port(process.args),
                                                      "command": " ".join(process.args[1:]),
                                                      **({"started_at": time.time()} if background else {})})
    except (OSError, RemError):
        _stop(process)
        raise
    return process


def saved_host_dead(address: str) -> bool:
    """This identity's Host was started before and its process is gone."""
    from ..project import selected_identity_dir
    saved = read_json(selected_identity_dir() / "rem-live-host.json", {})
    return saved.get("address") == address and not _alive(saved)


# A Host co rem open started in the background and found dead this soon after
# most likely never came up: say so, with its log, instead of "starting" again.
STARTUP_WINDOW = 600


def start(address: str) -> str | None:
    """Start this identity's Host unless ours is alive, and return without waiting:
    `co rem open` shows the saved page meanwhile. Returns what to tell the owner
    when the Host it started last time exited soon after."""
    from ..cli.co_ai.main import _owner_invite_lock
    from ..project import selected_identity_dir
    directory = selected_identity_dir()
    with _owner_invite_lock(directory):
        saved = read_json(directory / "rem-live-host.json", {})
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


def answers(port: int, address: str) -> bool:
    """Is this identity's Host serving on 127.0.0.1:port? Works with no network."""
    import httpx
    try:
        response = httpx.get(f"http://127.0.0.1:{port}/info", timeout=1.0)
    except httpx.HTTPError:
        return False
    return response.status_code == 200 and response.json().get("address") == address


def local_reader(address: str) -> str | None:
    """The base URL of this identity's Host on this computer, if one answers."""
    from ..project import selected_identity_dir
    saved = read_json(selected_identity_dir() / "rem-live-host.json", {})
    for port in dict.fromkeys(p for p in (saved.get("port"), DEFAULT_PORT) if isinstance(p, int)):
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
