"""
Purpose: Browser daemon client — sends short browser commands over the platform transport and runs the natural-language `do` agent locally so model waits never occupy the daemon.
LLM-Note:
  Dependencies: imports from [socket, os, json, sys, time, shlex, inspect, functools, pathlib, browser_agent.transport | lazy: BrowserAutomation and browser_agent.agent for `do`] | imported by [cli/commands/browser_commands.py] | tested by [tests/e2e/cli/test_browser_daemon.py]
  Data flow: direct verb → _request() → wire-v1 JSON {v,caller,account,tab,line,raw,engine}; an explicit Onion request probes the warm daemon's no-launch engine_status verb before sending any page action; `do` → local Agent + DaemonBrowserProxy → each tool invocation becomes one short _request(raw=True) to the shared daemon
  State/Effects: may spawn the daemon via `python -m connectonion.cli.browser_agent.daemon <sock> [--headless] [--engine=MODE]` detached (transport.spawn_detached: start_new_session POSIX / DETACHED_PROCESS Windows), logging to ~/.co/browser.log | writes to stdout/stderr
  Integration: exposes _caller() -> str, send(line, headless=False, tab=None, engine_mode="auto") -> int | FIRST-RUN AUTO-INSTALL: on the cold-start path (no daemon yet) AND when a warm daemon answers "No browser is installed for this user" (send retries once), a page-driving verb with no system Chrome triggers `python -m patchright install chromium` right in the user's terminal (chromium: per-user dir, never needs admin — the branded chrome channel runs a system installer) (_ensure_browser_ready) — `co browser` just works with zero setup commands; PAGELESS_VERBS (status/engine_status/tab/close/...) never provision
  Performance: direct verbs import only the lightweight transport client, then make one connect + request/response; Agent/Playwright and browser tool schemas load only for `do` or inside the daemon | daemon spawn adds browser launch latency on first call | model thinking happens in the caller process and holds no daemon lane
  Errors: _connect() retries transient refusal/backpressure and never unlinks an endpoint whose recorded owner is alive; only a truly stale POSIX socket is removed | missing endpoint → spawn daemon and wait until ready or timeout | setup RuntimeErrors become one clean stderr line, never a traceback containing HMAC-path locals | daemon death, overload shedding, or disconnect mid-request becomes a clean exit 1
"""

import functools
import inspect
import json
import os
import shlex
import socket
import sys
import time
from pathlib import Path

from . import transport


def default_sock_path() -> str:
    """Resolve the endpoint without importing the browser-owning daemon module."""
    return transport.default_address()


def _owner_pid(sock_path: str) -> int | None:
    """Return the live daemon pid recorded beside the endpoint, if there is one."""
    pid_file = Path(transport.pid_path(sock_path))
    if not pid_file.exists():
        return None
    raw = pid_file.read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        return None
    pid = int(raw)
    return pid if transport.pid_alive(pid) else None


def _owner_alive(sock_path: str) -> bool:
    """Read the daemon pid sidecar without importing Playwright or browser tools."""
    return _owner_pid(sock_path) is not None


