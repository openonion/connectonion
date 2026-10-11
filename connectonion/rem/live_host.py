"""Start the existing co ai Host when the owner explicitly opens live REM."""

import os
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
    process = None
    with _owner_invite_lock(directory):
        if host_online(address):
            return None
        saved = read_json(state, {})
        if saved.get("address") != address or not _alive(saved):
            process = _spawn(directory)
            try:
                write_json(state, {"address": address, "pid": process.pid,
                                   "command": " ".join(process.args[1:])})
            except (OSError, RemError):
                _stop(process)
                raise
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return f"co ai exited during startup; see {log}. Retry with `co ai` to see the error"
        if host_online(address, timeout=min(1.0, max(0.01, deadline - time.monotonic()))):
            return None
        time.sleep(0.2)
    if process is not None:
        _stop(process)
    return f"co ai did not become reachable within {timeout:g}s; see {log}. Retry with `co ai`"
