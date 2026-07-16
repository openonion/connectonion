r"""
Purpose: Cross-platform IPC primitives for the browser daemon/client so `co browser` runs natively on Windows (named pipes) as well as macOS/Linux (Unix sockets) — no WSL.
LLM-Note:
  Dependencies: imports from [os, time, getpass, subprocess, tempfile, hashlib, binascii, threading, multiprocessing.connection, pathlib | lazy: fcntl/msvcrt, ctypes] | imported by [browser_agent/daemon.py, browser_agent/client.py] | tested by [tests/unit/test_transport.py, tests/e2e/cli/test_browser_daemon.py]
  Data flow: daemon/client call default_address() → POSIX returns a Unix-socket filesystem path (unchanged from before), Windows returns a per-user named pipe \\.\pipe\co-browser-<hash> | pid_path()/lock_path() resolve real filesystem sidecars (POSIX: <addr>.pid/.lock exactly as before; Windows: hashed files under %LOCALAPPDATA%/co since a pipe name is not a path) | Windows wire: win_listener() creates the pipe WITHOUT an authkey and the daemon runs the mutual HMAC challenge itself via accept_authenticated() under a hard deadline (mpc's own accept()-time handshake blocks forever on a stalled client — a wedged single-threaded daemon); win_connect() is a normal authenticated mpc.Client | POSIX keeps its raw AF_UNIX socket in daemon.py/client.py untouched
  State/Effects: default_address()/_sidecar_dir() may mkdir the runtime dir (and chmod 0700 on POSIX — the socket dir IS the POSIX trust boundary, so a chmod failure raises loudly) | load_or_create_authkey() creates a 0600 key file in the sidecar dir (only used on Windows) and atomically replaces a persistently-corrupt one | acquire_singleton_lock() holds an OS lock (fcntl.flock POSIX / msvcrt.locking Windows) for the daemon's lifetime, released by the OS on death | spawn_detached() launches the daemon fully detached
  Integration: exposes IS_WINDOWS, AuthenticationError (= mpc's class), HANDSHAKE_TIMEOUT, default_address(), pid_path(), lock_path(), load_or_create_authkey(), pid_alive(), acquire_singleton_lock(), spawn_detached(), win_listener(), win_connect(), bounded_io(), accept_authenticated() | POSIX behavior is intentionally identical to the pre-existing raw-socket code so existing tests pass unchanged; only the Windows branch is new
  Performance: all helpers are cheap local ops | authkey is a 64-byte file read | bounded_io adds one short-lived thread per bounded pipe operation (handshake/read/reply — never touches Playwright)
  Errors: acquire_singleton_lock returns None when the lock is held (caller exits 0) | pid_alive treats EPERM/access-denied as ALIVE (the pid exists — same lesson as browser.py's _pid_alive) | load_or_create_authkey converges on ONE key under the O_EXCL create race, atomically replaces a file that stays invalid past the writers' microsecond window, and RAISES if no valid key can be produced — it never falls back to a fixed key, which would silently disable authentication | bounded_io raises TimeoutError on deadline (after closing the connection so the helper unblocks) and re-raises the operation's own exception otherwise | accept_authenticated returns None on a bad key, a stalled handshake, or a vanished client (the daemon keeps serving); a closed listener still raises out of accept() so a dying daemon exits instead of spinning
"""

import os
import time
import getpass
import subprocess
import tempfile
import hashlib
import binascii
import threading
import multiprocessing.connection as mpc
from pathlib import Path

IS_WINDOWS = os.name == "nt"

# The class mpc raises when the HMAC challenge fails — re-exported so callers write
# `except transport.AuthenticationError:` without importing multiprocessing themselves.
AuthenticationError = mpc.AuthenticationError

# The mutual HMAC handshake is three tiny local messages — normally sub-millisecond.
# The deadline exists for a client that connects and then stalls mid-challenge.
HANDSHAKE_TIMEOUT = 10.0


def _current_user() -> str:
    try:
        return getpass.getuser()
    except (OSError, KeyError):  # stripped service env: no env vars and no pwd entry
        return "user"


def _sidecar_dir() -> Path:
    r"""A real filesystem directory for .pid/.lock/authkey sidecars.

    A Windows named-pipe address (\\.\pipe\...) is not a filesystem path, so the
    sidecars cannot sit next to it — they live in a per-user runtime dir instead.
    On POSIX this is the same dir the socket lives in, so sidecar paths stay
    byte-identical to the pre-existing `<sock>.pid` / `<sock>.lock`.
    """
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "co"
        base.mkdir(parents=True, exist_ok=True)
    else:
        runtime = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
        base = Path(runtime) / "co"
        base.mkdir(parents=True, exist_ok=True)
        # This dir is the POSIX trust boundary (any local user who can reach the
        # socket can drive the browser) — a failed chmod must be loud, not skipped.
        os.chmod(base, 0o700)
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
    return str(_sidecar_dir() / "browser.sock")


def _addr_key(address: str) -> str:
    # Pipe names are case-insensitive on Windows — normalize so two spellings of the
    # same pipe can never read each other's pid/lock sidecars as different daemons.
    return "browser-" + hashlib.sha1(address.lower().encode()).hexdigest()[:12]


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


