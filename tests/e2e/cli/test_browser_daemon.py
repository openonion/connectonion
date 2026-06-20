"""
LLM-Note: Browser daemon dispatch + socket round-trip tests

What it tests:
- Pure helpers: _coerce, _split_tokens, _is_verb, _stringify
- dispatch(): verb matches a BrowserAutomation method → executes it; `do` → NL agent; unknown → error
- Full socket round-trip: client.send() ↔ a running BrowserDaemon over a real AF_UNIX socket

Components under test:
- connectonion.cli.browser_agent.daemon (BrowserDaemon, helpers)
- connectonion.cli.browser_agent.client (send)

Strategy: a StubBrowser stands in for BrowserAutomation so no real Chrome/Playwright
or network is needed. The daemon's lazy BrowserAutomation is swapped for the stub.
"""

import os
import threading
import time

import pytest

from connectonion.cli.browser_agent import daemon as d
from connectonion.cli.browser_agent import client as c


@pytest.fixture
def short_sock():
    """A short AF_UNIX path (macOS caps socket paths at 104 chars; tmp_path is too long)."""
    path = f"/tmp/co_test_{os.getpid()}_{time.time_ns()}.sock"
    yield path
    if os.path.exists(path):
        os.unlink(path)


class StubBrowser:
    """Stand-in for BrowserAutomation: same method shapes, no real browser."""

    def __init__(self):
        self.calls = []

    def go_to(self, url: str) -> str:
        self.calls.append(("go_to", url))
        return f"Navigated to {url}"

    def take_screenshot(self, path: str = None, full_page: bool = False) -> str:
        return f"shot path={path} full={full_page}"

    def get_links_from_page(self, domain_filter: str = "") -> list:
        return ["https://a.com", "https://b.com"]

    def _browser_is_usable(self) -> bool:
        return True

    def close(self) -> str:
        return "Browser closed"


def _wait_until_listening(sock_path, timeout=5.0):
    """Wait until the daemon has bound its socket (file appears), without leaking a connection."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(sock_path):
            return
        time.sleep(0.02)
    raise RuntimeError("daemon did not bind socket in time")


def make_daemon(sock_path, stub=None):
    """Build a daemon whose lazy BrowserAutomation is replaced by a stub."""
    daemon = d.BrowserDaemon(sock_path, headless=True)
    daemon.browser = stub or StubBrowser()
    return daemon


# ---- pure helpers --------------------------------------------------------

def test_coerce_types():
    assert d._coerce("true", bool) is True
    assert d._coerce("0", bool) is False
    assert d._coerce("7", int) == 7
    assert d._coerce("1.5", float) == 1.5
    assert d._coerce("x.com", str) == "x.com"


def test_split_tokens():
    pos, kw = d._split_tokens(["x.com", "--full-page", "--index=2"])
    assert pos == ["x.com"]
    assert kw == {"full_page": True, "index": "2"}


def test_stringify_list_is_one_per_line():
    assert d._stringify(["a", "b"]) == "a\nb"
    assert d._stringify(None) == ""
    assert d._stringify("hi") == "hi"


# ---- dispatch (the core: match function name → execute) ------------------

def test_dispatch_matched_verb_executes(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, payload = daemon.dispatch("go_to x.com")
    assert ok is True
    assert payload == "Navigated to x.com"
    assert daemon.browser.calls == [("go_to", "x.com")]


def test_dispatch_coerces_bool_flag(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, payload = daemon.dispatch("take_screenshot --full-page")
    assert ok is True
    assert payload == "shot path=None full=True"


def test_dispatch_list_result(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, payload = daemon.dispatch("get_links_from_page")
    assert ok is True
    assert payload == "https://a.com\nhttps://b.com"


def test_dispatch_unknown_command(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, payload = daemon.dispatch("frobnicate now")
    assert ok is False
    assert payload.startswith("unknown command: frobnicate")
    # agent-friendly next steps
    assert "co browser help" in payload
    assert 'do "<instruction>"' in payload


def test_dispatch_wrong_args_shows_signature(tmp_path):
    """A TypeError from wrong args must include the function's usage so an agent can fix it."""
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, payload = daemon.dispatch("go_to")  # missing required `url`
    assert ok is False
    assert "TypeError" in payload
    assert "usage: go_to(url)" in payload


def test_dispatch_empty(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, payload = daemon.dispatch("")
    assert ok is False


def test_dispatch_do_routes_to_nl(tmp_path, monkeypatch):
    """`do` must go to the NL agent, not function dispatch."""
    captured = {}

    class FakeAgent:
        def input(self, command):
            captured["command"] = command
            return "agent says hi"

    monkeypatch.setattr(d, "resolve_api_key", lambda: "key")
    monkeypatch.setattr(d, "build_browser_agent", lambda browser, key: FakeAgent())

    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, payload = daemon.dispatch('do find the cheapest flight')
    assert ok is True
    assert payload == "agent says hi"
    assert captured["command"] == "find the cheapest flight"


# ---- self-describing help (no browser launched) -------------------------

def test_signature_str():
    assert d.signature_str(StubBrowser.go_to) == "(url)"
    assert d.signature_str(StubBrowser.take_screenshot) == "(path=None, full_page=False)"


def test_list_functions_describes_real_methods():
    """`co browser help` introspects BrowserAutomation: name + signature + summary."""
    text = d.list_functions()
    assert "go_to(url)" in text
    assert "— Navigate to a URL." in text
    # private methods are hidden
    assert "_browser_is_usable" not in text


def test_handle_browser_help_needs_no_browser(capsys):
    """`co browser help` prints functions and exits 0 without spawning a daemon."""
    from connectonion.cli.commands.browser_commands import handle_browser
    code = handle_browser(["help"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Functions:" in out
    assert "go_to(url)" in out


def test_handle_browser_no_args_is_usage_error(capsys):
    from connectonion.cli.commands.browser_commands import handle_browser
    code = handle_browser([])
    err = capsys.readouterr().err
    assert code == 1
    assert "co browser <function>" in err


# ---- full socket round-trip: client.send() ↔ daemon ----------------------

def test_socket_round_trip(short_sock, monkeypatch, capsys):
    sock_path = short_sock
    monkeypatch.setenv("CO_BROWSER_SOCK", sock_path)

    daemon = make_daemon(sock_path)
    t = threading.Thread(target=daemon.serve, daemon=True)
    t.start()

    _wait_until_listening(sock_path)

    code = c.send("go_to example.com", headless=True)
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == "Navigated to example.com"
    assert daemon.browser.calls == [("go_to", "example.com")]


def test_socket_round_trip_error_to_stderr(short_sock, monkeypatch, capsys):
    sock_path = short_sock
    monkeypatch.setenv("CO_BROWSER_SOCK", sock_path)

    daemon = make_daemon(sock_path)
    threading.Thread(target=daemon.serve, daemon=True).start()
    _wait_until_listening(sock_path)

    code = c.send("frobnicate", headless=True)
    err = capsys.readouterr().err.strip()
    assert code == 1
    assert "unknown command: frobnicate" in err
