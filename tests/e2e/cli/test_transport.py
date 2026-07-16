"""
LLM-Note: Cross-platform transport primitives for the browser daemon/client.

What it tests (runs on BOTH POSIX and Windows CI):
- default_address honors $CO_BROWSER_SOCK; pid_path/lock_path derive real filesystem sidecars
- pid_alive: True for this process, False for a dead/invalid pid
- load_or_create_authkey: stable across calls, converges on one key
- acquire_singleton_lock: exclusive + non-blocking, released on close
- spawn_detached: launches a detached child that actually runs
- The named-pipe / Unix-socket wire with an HMAC authkey: a correct key round-trips,
  a wrong key raises AuthenticationError (this is the Windows-native path in CI)

Component under test: connectonion.cli.browser_agent.transport
"""

import os
import sys
import time
import threading
import subprocess
from pathlib import Path

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


def test_pid_alive():
    assert tp.pid_alive(os.getpid()) is True
    assert tp.pid_alive(0) is False
    assert tp.pid_alive(-1) is False
    # a pid that is almost certainly not running
    assert tp.pid_alive(4000000000) is False


def test_authkey_is_stable_and_created(monkeypatch, tmp_path):
    # isolate the sidecar dir away from the real ~/.co / %LOCALAPPDATA%
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    first = tp.load_or_create_authkey()
    second = tp.load_or_create_authkey()
    assert isinstance(first, bytes) and len(first) >= 16
    assert first == second  # a second call returns the same persisted key


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
    log = open(tmp_path / "out.log", "a")
    code = f"open(r'{marker}', 'w').write('ok')"
    proc = tp.spawn_detached([sys.executable, "-c", code], log)
    deadline = time.time() + 10
    while time.time() < deadline and not marker.exists():
        time.sleep(0.05)
    log.close()
    assert marker.exists(), "detached child did not run"


# ---- the authenticated wire (Windows named pipe / POSIX unix socket) --------

def _listen_once(address, authkey, hold):
    """Serve exactly one request on the platform-native authenticated transport."""
    if tp.IS_WINDOWS:
        listener = tp.win_listener(address, authkey)
    else:
        import multiprocessing.connection as mpc
        listener = mpc.Listener(address, authkey=authkey)
    hold["listener"] = listener
    try:
        conn = listener.accept()  # performs the HMAC handshake
        data = conn.recv_bytes()
        conn.send_bytes(b"echo:" + data)
        conn.close()
    except Exception as exc:  # a failed handshake surfaces here
        hold["server_error"] = type(exc).__name__


def _client_connect(address, authkey):
    if tp.IS_WINDOWS:
        return tp.win_connect(address, authkey)
    import multiprocessing.connection as mpc
    return mpc.Client(address, authkey=authkey)


def _wire_address():
    if tp.IS_WINDOWS:
        return rf"\\.\pipe\co_wire_{os.getpid()}_{time.time_ns()}"
    return f"/tmp/co_wire_{os.getpid()}_{time.time_ns()}.sock"


def test_wire_round_trip_with_correct_authkey():
    address, key = _wire_address(), b"K" * 32
    hold = {}
    server = threading.Thread(target=_listen_once, args=(address, key, hold), daemon=True)
    server.start()
    _wait_for(lambda: "listener" in hold)
    conn = _client_connect(address, key)
    conn.send_bytes(b"hello")
    assert conn.recv_bytes() == b"echo:hello"
    conn.close()
    server.join(timeout=5)
    hold["listener"].close()
    assert "server_error" not in hold


def test_wire_rejects_wrong_authkey():
    address = _wire_address()
    hold = {}
    server = threading.Thread(target=_listen_once, args=(address, b"K" * 32, hold), daemon=True)
    server.start()
    _wait_for(lambda: "listener" in hold)
    with pytest.raises(tp.AuthenticationError):
        conn = _client_connect(address, b"WRONG" * 7)
        conn.recv_bytes()
    server.join(timeout=5)
    hold["listener"].close()


def _wait_for(pred, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return
        time.sleep(0.02)
    raise RuntimeError("condition not met in time")
