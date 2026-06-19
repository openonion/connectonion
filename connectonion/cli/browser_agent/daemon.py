"""
Purpose: Persistent browser daemon — owns one BrowserAutomation and dispatches CLI verbs to it over a Unix socket.
LLM-Note:
  Dependencies: imports from [socket, os, sys, shlex, inspect, signal, atexit, pathlib, useful_tools.browser_tools.BrowserAutomation, browser_agent.agent (resolve_api_key, build_browser_agent)] | imported by [browser_agent/client.py (spawns via python -m), cli/commands/browser_commands.py (indirectly)] | tested by [tests/e2e/cli/test_cli_browser.py]
  Data flow: client sends one request line over AF_UNIX socket → shlex.split → first token compared against BrowserAutomation method names → match: coerce args via signature type hints + getattr(browser, verb)(*args) → no match: whole line handed to NL Agent on the same live browser → response "OK\n<payload>" or "ERR\n<message>" written back, connection closed
  State/Effects: single-threaded serial server (sync Playwright requires one thread) | owns one BrowserAutomation for daemon lifetime | binds AF_UNIX socket at default_sock_path() | daemon exits once an opened browser becomes unusable (close / crash / window shut) | unlinks socket on exit
  Integration: exposes default_sock_path(), BrowserDaemon, main() | launched detached via `python -m connectonion.cli.browser_agent.daemon <sock_path> [--headless]`
  Performance: one request at a time | browser launch overhead on first verb (1-3s) | NL verb builds a fresh Agent per call
  Errors: method exceptions are caught at the dispatch boundary and returned as "ERR\n<message>" (the protocol's purpose) | bind race with a second daemon → loser exits
"""

import os
import sys
import socket
import shlex
import inspect
import signal
import atexit
import tempfile
import threading
from pathlib import Path

from connectonion.useful_tools.browser_tools import BrowserAutomation
from .agent import resolve_api_key, build_browser_agent


def default_sock_path() -> str:
    """Runtime socket path: $CO_BROWSER_SOCK, else $XDG_RUNTIME_DIR/co, else $TMPDIR/co."""
    override = os.environ.get("CO_BROWSER_SOCK")
    if override:
        return override
    runtime = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    base = Path(runtime) / "co"
    base.mkdir(parents=True, exist_ok=True)
    os.chmod(base, 0o700)
    return str(base / "browser.sock")


def _coerce(value: str, annotation):
    """Coerce a shell string token to the parameter's annotated type."""
    if annotation is bool:
        return value.lower() in ("1", "true", "yes", "on")
    if annotation is int:
        return int(value)
    if annotation is float:
        return float(value)
    return value


def _split_tokens(tokens):
    """Split shell tokens into positional args and --key[=value] kwargs."""
    positional, kwargs = [], {}
    for tok in tokens:
        if tok.startswith("--"):
            key, eq, val = tok[2:].partition("=")
            kwargs[key.replace("-", "_")] = val if eq else True
        else:
            positional.append(tok)
    return positional, kwargs


def _is_verb(browser, name: str) -> bool:
    """True when `name` is a public, callable method on the browser instance."""
    if name.startswith("_"):
        return False
    attr = getattr(browser, name, None)
    return callable(attr)


def signature_str(method) -> str:
    """Render a method's call signature without `self`, e.g. '(url)' or '(path=None, full_page=False)'."""
    parts = []
    for p in inspect.signature(method).parameters.values():
        if p.name == "self":
            continue
        parts.append(p.name if p.default is inspect.Parameter.empty else f"{p.name}={p.default!r}")
    return "(" + ", ".join(parts) + ")"


