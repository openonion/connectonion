"""
Purpose: Thin client for the browser daemon — wraps one command as a JSON envelope, sends it over the platform transport (POSIX Unix socket / Windows named pipe), and maps the reply to stdout/stderr/exit code.
LLM-Note:
  Dependencies: imports from [socket, os, json, sys, time, pathlib, browser_agent.daemon (default_sock_path, _owner_alive), browser_agent.transport] | imported by [cli/commands/browser_commands.py] | tested by [tests/e2e/cli/test_browser_daemon.py]
  Data flow: send(line, headless, tab) → derive caller label and public billing address → build wire-v1 JSON {v,caller,account,tab,line} (no API key crosses the transport) → connect/spawn daemon → print reply and mirror its exit code
  State/Effects: may spawn the daemon via `python -m connectonion.cli.browser_agent.daemon <sock> [--headless]` detached (transport.spawn_detached: start_new_session POSIX / DETACHED_PROCESS Windows), logging to ~/.co/browser.log | writes to stdout/stderr
  Integration: exposes _caller() -> str, send(line, headless=False, tab=None) -> int | FIRST-RUN AUTO-INSTALL: on the cold-start path (no daemon yet) AND when a warm daemon answers "No browser is installed for this user" (send retries once), a page-driving verb with no system Chrome triggers `python -m patchright install chromium` right in the user's terminal (chromium: per-user dir, never needs admin — the branded chrome channel runs a system installer) (_ensure_browser_ready) — `co browser` just works with zero setup commands; PAGELESS_VERBS (status/tab/close/...) never provision
  Performance: one connect + request/response | daemon spawn adds browser launch latency on first call
  Errors: _connect() retries ~2s on a transient connection refusal from a busy single-threaded daemon (does NOT unlink a live-but-busy socket); only a truly stale POSIX socket is unlinked | missing endpoint → spawn daemon and wait until ready or timeout | ALL setup RuntimeErrors (Windows authkey mismatch/corruption, daemon didn't start) are caught in send() → one clean stderr line + exit 1, NEVER a traceback (typer's pretty exceptions would print frame locals, which hold the HMAC secret on the connect path) | daemon dying mid-request → clean stderr line + exit 1
"""

import os
import json
import sys
import time
import socket
from pathlib import Path

from .daemon import default_sock_path, _owner_alive
from . import transport


def _connect(sock_path: str):
    """Connect to the daemon. Returns a live connection, or None if the daemon is
    genuinely gone. A busy single-threaded daemon (mid `do` task) can momentarily
    refuse while its accept backlog is full — that is NOT a dead daemon, so retry
    while its recorded owner is alive; a dead owner fails fast (the spawned daemon
    replaces it). POSIX uses a raw AF_UNIX socket (unchanged); Windows uses the
    authenticated named-pipe client from `transport`. Raises RuntimeError only for
    an authkey mismatch against a live daemon (send() turns it into a clean line)."""
    if transport.IS_WINDOWS:
        return _connect_windows(sock_path)
    return _connect_posix(sock_path)


def _connect_posix(sock_path: str):
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
            # ConnectionRefused (handled above) is the only error that means
            # "nobody is listening". Any other OSError — EACCES from a process
            # sandbox, EMFILE, ENOBUFS — says nothing about whether the daemon
            # is alive, and unlinking on those took a live, idle daemon
            # permanently offline: it kept accept()ing on an unlinked inode
            # while every later client reported "daemon is busy".
            if not _owner_alive(sock_path) and os.path.exists(sock_path):
                os.unlink(sock_path)
            return None
    return None  # still refusing after the window — let the caller spawn a fresh daemon


