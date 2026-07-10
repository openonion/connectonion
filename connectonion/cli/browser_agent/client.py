"""
Purpose: Thin client for the browser daemon — sends one request line over the Unix socket and maps the reply to stdout/stderr/exit code.
LLM-Note:
  Dependencies: imports from [socket, os, sys, time, subprocess, pathlib, browser_agent.daemon.default_sock_path] | imported by [cli/commands/browser_commands.py] | tested by [tests/e2e/cli/test_cli_browser.py]
  Data flow: send(line, headless) → connect to default_sock_path() (spawning the daemon detached if absent / unlinking a stale socket) → send line, half-close → read reply to EOF → first line "OK"/"ERR" sets exit code, rest is payload → OK prints to stdout, ERR prints to stderr → returns exit code int
  State/Effects: may spawn the daemon via `python -m connectonion.cli.browser_agent.daemon <sock> [--headless]` with start_new_session=True, logging to ~/.co/browser.log | writes to stdout/stderr
  Integration: exposes send(line, headless=False) -> int
  Performance: one connect + request/response | daemon spawn adds browser launch latency on first call
  Errors: connection refused / missing socket → spawn daemon and retry until ready or timeout
"""

import os
import sys
import time
import socket
import subprocess
from pathlib import Path

from .daemon import default_sock_path


def _connect(sock_path: str):
    """Connect to the daemon socket, or None if nothing is listening."""
    if not os.path.exists(sock_path):
        return None
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        conn.connect(sock_path)
        return conn
    except OSError:
        conn.close()
        os.unlink(sock_path)  # stale socket
        return None


def _spawn_daemon(sock_path: str, headless: bool):
    """Launch the daemon detached and wait until its socket accepts connections."""
    log_path = Path.home() / ".co" / "browser.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "a")
    cmd = [sys.executable, "-m", "connectonion.cli.browser_agent.daemon", sock_path]
    if headless:
        cmd.append("--headless")
    subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)

    for _ in range(100):  # up to ~10s for the browser to launch
        conn = _connect(sock_path)
        if conn:
            return conn
        time.sleep(0.1)
    raise RuntimeError(f"browser daemon did not start (see {log_path})")


def send(line: str, headless: bool = False) -> int:
    """Send one request line; print the reply; return the process exit code."""
    # CO_BROWSER_TAB names this client's own tab: one task = one tab. Concurrent
    # runs (main session, subagents) each export a different name and coexist
    # instead of stomping one shared page. Close it with `co browser closetab`.
    tab = os.environ.get("CO_BROWSER_TAB")
    if tab and not line.startswith("@"):
        line = f"@{tab} {line}"
    sock_path = default_sock_path()
    conn = _connect(sock_path) or _spawn_daemon(sock_path, headless)

    conn.sendall(line.encode())
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
    print(payload, file=sys.stderr)
    return 1
