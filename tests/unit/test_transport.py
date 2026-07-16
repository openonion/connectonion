"""
LLM-Note: Cross-platform transport primitives for the browser daemon/client.

What it tests (runs on BOTH POSIX and Windows CI):
- default_address honors $CO_BROWSER_SOCK; pid_path/lock_path derive real filesystem sidecars
- pid_alive: True for this process, False for a dead/invalid pid
- load_or_create_authkey: stable across calls; SELF-HEALS an empty/truncated key file
  (a crashed writer's leftover) by atomic replacement; concurrent callers converge on
  one key; never returns a weak fallback
- acquire_singleton_lock: exclusive + non-blocking, released on close
- spawn_detached: launches a detached child that actually runs
- bounded_io: returns the operation's value, re-raises its exception, and closes the
  connection + raises TimeoutError when the operation stalls past the deadline
- accept_authenticated: a correct key round-trips; a wrong key is rejected; a client
  that connects and NEVER speaks the challenge cannot wedge the acceptor (returns None
  within the deadline, and a well-behaved client succeeds right after)

Component under test: connectonion.cli.browser_agent.transport
"""

import os
import sys
import time
import threading
import multiprocessing.connection as mpc

import pytest

from connectonion.cli.browser_agent import transport as tp


def test_default_address_honors_override(monkeypatch):
    monkeypatch.setenv("CO_BROWSER_SOCK", "custom-endpoint-xyz")
    assert tp.default_address() == "custom-endpoint-xyz"


def test_pid_and_lock_paths_are_distinct_filesystem_paths():
    addr = tp.default_address()
    pid_p, lock_p = tp.pid_path(addr), tp.lock_path(addr)
    assert pid_p != lock_p
    # both must be creatable filesystem paths (a Windows pipe name is not)
    assert not pid_p.startswith(r"\\.\pipe")
    assert not lock_p.startswith(r"\\.\pipe")
    if not tp.IS_WINDOWS:
        assert pid_p == addr + ".pid"      # POSIX layout unchanged
        assert lock_p == addr + ".lock"


def test_sidecar_keying_is_case_insensitive():
    # Windows pipe names are case-insensitive; two spellings of one pipe must share sidecars.
    if tp.IS_WINDOWS:
        assert tp.pid_path(r"\\.\pipe\CO-X") == tp.pid_path(r"\\.\pipe\co-x")


def test_pid_alive():
    assert tp.pid_alive(os.getpid()) is True
    assert tp.pid_alive(0) is False
    assert tp.pid_alive(-1) is False
    # a pid that is almost certainly not running
    assert tp.pid_alive(4000000000) is False