def _connect_windows(sock_path: str):
    authkey = transport.load_or_create_authkey()  # one 64-byte read, hoisted off the loop
    # Retry window for a briefly-unavailable pipe. (mpc's Client additionally waits out
    # PIPE_BUSY internally, so a genuinely busy daemon behaves like the POSIX backlog:
    # the client waits rather than erroring.)
    for attempt in range(20):
        try:
            return transport.win_connect(sock_path, authkey)
        except transport.AuthenticationError:
            # A daemon is listening but rejects our key (the authkey file was recreated
            # under a live daemon). Spawning another daemon can't help — it would yield
            # to the live one — so fail fast with the actual fix.
            raise RuntimeError(
                "browser daemon rejected this client's auth key — stop the old daemon "
                "and retry (it will restart with the current key)"
            )
        except FileNotFoundError:
            return None  # no pipe = no daemon (pipes die with their process) — spawn one
        except EOFError:
            return None  # daemon died mid-handshake — treat as gone; caller respawns
        except (ConnectionError, OSError):
            if not _owner_alive(sock_path):
                return None  # nobody home — don't burn the retry window
            time.sleep(0.1)
    return None  # still unavailable after the window — let the caller spawn a fresh daemon


def _spawn_daemon(sock_path: str, headless: bool):
    """Launch the daemon detached and wait until its socket accepts connections."""
    log_path = Path.home() / ".co" / "browser.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "connectonion.cli.browser_agent.daemon", sock_path]
    if headless:
        cmd.append("--headless")
    with open(log_path, "a", encoding="utf-8") as log:  # the child dups the handle; ours closes right away
        transport.spawn_detached(cmd, log)  # POSIX: new session · Windows: DETACHED_PROCESS

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


def _caller_account() -> str:
    """Public address of the account this invocation expects `do` to bill."""
    from connectonion import address

    try:
        data = address.load(Path.cwd() / ".co") or address.load(Path.home() / ".co")
    except Exception:
        # Page-only commands and `status` must remain usable while diagnosing a
        # broken local identity. An empty account keeps compatibility; the
        # daemon still names its payer in status.
        return ""
    return str((data or {}).get("address") or "")


# Verbs that never launch Chrome: no point provisioning a browser for them.
PAGELESS_VERBS = {"status", "tab", "help", "use", "switch", "close", "closetab"}


def _ensure_browser_ready(line: str) -> bool:
    """First-run auto-install: if this command will drive a page and no browser
    exists, install one NOW — the user just runs `co browser ...` and it works.
    Nobody should have to learn about patchright or doctor commands first.

    Returns whether an install was attempted, so a caller that is retrying can
    tell "provisioned, worth another go" from "nothing to provision".

    Called on the cold-start path (no daemon yet), and again if a warm daemon
    answers that no browser is installed — a daemon that outlived the missing
    browser would otherwise never reach this and fail identically forever.
    `patchright install chrome` is idempotent — a re-run when the browser is
    already downloaded returns in about a second without downloading.
    """
    verb = line.split()[0] if line.strip() else ""
    if verb in PAGELESS_VERBS:
        return False
    from connectonion.useful_tools.browser_tools.chrome_finder import find_system_chrome
    if find_system_chrome():
        return False  # a real desktop Chrome is installed — nothing to provision
    import subprocess
    print("First run: setting up a browser for co browser (one-time download)...",
          file=sys.stderr)
    # chromium, NOT the branded chrome channel: `install chrome` runs a system-wide
    # installer on Windows (admin rights — corporate machines fail), while chromium
    # lands in the per-user browsers dir and works for everyone, headless shell included.
    result = subprocess.run([sys.executable, "-m", "patchright", "install", "chromium"])
    if result.returncode != 0:
        # Don't block the command: Chrome may live at a nonstandard path, and the
        # daemon's launch error is actionable if it truly can't start.
        print("Browser setup did not complete — trying to run anyway "
              "(if launch fails: python -m patchright install chromium)", file=sys.stderr)
    return True


