"""
Purpose: Thin client for the browser daemon — wraps one command as a JSON envelope, sends it over the Unix socket, and maps the reply to stdout/stderr/exit code.
LLM-Note:
  Dependencies: imports from [socket, os, json, sys, time, subprocess, pathlib, browser_agent.daemon.default_sock_path] | imported by [cli/commands/browser_commands.py] | tested by [tests/e2e/cli/test_browser_daemon.py]
  Data flow: send(line, headless, tab) → _caller() derives identity (CO_WHO, else claude-<CLAUDE_JOB_DIR>, else "") → build wire-v1 envelope json{v:1, caller, tab, line} (structured caller/tab means any character in a name is safe — nothing is spliced into the shlex-parsed command line) → _connect(default_sock_path()) or _spawn_daemon() → send, half-close, read reply to EOF → header "OK" prints payload to stdout & returns 0 | header "ERR"/"ERR <n>" prints payload to stderr & returns the int (1 default, else 2/3/4) → a pre-upgrade daemon's "unknown command: {…" reply is rewritten to a restart hint
  State/Effects: may spawn the daemon via `python -m connectonion.cli.browser_agent.daemon <sock> [--headless]` with start_new_session=True, logging to ~/.co/browser.log | writes to stdout/stderr
  Integration: exposes _caller() -> str, send(line, headless=False, tab=None) -> int
  Performance: one connect + request/response | daemon spawn adds browser launch latency on first call
  Errors: _connect() retries ~2s on a transient ECONNREFUSED from a busy single-threaded daemon (does NOT unlink a live-but-busy socket); only a truly stale socket (other OSError) is unlinked | missing socket → spawn daemon and wait until ready or timeout
"""

import os
import json
import sys
import time
import socket
import subprocess
from pathlib import Path

from .daemon import default_sock_path, _owner_alive


def _connect(sock_path: str):
    """Connect to the daemon socket. Returns a live connection, or None if the daemon
    is genuinely gone. A busy single-threaded daemon (mid `do` task) can momentarily
    refuse with ECONNREFUSED while its accept backlog is full — that is NOT a dead
    daemon, so retry while its recorded owner is alive; a dead owner's stale socket
    fails fast (the spawned daemon's _bind replaces it)."""
    if not os.path.exists(sock_path):
        return None
    for attempt in range(20):  # ~2s of ECONNREFUSED tolerance for a busy daemon
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            conn.connect(sock_path)
            return conn
        except ConnectionRefusedError:
            conn.close()
            if not _owner_alive(sock_path):
                return None  # stale socket, nobody home — don't burn the retry window
            time.sleep(0.1)
        except OSError:
            conn.close()
            if os.path.exists(sock_path):
                os.unlink(sock_path)  # stale socket: nothing is listening on it
            return None
    return None  # still refusing after the window — let the caller spawn a fresh daemon


def _spawn_daemon(sock_path: str, headless: bool):
    """Launch the daemon detached and wait until its socket accepts connections."""
    log_path = Path.home() / ".co" / "browser.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "a")
    cmd = [sys.executable, "-m", "connectonion.cli.browser_agent.daemon", sock_path]
    if headless:
        cmd.append("--headless")
    subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)

    # Wall-clock deadline, not an attempt count: against a busy daemon each _connect
    # can itself take ~2s of refused-retries, so counting attempts multiplies silently.
    deadline = time.time() + 15
    while time.time() < deadline:
        conn = _connect(sock_path)
        if conn:
            return conn
        time.sleep(0.1)
    if _owner_alive(sock_path):
        # A daemon IS running — it just can't take our connection right now (its
        # backlog is full behind a long-running command). "Did not start" would lie.
        raise RuntimeError("browser daemon is busy (a long command is holding it) — try again")
    raise RuntimeError(f"browser daemon did not start (see {log_path})")


def _caller() -> str:
    """Stable-per-agent identity so the daemon can say WHO occupies a tab.

    CO_WHO wins (set it to name yourself); a Claude Code session is identified by
    its job dir; otherwise anonymous — anonymous callers get no contention guard,
    so concurrent agents should set CO_WHO or use named tabs.
    """
    who = os.environ.get("CO_WHO")
    if not who:
        job = os.environ.get("CLAUDE_JOB_DIR")
        who = f"claude-{Path(job).name}" if job else ""
    # Only trim surrounding whitespace — the JSON envelope carries any inner character
    # safely, so distinct names like "agent 1"/"agent-1" must stay distinct.
    return who.strip()


def send(line: str, headless: bool = False, tab: str = None) -> int:
    """Send one request; print the reply; return the process exit code.

    Wire v1 is a JSON envelope {caller, tab, line} — caller identity and tab
    targeting are structured fields, so any character in a name is safe (nothing
    is spliced into the shlex-parsed command line)."""
    request = json.dumps({"v": 1, "caller": _caller(), "tab": tab, "line": line})
    sock_path = default_sock_path()
    conn = _connect(sock_path) or _spawn_daemon(sock_path, headless)

    conn.sendall(request.encode())
    conn.shutdown(socket.SHUT_WR)

    chunks = []
    while True:
        chunk = conn.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
    conn.close()

    header, _, payload = b"".join(chunks).decode().partition("\n")
    if header == "OK":
        if payload:
            print(payload)
        return 0
    # An old (pre-upgrade) daemon shlex-splits the JSON envelope and rejects its first
    # token — which, after shlex strips the quotes, is 'unknown command: {v:1,...'.
    if payload.startswith("unknown command: {"):
        payload = (
            "an old browser daemon (pre-upgrade) is still running and does not speak "
            "this client's protocol.\nrestart it:  pkill -f connectonion.cli.browser_agent.daemon"
        )
    print(payload, file=sys.stderr)
    # "ERR" = generic failure (1); "ERR <n>" carries a distinct code so callers can
    # branch without parsing prose (2 = usage, 3 = unknown tab, 4 = tab busy).
    parts = header.split()
    return int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1