@pytest.fixture
def keydir(monkeypatch, tmp_path):
    """Isolate the sidecar dir away from the real runtime dirs."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return tmp_path / "co"


def test_authkey_is_stable_and_created(keydir):
    first = tp.load_or_create_authkey()
    second = tp.load_or_create_authkey()
    assert isinstance(first, bytes) and len(first) >= 16
    assert first == second  # a second call returns the same persisted key
    assert (keydir / "authkey").exists()


def test_authkey_heals_an_empty_file(keydir):
    """A crash between O_EXCL create and write leaves a 0-byte file — it must be
    atomically replaced with a valid key, not brick the CLI forever."""
    keydir.mkdir(parents=True, exist_ok=True)
    (keydir / "authkey").write_bytes(b"")
    key = tp.load_or_create_authkey()
    assert len(key) >= 16
    assert (keydir / "authkey").read_bytes().strip() == key  # healed on disk too


def test_authkey_heals_a_truncated_file(keydir):
    keydir.mkdir(parents=True, exist_ok=True)
    (keydir / "authkey").write_bytes(b"short")  # < 16 bytes: invalid
    key = tp.load_or_create_authkey()
    assert len(key) >= 16
    assert key != b"short"


def test_authkey_concurrent_callers_converge(keydir):
    """N threads racing the first creation must all end up with the SAME key."""
    results = []
    threads = [threading.Thread(target=lambda: results.append(tp.load_or_create_authkey()))
               for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert len(results) == 8
    assert len(set(results)) == 1


def test_singleton_lock_is_exclusive_and_releasable(tmp_path):
    lock_file = str(tmp_path / "x.lock")
    first = tp.acquire_singleton_lock(lock_file)
    assert first is not None
    # a second acquire while the first is held must fail (non-blocking)
    assert tp.acquire_singleton_lock(lock_file) is None
    first.close()  # releasing lets a fresh acquire succeed
    again = tp.acquire_singleton_lock(lock_file)
    assert again is not None
    again.close()


def test_spawn_detached_runs_a_child(tmp_path):
    marker = tmp_path / "ran.txt"
    code = f"open(r'{marker}', 'w').write('ok')"
    with open(tmp_path / "out.log", "a") as log:
        tp.spawn_detached([sys.executable, "-c", code], log)
    deadline = time.time() + 10
    while time.time() < deadline and not marker.exists():
        time.sleep(0.05)
    assert marker.exists(), "detached child did not run"


# ---- bounded_io: the anti-wedge primitive -----------------------------------

class _FakeConn:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_bounded_io_returns_value_and_reraises():
    conn = _FakeConn()
    assert tp.bounded_io(conn, lambda: 42, timeout=5) == 42
    with pytest.raises(ValueError):
        tp.bounded_io(conn, lambda: (_ for _ in ()).throw(ValueError("boom")), timeout=5)
    assert conn.closed is False  # fast completion never touches the connection


def test_bounded_io_times_out_and_closes():
    conn = _FakeConn()
    release = threading.Event()
    with pytest.raises(TimeoutError):
        tp.bounded_io(conn, release.wait, timeout=0.2)  # op stalls past the deadline
    assert conn.closed is True  # closed so a real blocked syscall would unblock
    release.set()  # let the helper thread finish


# ---- the authenticated wire (Windows named pipe / POSIX unix socket) --------
# In production only the Windows daemon uses this handshake; the helpers are
# family-agnostic, so the SAME code paths are exercised on the POSIX CI leg too.

def _wire_address():
    if tp.IS_WINDOWS:
        return rf"\\.\pipe\co_wire_{os.getpid()}_{time.time_ns()}"
    return f"/tmp/co_wire_{os.getpid()}_{time.time_ns()}.sock"


def _wire_listener(address):
    if tp.IS_WINDOWS:
        return tp.win_listener(address)   # product code path on Windows
    return mpc.Listener(address)          # AF_UNIX inferred from the path


def _wire_client(address, authkey):
    if tp.IS_WINDOWS:
        return tp.win_connect(address, authkey)  # product code path on Windows
    return mpc.Client(address, authkey=authkey)


def _serve_once(listener, authkey, hold, timeout=5.0):
    """Accept + authenticate one client (deadline-bounded) and echo one message."""
    conn = tp.accept_authenticated(listener, authkey, timeout=timeout)
    hold["conn"] = conn
    if conn is not None:
        data = conn.recv_bytes()
        conn.send_bytes(b"echo:" + data)
        conn.close()


def _start_server(listener, authkey, timeout=5.0):
    hold = {}
    thread = threading.Thread(target=_serve_once, args=(listener, authkey, hold),
                              kwargs={"timeout": timeout}, daemon=True)
    thread.start()
    return hold, thread


def test_wire_round_trip_with_correct_authkey():
    address, key = _wire_address(), b"K" * 32
    listener = _wire_listener(address)
    hold, server = _start_server(listener, key)
    conn = _wire_client(address, key)
    conn.send_bytes(b"hello")
    assert conn.recv_bytes() == b"echo:hello"
    conn.close()
    server.join(timeout=5)
    listener.close()
    assert hold["conn"] is not None


def test_wire_rejects_wrong_authkey():
    address = _wire_address()
    listener = _wire_listener(address)
    hold, server = _start_server(listener, b"K" * 32)
    with pytest.raises(tp.AuthenticationError):
        conn = _wire_client(address, b"WRONG" * 7)
        conn.recv_bytes()
    server.join(timeout=5)
    listener.close()
    assert hold["conn"] is None  # the acceptor rejected it and kept its loop alive


def test_wire_stalled_handshake_cannot_wedge_the_acceptor():
    """A client that connects and never speaks the challenge (crashed client, pipe
    scanner) must be dropped within the deadline — and a well-behaved client must
    succeed immediately afterwards. This is the daemon anti-wedge regression test."""
    address, key = _wire_address(), b"K" * 32
    listener = _wire_listener(address)

    hold, server = _start_server(listener, key, timeout=0.5)
    # authkey=None skips mpc's client-side handshake: connect, then total silence.
    stalled = mpc.Client(address) if not tp.IS_WINDOWS else mpc.Client(address, family="AF_PIPE")
    server.join(timeout=5)
    assert not server.is_alive(), "acceptor wedged on a silent client"
    assert hold["conn"] is None
    stalled.close()

    # The acceptor survived — the next legitimate client round-trips fine.
    hold2, server2 = _start_server(listener, key)
    conn = _wire_client(address, key)
    conn.send_bytes(b"after-stall")
    assert conn.recv_bytes() == b"echo:after-stall"
    conn.close()
    server2.join(timeout=5)
    listener.close()
    assert hold2["conn"] is not None