def send(line: str, headless: bool = False, tab: str = None,
         _provisioned: bool = False) -> int:
    """Send one request; print the reply; return the process exit code.

    Wire v1 is a JSON envelope {caller, account, tab, line}. `account` is the
    public address only; an API key never crosses the daemon transport."""
    account = _caller_account()
    if line.split()[:1] == ["do"] and not account:
        print(
            "cannot determine which OpenOnion account should pay for `do`; "
            "run `co status` or `co auth` first",
            file=sys.stderr,
        )
        return 5
    request = json.dumps({
        "v": 1,
        "caller": _caller(),
        "account": account,
        "tab": tab,
        "line": line,
    })
    sock_path = default_sock_path()
    try:
        conn = _connect(sock_path)
        if conn is None:
            if line.split()[:1] == ["status"]:
                # Asking whether the browser is running must not start it. With
                # nobody listening the answer is already known, and obtaining it
                # by launching a Chrome — and creating ~/.co/browser.log to do
                # so — is both backwards and the thing that broke in a managed
                # sandbox: $HOME readable, writes only in the workspace, so the
                # open raised PermissionError, which the RuntimeError below does
                # not catch, and the CLI printed a traceback instead of a status
                # (#356).
                #
                # A failed connect is not "nobody listening": a daemon whose
                # backlog is full behind a long command refuses connections too.
                # Saying "not running — the next page command starts one" then
                # sends the reader in the wrong direction, and every command they
                # try answers "busy". _owner_alive reads the pidfile and asks
                # whether that pid lives — no spawn, no log, so the #356
                # constraint above still holds.
                if _owner_alive(sock_path):
                    print("Browser daemon: running, busy with a long command "
                          "— try again shortly")
                else:
                    print("Browser daemon: not running — the next page command starts one")
                return 0
            _ensure_browser_ready(line)  # cold start: provision the browser first
            conn = _spawn_daemon(sock_path, headless)
    except RuntimeError as exc:
        # Setup failures (authkey mismatch/corruption, daemon didn't start) must exit
        # with a clean one-line error, NEVER a traceback: typer's pretty exceptions
        # print frame locals, and connect-path frames hold the HMAC secret.
        print(str(exc), file=sys.stderr)
        return 1

    if transport.IS_WINDOWS:
        # Named-pipe wire: one framed message each way (no half-close needed).
        try:
            conn.send_bytes(request.encode())
            reply = conn.recv_bytes()
        except (EOFError, OSError):
            # The daemon died mid-request (browser crash mid-command). Mirror the POSIX
            # empty-reply degradation: a clean error and exit 1, never a traceback.
            print("browser daemon closed the connection mid-request — try again", file=sys.stderr)
            conn.close()
            return 1
        conn.close()
    else:
        conn.sendall(request.encode())
        conn.shutdown(socket.SHUT_WR)  # half-close signals end-of-request to the daemon
        chunks = []
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        conn.close()
        reply = b"".join(chunks)

    header, _, payload = reply.decode().partition("\n")
    if header == "OK":
        if payload:
            print(payload)
        return 0
    # A warm daemon reached the launcher and found no browser. The cold-start
    # provisioning above was skipped because the connect succeeded, so without
    # this every page command on this box fails identically forever. The daemon's
    # verdict is the signal: whether patchright's downloaded chromium exists is
    # not something to guess at from a version-numbered cache path.
    if "No browser is installed for this user" in payload and not _provisioned:
        if _ensure_browser_ready(line):
            return send(line, headless=headless, tab=tab, _provisioned=True)

    # An old (pre-upgrade) daemon shlex-splits the JSON envelope and rejects its first
    # token — which, after shlex strips the quotes, is 'unknown command: {v:1,...'.
    if payload.startswith("unknown command: {"):
        payload = (
            "an old browser daemon (pre-upgrade) is still running and does not speak "
            "this client's protocol.\n"
            # The bracketed [.] is load-bearing. `pkill -f` matches whole command
            # lines, so the plain pattern matches the shell running it and kills
            # that shell — measured on Linux: anything after it in the same
            # command never runs. An agent reads this line and runs it that way.
            "restart it:  pkill -f 'connectonion.cli.browser_agent[.]daemon'"
        )
    print(payload, file=sys.stderr)
    # "ERR" = generic failure (1); "ERR <n>" carries a distinct code so callers can
    # branch without parsing prose (2 = usage, 3 = unknown tab, 4 = tab busy).
    parts = header.split()
    return int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1