def _read_key(key_file: Path):
    """The key bytes if the file holds a valid key, else None."""
    try:
        data = key_file.read_bytes().strip()
    except OSError:
        return None
    return data if len(data) >= 16 else None


def _write_key_exclusive(path: Path):
    """Create `path` with a fresh key. Returns None if the path already exists
    (another writer won the race) or cannot be created."""
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError:
        return None
    try:
        key = binascii.hexlify(os.urandom(32))
        os.write(fd, key)
        return key
    finally:
        os.close(fd)


def _replace_corrupt_key(key_file: Path):
    """Atomically publish a fresh key over a corrupt one (a crashed writer's leftover).
    Returns the new key, or None if the swap could not be completed."""
    tmp = key_file.with_name(f"authkey.{os.getpid()}.tmp")
    key = _write_key_exclusive(tmp)
    if key is None:
        return None
    try:
        os.replace(str(tmp), str(key_file))
    except OSError:  # e.g. Windows: the target is held open by another process
        os.unlink(str(tmp))
        return None
    return key


def load_or_create_authkey() -> bytes:
    """A per-user secret shared by daemon and client for the named-pipe HMAC handshake.

    Only used on Windows (POSIX relies on the 0700 socket dir). Fails CLOSED: this
    returns a valid ≥16-byte key or raises — never a fixed or empty fallback, which
    would silently turn the authentication boundary into a constant. Concurrent
    cold-starts converge on one key (O_EXCL decides the writer; readers wait out the
    microsecond create→write window), and a file that stays invalid past that window
    is a crashed writer's leftover, replaced atomically.
    """
    key_file = _sidecar_dir() / "authkey"
    for attempt in range(50):
        key = _read_key(key_file)
        if key:
            return key
        if not key_file.exists():
            key = _write_key_exclusive(key_file)
            if key:
                return key
        elif attempt >= 5:  # invalid for >100ms — corrupt leftover, not a mid-write race
            key = _replace_corrupt_key(key_file)
            if key:
                return key
        time.sleep(0.02)
    raise RuntimeError(
        f"could not create or read a valid browser IPC auth key at {key_file} — "
        "remove that file and retry"
    )


def pid_alive(pid: int) -> bool:
    """True when `pid` names a running process.

    EPERM / access-denied means the pid EXISTS but belongs to another user — that is
    ALIVE (the same lesson browser.py's _pid_alive learned; reporting a live daemon
    dead is how you end up with two daemons fighting over one Chrome profile).
    """
    if pid <= 0:
        return False
    if IS_WINDOWS:
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        ERROR_ACCESS_DENIED = 5
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return ctypes.get_last_error() == ERROR_ACCESS_DENIED
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
    except PermissionError:
        return True
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
# POSIX keeps its raw AF_UNIX socket in daemon.py/client.py; these are Windows-only
# in production, but accept_authenticated() is family-agnostic so its handshake
# bounding is unit-tested on every platform.

def win_listener(address: str):
    """A named-pipe Listener WITHOUT an authkey — the handshake is deliberately not
    run inside accept() (see accept_authenticated) so it can be deadline-bounded."""
    return mpc.Listener(address, family="AF_PIPE")


def win_connect(address: str, authkey: bytes):
    """Connect to the daemon's named pipe, authenticating with the shared key."""
    return mpc.Client(address, family="AF_PIPE", authkey=authkey)


def bounded_io(conn, fn, timeout: float):
    """Run one blocking pipe operation under a hard deadline.

    mpc named-pipe Connections have no native timeouts anywhere — not in the accept
    handshake, not mid-frame in recv_bytes, not in send_bytes against a full pipe with
    a stalled reader. Any of those would wedge the single-threaded daemon forever
    (POSIX gets all of this from one settimeout(120)). The operation runs in a
    short-lived helper thread joined against the deadline; on timeout the connection
    is closed (which errors the helper's blocked syscall, so the thread exits) and
    TimeoutError raises. The helper's own exception re-raises here unchanged.
    """
    outcome = {}

    def _run():
        try:
            outcome["value"] = fn()
        except Exception as exc:  # captured, then re-raised on the caller's thread
            outcome["error"] = exc

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(timeout)
    if "value" in outcome:
        return outcome["value"]
    if "error" in outcome:
        raise outcome["error"]
    conn.close()
    raise TimeoutError(f"pipe operation timed out after {timeout:.0f}s")


def accept_authenticated(listener, authkey: bytes, timeout: float = HANDSHAKE_TIMEOUT):
    """Accept one connection and run the mutual HMAC challenge under a hard deadline.

    mpc's `Listener(authkey=...)` runs the challenge INSIDE accept() with blocking
    recvs — a client that connects and then stalls mid-handshake would wedge the
    single-threaded daemon forever, and the request read timeout starts too late to
    help. So win_listener() creates the pipe without an authkey and the challenge
    runs here, deadline-bounded. A closed/broken listener still raises out of
    accept() — a dying daemon must exit its serve loop, not spin on a dead endpoint.

    Returns the authenticated connection, or None (bad key, stall, or vanished client).
    """
    conn = listener.accept()

    def _handshake():
        mpc.deliver_challenge(conn, authkey)
        mpc.answer_challenge(conn, authkey)
        return True

    try:
        bounded_io(conn, _handshake, timeout)
        return conn
    except Exception:  # bad digest, stall (TimeoutError), vanished client → reject
        conn.close()
        return None