def list_functions() -> str:
    """One line per public browser function: `name(args) — first docstring line`.

    Introspects the BrowserAutomation class (no browser launched) so the CLI is
    self-describing — an agent can run `co browser help` to discover what it can call.
    """
    lines = []
    for name, method in inspect.getmembers(BrowserAutomation, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        doc = (inspect.getdoc(method) or "").splitlines()
        summary = doc[0] if doc else ""
        lines.append(f"  {name}{signature_str(method)}" + (f" — {summary}" if summary else ""))
    return "\n".join(lines)


class BrowserDaemon:
    """Single-threaded server owning one BrowserAutomation, dispatching verbs to it."""

    def __init__(self, sock_path: str, headless: bool = False):
        self.sock_path = sock_path
        self.browser = BrowserAutomation(headless=headless)
        self._srv = None
        self._had_browser = False

    def dispatch(self, line: str) -> tuple:
        """Run one request. Returns (ok: bool, payload: str)."""
        tokens = shlex.split(line)
        if not tokens:
            return False, "empty request"

        verb = tokens[0]
        if verb == "do":  # explicit natural-language agent
            command = line.split(None, 1)[1] if len(tokens) > 1 else ""
            return self._run_nl(command)
        if _is_verb(self.browser, verb):
            return self._call_verb(verb, tokens[1:])
        return False, (
            f"unknown command: {verb}\n"
            f"Run 'co browser help' to list functions, or "
            f"'co browser do \"<instruction>\"' for natural language."
        )

    def _call_verb(self, verb: str, raw_args) -> tuple:
        """Match the verb to a browser method and execute it with coerced args."""
        method = getattr(self.browser, verb)
        positional, kwargs = _split_tokens(raw_args)

        params = list(inspect.signature(method).parameters.values())
        args = [_coerce(v, params[i].annotation if i < len(params) else str)
                for i, v in enumerate(positional)]
        kw = {}
        param_by_name = {p.name: p for p in params}
        for k, v in kwargs.items():
            ann = param_by_name[k].annotation if k in param_by_name else str
            kw[k] = v if v is True else _coerce(v, ann)

        try:
            result = method(*args, **kw)
        except Exception as exc:  # dispatch boundary: report to client as ERR
            # On wrong arguments, show the expected signature so an agent can self-correct.
            hint = f"\nusage: {verb}{signature_str(method)}" if isinstance(exc, TypeError) else ""
            return False, f"{type(exc).__name__}: {exc}{hint}"
        return True, _stringify(result)

    def _run_nl(self, command: str) -> tuple:
        """Hand the command to the NL agent driving the same live browser."""
        api_key = resolve_api_key()
        if not api_key:
            return False, "Browser agent requires authentication. Run: co auth"
        try:
            result = build_browser_agent(self.browser, api_key).input(command)
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
        return True, _stringify(result)

    def serve(self):
        self._bind()
        atexit.register(self._cleanup)
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

        while True:
            conn, _ = self._srv.accept()
            request = _recv_all(conn).decode().strip()
            ok, payload = self.dispatch(request)
            conn.sendall((("OK" if ok else "ERR") + "\n" + payload).encode())
            conn.close()

            self._had_browser = self._had_browser or self.browser._browser_is_usable()
            if self._had_browser and not self.browser._browser_is_usable():
                break  # browser closed / crashed → daemon's job is done

    def _bind(self):
        """Bind the socket, yielding to any daemon that already owns it."""
        if os.path.exists(self.sock_path):
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.connect(self.sock_path)
                probe.close()
                sys.exit(0)  # another daemon already serving
            except OSError:
                os.unlink(self.sock_path)  # stale socket
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(self.sock_path)
        self._srv.listen(8)

    def _cleanup(self):
        self.browser.close()
        if self._srv:
            self._srv.close()
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)


def _recv_all(conn) -> bytes:
    """Read until the client half-closes (EOF)."""
    chunks = []
    while True:
        chunk = conn.recv(65536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _stringify(result) -> str:
    """Methods return str or list[str]; lists print one item per line for piping."""
    if isinstance(result, list):
        return "\n".join(str(x) for x in result)
    return "" if result is None else str(result)


def main():
    sock_path = sys.argv[1] if len(sys.argv) > 1 else default_sock_path()
    headless = "--headless" in sys.argv[2:]
    BrowserDaemon(sock_path, headless=headless).serve()


if __name__ == "__main__":
    main()