def _wait_for_pid_exit(pid: int, timeout: float = 15.0) -> bool:
    """Wait for one exact daemon process, never a replacement using its endpoint."""
    deadline = time.monotonic() + timeout
    while transport.pid_alive(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def _connect(sock_path: str):
    """Connect to the daemon. Returns a live connection, or None if the daemon is
    genuinely gone. A daemon at its bounded connection cap can momentarily refuse —
    that is NOT a dead daemon, so retry
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


def _spawn_daemon(sock_path: str, headless: bool, engine_mode: str = "auto"):
    """Launch the daemon detached and wait until its socket accepts connections."""
    log_path = Path.home() / ".co" / "browser.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "connectonion.cli.browser_agent.daemon", sock_path]
    if headless:
        cmd.append("--headless")
    cmd.append(f"--engine={engine_mode}")
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
        # bounded client capacity is full). "Did not start" would lie.
        raise RuntimeError("browser daemon is at connection capacity — try again")
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
        # Page-only commands remain usable; `do` refuses before starting its model.
        return ""
    return str((data or {}).get("address") or "")


# Verbs that never launch Chrome: no point provisioning a browser for them.
PAGELESS_VERBS = {
    "status", "engine_status", "tab", "help", "use", "switch", "close", "closetab",
}


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


def _request(line: str, headless: bool = False, tab: str = None,
             raw_result: bool = False, _provisioned: bool = False,
             engine_mode: str = "auto", _protocol_checked: bool = False) -> tuple:
    """Send one short daemon request and return ``(code, payload)``.

    ``raw_result`` is for the client-side agent: image data must reach its vision
    formatter, while an interactive shell should still receive a saved-file line.
    The account address is public; the API key never crosses this transport.
    """
    account = _caller_account()
    request = json.dumps({
        "v": 1,
        "caller": _caller(),
        "account": account,
        "tab": tab,
        "line": line,
        "raw": raw_result,
        "engine": engine_mode,
    })
    sock_path = default_sock_path()
    owner_pid = None
    try:
        conn = _connect(sock_path)
        if (conn is not None and engine_mode == "onion"
                and not _protocol_checked and line != "engine_status"):
            # A pre-1.8 daemon ignores unknown envelope fields. Sending an
            # explicit Onion request straight to it could therefore drive its
            # old system-Chrome context before the client notices. Probe the
            # new no-launch status verb first and refuse old daemons before the
            # requested command has any browser effect. Auto/system preserve
            # wire-v1 compatibility: an old daemon's system browser is a safe
            # realization of both modes and does not risk an unintended charge.
            conn.close()
            probe_code, probe_payload = _request(
                "engine_status",
                headless=headless,
                engine_mode=engine_mode,
                _protocol_checked=True,
            )
            if probe_code:
                return 1, (
                    "the running browser daemon predates 1.8 engine pinning. "
                    "Restart it before using this client: "
                    "pkill -f 'connectonion.cli.browser_agent[.]daemon'"
                )
            conn = _connect(sock_path)
            if conn is None:
                return _request(
                    line,
                    headless=headless,
                    tab=tab,
                    raw_result=raw_result,
                    _provisioned=_provisioned,
                    engine_mode=engine_mode,
                    _protocol_checked=True,
                )
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
                # bounded client capacity can refuse connections too.
                # Saying "not running — the next page command starts one" then
                # sends the reader in the wrong direction, and every command they
                # try answers "busy". _owner_alive reads the pidfile and asks
                # whether that pid lives — no spawn, no log, so the #356
                # constraint above still holds.
                if _owner_alive(sock_path):
                    return 0, "Browser daemon: running, busy at connection capacity — try again shortly"
                return 0, "Browser daemon: not running — the next page command starts one"
            if engine_mode != "onion":
                _ensure_browser_ready(line)  # system or auto fallback needs this
            conn = _spawn_daemon(sock_path, headless, engine_mode)
        # A successful whole-browser close is a lifecycle barrier on Windows.
        # Record the exact process serving this connection so a concurrently
        # started replacement is never mistaken for the daemon being closed.
        if transport.IS_WINDOWS and tab is None and line.split() == ["close"]:
            owner_pid = _owner_pid(sock_path)
            # Embedded users and socket round-trip tests may run the daemon in
            # another thread of this process. That process cannot exit while the
            # caller is waiting inside it; production's detached daemon always
            # has a different pid.
            if owner_pid == os.getpid():
                owner_pid = None
    except RuntimeError as exc:
        # Setup failures (authkey mismatch/corruption, daemon didn't start) must exit
        # with a clean one-line error, NEVER a traceback: typer's pretty exceptions
        # print frame locals, and connect-path frames hold the HMAC secret.
        return 1, str(exc)

    if transport.IS_WINDOWS:
        # Named-pipe wire: one framed message each way (no half-close needed).
        try:
            conn.send_bytes(request.encode())
            reply = conn.recv_bytes()
        except (EOFError, OSError):
            # The daemon died mid-request (browser crash mid-command). Mirror the POSIX
            # empty-reply degradation: a clean error and exit 1, never a traceback.
            conn.close()
            return 1, "browser daemon closed the connection mid-request — try again"
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
        if owner_pid is not None and not _wait_for_pid_exit(owner_pid):
            return 1, (
                "Browser closed, but its daemon did not stop within 15 seconds — "
                "try again"
            )
        return 0, payload
    # A warm daemon reached the launcher and found no browser. The cold-start
    # provisioning above was skipped because the connect succeeded, so without
    # this every page command on this box fails identically forever. The daemon's
    # verdict is the signal: whether patchright's downloaded chromium exists is
    # not something to guess at from a version-numbered cache path.
    if "No browser is installed for this user" in payload and not _provisioned:
        if _ensure_browser_ready(line):
            return _request(
                line, headless=headless, tab=tab, raw_result=raw_result,
                _provisioned=True, engine_mode=engine_mode,
            )

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
    # "ERR" = generic failure (1); "ERR <n>" carries a distinct code so callers can
    # branch without parsing prose (2 = usage, 3 = unknown tab, 4 = tab busy).
    parts = header.split()
    code = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1
    return code, payload


def _tool_line(name: str, args: tuple, kwargs: dict) -> str:
    """Serialize one proxy method call with the daemon's shell grammar."""
    tokens = [name]
    tokens.extend(str(value) for value in args if value is not None)
    for key, value in kwargs.items():
        if value is None:
            continue
        flag = "--" + key.replace("_", "-")
        if isinstance(value, bool):
            tokens.append(f"{flag}={'true' if value else 'false'}")
        else:
            tokens.append(f"{flag}={value}")
    return shlex.join(tokens)


class DaemonBrowserProxy:
    """BrowserAutomation-shaped tools whose calls cross the daemon one at a time."""

    def __init__(self, headless: bool = False, tab: str = None, engine_mode: str = "auto"):
        self._headless = headless
        self._tab = tab
        self._engine_mode = engine_mode

    def _call(self, name: str, args: tuple, kwargs: dict):
        request_kwargs = {
            "headless": self._headless,
            "tab": self._tab,
            "raw_result": True,
        }
        if self._engine_mode != "auto":
            request_kwargs["engine_mode"] = self._engine_mode
        code, payload = _request(_tool_line(name, args, kwargs), **request_kwargs)
        if code:
            raise RuntimeError(payload)
        return payload


def _proxy_method(name, method):
    @functools.wraps(method)
    def call(self, *args, **kwargs):
        return self._call(name, args, kwargs)

    return call


_proxy_methods_installed = False


def _install_proxy_methods() -> None:
    """Mirror BrowserAutomation's tool schema only for the natural-language `do` path.

    Direct verbs already know their wire command and must not spend seconds importing
    Playwright, Agent, TUI, and provider integrations before they can connect to the
    persistent daemon. The daemon loads BrowserAutomation in its own long-lived process.
    """
    global _proxy_methods_installed
    if _proxy_methods_installed:
        return
    from connectonion.useful_tools.browser_tools import BrowserAutomation

    # Keep the agent's tool schema identical without duplicating dozens of signatures.
    # functools.wraps preserves each original signature and docstring for the tool
    # factory; every implementation delegates to _call().
    for name, method in inspect.getmembers(BrowserAutomation, predicate=inspect.isfunction):
        if not name.startswith("_"):
            setattr(DaemonBrowserProxy, name, _proxy_method(name, method))
    _proxy_methods_installed = True


def _run_do(line: str, headless: bool, tab: str, engine_mode: str = "auto") -> tuple:
    """Run the model loop here; only its browser tool calls enter the daemon."""
    account = _caller_account()
    if not account:
        return 5, (
            "cannot determine which OpenOnion account should pay for `do`; "
            "run `co status` or `co auth` first"
        )
    tokens = shlex.split(line)
    command = " ".join(tokens[1:])
    if not command:
        return 2, 'usage: co browser do "<instruction>"'

    from .agent import build_browser_agent, resolve_api_key

    _install_proxy_methods()

    api_key = resolve_api_key()
    if not api_key:
        return 5, "Browser agent requires authentication. Run: co auth"
    try:
        result = build_browser_agent(
            DaemonBrowserProxy(headless=headless, tab=tab, engine_mode=engine_mode), api_key
        ).input(command)
    except Exception as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return 0, "" if result is None else str(result)


def send(line: str, headless: bool = False, tab: str = None,
         _provisioned: bool = False, engine_mode: str = "auto") -> int:
    """Run a CLI command, print its result, and return its process exit code."""
    try:
        verb = shlex.split(line)[:1]
    except ValueError as exc:
        print(f"unparseable request: {exc}", file=sys.stderr)
        return 2

    if verb == ["do"]:
        code, payload = (
            _run_do(line, headless, tab)
            if engine_mode == "auto"
            else _run_do(line, headless, tab, engine_mode)
        )
    else:
        request_kwargs = {
            "headless": headless,
            "tab": tab,
            "_provisioned": _provisioned,
        }
        if engine_mode != "auto":
            request_kwargs["engine_mode"] = engine_mode
        code, payload = _request(line, **request_kwargs)
    if payload:
        print(payload, file=sys.stderr if code else sys.stdout)
    return code
