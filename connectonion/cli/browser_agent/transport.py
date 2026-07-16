"""
Purpose: Cross-platform IPC primitives for the browser daemon/client so `co browser` runs natively on Windows (named pipes) as well as macOS/Linux (Unix sockets) — no WSL.
LLM-Note:
  Dependencies: imports from [os, sys, subprocess, tempfile, hashlib, binascii, pathlib | lazy: fcntl/msvcrt, ctypes, multiprocessing.connection] | imported by [browser_agent/daemon.py, browser_agent/client.py] | tested by [tests/e2e/cli/test_browser_daemon.py, tests/e2e/cli/test_transport.py]
  Data flow: daemon/client call default_address() → POSIX returns a Unix-socket filesystem path (unchanged from before), Windows returns a per-user named pipe \\.\pipe\co-browser-<hash> | pid_path()/lock_path() resolve real filesystem sidecars (POSIX: <addr>.pid/.lock exactly as before; Windows: hashed files under %LOCALAPPDATA%/co since a pipe name is not a path) | on Windows the wire uses multiprocessing.connection Listener/Client with an HMAC authkey (win_listener/win_connect); POSIX keeps its raw AF_UNIX socket in daemon.py/client.py untouched
  State/Effects: default_address()/_sidecar_dir() may mkdir + chmod 0700 the runtime dir | load_or_create_authkey() writes ~/.co-scoped 0600 key file (Windows path only) | acquire_singleton_lock() holds an OS lock (fcntl.flock POSIX / msvcrt.locking Windows) for the daemon's lifetime, released by the OS on death | spawn_detached() launches the daemon fully detached
  Integration: exposes IS_WINDOWS, default_address(), pid_path(), lock_path(), load_or_create_authkey(), pid_alive(), acquire_singleton_lock(), spawn_detached(), win_listener(), win_connect(), AuthenticationError | POSIX behavior is intentionally identical to the pre-existing raw-socket code so existing tests pass unchanged; only the Windows branch is new
  Performance: all helpers are cheap local ops | authkey/liveness are single file/syscall
  Errors: acquire_singleton_lock returns None when the lock is held (caller exits 0) | pid_alive False on any probe failure | load_or_create_authkey resolves a single shared key even under a create race (O_EXCL)
"""

import os
import sys
import subprocess
import tempfile
import hashlib
import binascii
from pathlib import Path

IS_WINDOWS = os.name == "nt"


def _current_user() -> str:
    for var in ("USERNAME", "USER", "LOGNAME"):
        value = os.environ.get(var)
        if value:
            return value
    return "user"


def _sidecar_dir() -> Path:
    """A real filesystem directory for .pid/.lock/authkey sidecars.

    A Windows named-pipe address (\\.\pipe\...) is not a filesystem path, so the
    sidecars cannot sit next to it — they live in a per-user runtime dir instead.
    On POSIX this is the same dir the socket lives in, so sidecar paths stay
    byte-identical to the pre-existing `<sock>.pid` / `<sock>.lock`.
    """
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "co"
    else:
        runtime = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
        base = Path(runtime) / "co"
    base.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(base, 0o700)
    except OSError:
        pass
    return base


def default_address() -> str:
    """The daemon endpoint. $CO_BROWSER_SOCK overrides on both platforms.

    POSIX: a Unix-socket path under $XDG_RUNTIME_DIR/co (or $TMPDIR/co) — unchanged.
    Windows: a per-user named pipe (the pipe namespace is machine-global, so it is
    scoped by username to avoid cross-user collisions).
    """
    override = os.environ.get("CO_BROWSER_SOCK")
    if override:
        return override
    if IS_WINDOWS:
        who = hashlib.sha1(_current_user().encode()).hexdigest()[:12]
        return r"\\.\pipe\co-browser-" + who
    runtime = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    base = Path(runtime) / "co"
    base.mkdir(parents=True, exist_ok=True)
    os.chmod(base, 0o700)
    return str(base / "browser.sock")


def _addr_key(address: str) -> str:
    return "browser-" + hashlib.sha1(address.encode()).hexdigest()[:12]


def pid_path(address: str) -> str:
    """Sidecar recording the owner pid. POSIX: `<address>.pid` (unchanged)."""
    if IS_WINDOWS:
        return str(_sidecar_dir() / (_addr_key(address) + ".pid"))
    return address + ".pid"


def lock_path(address: str) -> str:
    """Sidecar holding the lifetime singleton lock. POSIX: `<address>.lock` (unchanged)."""
    if IS_WINDOWS:
        return str(_sidecar_dir() / (_addr_key(address) + ".lock"))
    return address + ".lock"


def load_or_create_authkey() -> bytes:
    """A per-user secret shared by daemon and client for the named-pipe HMAC handshake.

    Only used on Windows (POSIX relies on the 0700 socket dir). Created atomically
    with O_EXCL so concurrent cold-starts converge on ONE key rather than racing to
    write different ones.
    """
    key_file = _sidecar_dir() / "authkey"
    for _ in range(6):
        if key_file.exists():
            data = key_file.read_bytes().strip()
            if len(data) >= 16:
                return data
        try:
            fd = os.open(str(key_file), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue  # someone else just created it — loop back and read it
        except OSError:
            break
        try:
            os.write(fd, binascii.hexlify(os.urandom(32)))
        finally:
            os.close(fd)
    try:
        return key_file.read_bytes().strip()
    except OSError:
        return b"co-browser-local"


def pid_alive(pid: int) -> bool:
    """True when `pid` names a running process. POSIX: os.kill(pid, 0). Windows: OpenProcess."""
    if pid <= 0:
        return False
    if IS_WINDOWS:
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
    except (OSError, OverflowError, ValueError):
        return False
    return True


def acquire_singleton_lock(path: str):
    """Take an exclusive, non-blocking, lifetime lock. Returns the open handle to keep
    alive (the OS releases it on process death, SIGKILL included), or None if held.

    POSIX: fcntl.flock. Windows: msvcrt.locking on the first byte.
    """
    handle = open(path, "a+")
    try:
        if IS_WINDOWS:
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def spawn_detached(cmd, log_file):
    """Launch `cmd` fully detached so it outlives the client. POSIX: new session.
    Windows: DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP."""
    if IS_WINDOWS:
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        return subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    return subprocess.Popen(
        cmd, stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True
    )


# ---- Windows named-pipe wire (multiprocessing.connection + HMAC authkey) ----
# POSIX keeps its raw AF_UNIX socket in daemon.py/client.py; these are Windows-only.

def _mpc():
    import multiprocessing.connection as mpc
    return mpc


def win_listener(address: str, authkey: bytes):
    """A named-pipe Listener with HMAC auth. Raises if another daemon already owns the name."""
    return _mpc().Listener(address, family="AF_PIPE", authkey=authkey)


def win_connect(address: str, authkey: bytes):
    """Connect to the daemon's named pipe, authenticating with the shared key."""
    return _mpc().Client(address, family="AF_PIPE", authkey=authkey)


def AuthenticationError():
    """The exception class raised on a failed authkey handshake (for except clauses)."""
    return _mpc().AuthenticationError
