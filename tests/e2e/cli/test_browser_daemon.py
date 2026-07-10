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
    """Stand-in for BrowserAutomation: same method shapes, no real browser.

    Mirrors the session-per-tab model: tabs live in `_pages` keyed by a session
    key (None = default/base tab); `_bind_session` records the active key.
    """

    def __init__(self):
        self.calls = []
        self._headless = True
        self._pages = {None: object()}   # default/base tab always exists
        self._tab_meta = {}
        self._session = None

    def _bind_session(self, key):
        self._session = key

    def _bound_session_key(self):
        return self._session

    def go_to(self, url: str, purpose: str = "", who: str = "", hours: float = 0.0) -> str:
        self.calls.append(("go_to", url))
        if purpose or who:
            self._tab_meta[self._session] = {"who": who, "purpose": purpose}
        return f"Navigated to {url}"

    def newtab(self, url: str = "", purpose: str = "", who: str = "") -> str:
        if not purpose or not who:
            raise ValueError("newtab requires --purpose and --who")
        key = self._session
        self._pages[key] = object()
        self._tab_meta[key] = {"who": who, "purpose": purpose}
        self.calls.append(("newtab", url, purpose, who))
        if url:
            return self.go_to(url, purpose=purpose, who=who)
        return f"Opened new tab · who={who} · purpose={purpose!r}"

    def tab_status(self) -> str:
        lines = [f"Tabs ({len(self._pages)}):"]
        for key, meta in self._tab_meta.items():
            name = "default" if key is None else key
            marker = "*" if key == self._session else " "
            lines.append(f"  {marker}[{name}] who={meta.get('who', '-')}  purpose={meta.get('purpose', '-')!r}")
        return "\n".join(lines)

    def close_tab(self, key) -> str:
        if key not in self._pages:
            return f"No open tab for {key!r}"
        self._pages.pop(key, None)
        self._tab_meta.pop(key, None)
        return "Tab closed"

    def take_screenshot(self, path: str = None, full_page: bool = False) -> str:
        return f"shot path={path} full={full_page}"

    def get_links_from_page(self, domain_filter: str = "") -> list:
        return ["https://a.com", "https://b.com"]

    def _browser_is_usable(self) -> bool:
        return True

    def _launch_failed(self) -> bool:
        return False

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


def test_dispatch_image_payload_shows_path_not_base64(tmp_path):
    """A CLI verb returning a base64 image shows the saved path, not the blob."""
    class ImageBrowser(StubBrowser):
        def __init__(self):
            super().__init__()
            self.last_screenshot_path = ".tmp/screenshots/step_x.png"

        def take_screenshot(self, path: str = None, full_page: bool = False) -> str:
            return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="

    daemon = make_daemon(str(tmp_path / "s.sock"), stub=ImageBrowser())
    ok, payload = daemon.dispatch("take_screenshot")
    assert ok is True
    assert payload == "Screenshot saved to: .tmp/screenshots/step_x.png"
    assert "base64" not in payload


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
    assert "usage: go_to(url" in payload


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


# ---- status + tab accountability ----------------------------------------

def test_ago_formats_durations():
    assert d._ago(5) == "5s ago"
    assert d._ago(90) == "1m ago"
    assert d._ago(7200) == "2h ago"
    assert d._ago(200000) == "2d ago"


def test_status_reports_last_command_and_tabs(tmp_path):
    """`status` shows browser state, the active tab, the last command, and tabs (with who/purpose)."""
    daemon = make_daemon(str(tmp_path / "s.sock"))
    daemon.dispatch('go_to x.com --purpose=launch --who=aaron')

    ok, payload = daemon.dispatch("status")
    assert ok is True
    assert "Browser: open" in payload
    assert "active tab=default" in payload
    assert "go_to x.com" in payload
    assert "who=aaron" in payload
    assert "launch" in payload
    assert "Tabs (1):" in payload


def test_use_switches_active_tab(tmp_path):
    """`use`/`switch` change which tab subsequent commands target; `default` returns to base."""
    daemon = make_daemon(str(tmp_path / "s.sock"))
    daemon.dispatch('newtab a.com --purpose=work --who=aaron')  # allocates tab "1", makes it active
    assert daemon.current_session == "1"

    ok, payload = daemon.dispatch("use default")
    assert ok is True
    assert daemon.current_session is None
    assert "Switched to tab default" in payload

    ok, payload = daemon.dispatch("switch 1")
    assert ok is True
    assert daemon.current_session == "1"


def test_use_unknown_tab_is_error(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, payload = daemon.dispatch("use 99")
    assert ok is False
    assert "unknown tab: 99" in payload


def test_use_without_arg_shows_usage(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, payload = daemon.dispatch("use")
    assert ok is False
    assert "usage: use <tab>" in payload


def test_newtab_allocates_incrementing_tab_ids(tmp_path):
    """Each `newtab` occupies a fresh tab id and makes it active."""
    daemon = make_daemon(str(tmp_path / "s.sock"))

    ok, payload = daemon.dispatch('newtab a.com --purpose=work --who=aaron')
    assert ok is True
    assert payload.startswith("[tab 1]")
    assert daemon.current_session == "1"

    ok, payload = daemon.dispatch('newtab b.com --purpose=inbox --who=tamara')
    assert ok is True
    assert payload.startswith("[tab 2]")
    assert daemon.current_session == "2"
    assert set(daemon.browser._pages) == {None, "1", "2"}


def test_newtab_missing_who_rolls_back(tmp_path):
    """A refused newtab (missing who/purpose) must not leave a half-created active tab."""
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, payload = daemon.dispatch('newtab a.com --purpose=work')  # who missing
    assert ok is False
    assert "requires --purpose and --who" in payload
    assert daemon.current_session is None


# ---- closetab: close ONE tab, leave the rest open -----------------------

def test_closetab_closes_a_tab(tmp_path):
    """`closetab <id>` closes just that tab; the others stay in _pages."""
    daemon = make_daemon(str(tmp_path / "s.sock"))
    p0, p1 = object(), object()
    daemon.browser._pages = {None: p0, "1": p1}

    ok, payload = daemon.dispatch("closetab 1")
    assert ok is True
    assert "1" not in daemon.browser._pages
    assert None in daemon.browser._pages   # the rest of the browser stays open
    assert "Closed tab 1" in payload


def test_closetab_unknown_tab_is_error(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, payload = daemon.dispatch("closetab 9")
    assert ok is False
    assert "unknown tab" in payload


def test_closetab_without_arg_shows_usage(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, payload = daemon.dispatch("closetab")
    assert ok is False
    assert "usage: closetab" in payload


def test_closetab_active_tab_repoints_current(tmp_path):
    """Closing the active tab re-points current_session to a still-open tab."""
    daemon = make_daemon(str(tmp_path / "s.sock"))
    p0, p1 = object(), object()
    daemon.browser._pages = {None: p0, "1": p1}
    daemon.current_session = "1"

    ok, payload = daemon.dispatch("closetab 1")
    assert ok is True
    assert daemon.current_session != "1"        # no longer pointing at the closed tab
    assert daemon.current_session is None        # re-pointed at the remaining (default) tab


def test_status_does_not_become_the_last_command(tmp_path):
    """Running `status` must not overwrite the recorded last command."""
    daemon = make_daemon(str(tmp_path / "s.sock"))
    daemon.dispatch("go_to x.com")
    daemon.dispatch("status")
    assert daemon.last_command["line"] == "go_to x.com"


def test_status_before_any_command(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, payload = daemon.dispatch("status")
    assert ok is True
    assert "Last command: (none yet)" in payload


# ---- self-describing help (no browser launched) -------------------------

def test_signature_str():
    assert d.signature_str(StubBrowser.go_to) == "(url, purpose='', who='', hours=0.0)"
    assert d.signature_str(StubBrowser.take_screenshot) == "(path=None, full_page=False)"


def test_list_functions_describes_real_methods():
    """`co browser help` introspects BrowserAutomation: name + signature + summary."""
    text = d.list_functions()
    assert "go_to(url" in text
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
    assert "go_to(url" in out


def test_next_tip_rotates(tmp_path, monkeypatch):
    """Each run surfaces the next tip; the index wraps around and persists in ~/.co."""
    import pathlib
    from connectonion.cli.commands import browser_commands as bc

    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)

    seen = [bc._next_tip() for _ in range(len(bc.TIPS) + 1)]
    assert seen[0] == bc.TIPS[0]
    assert seen[1] == bc.TIPS[1]
    assert seen[len(bc.TIPS)] == bc.TIPS[0]          # wrapped back to the start
    assert (tmp_path / ".co" / ".browser_tip").exists()


def test_tip_hidden_when_not_a_tty(monkeypatch, capsys):
    """Piped/scripted output (and the NL agent) must not get a decorative tip."""
    from connectonion.cli.commands import browser_commands as bc

    monkeypatch.setattr(bc, "send", lambda *a, **k: 0)
    monkeypatch.setattr(bc.sys.stdout, "isatty", lambda: False)

    code = bc.handle_browser(["go_to", "x.com"])
    out = capsys.readouterr().out
    assert code == 0
    assert "💡" not in out


def test_tip_shown_on_success_tty(tmp_path, monkeypatch, capsys):
    """On an interactive terminal a successful command appends a rotating tip."""
    import pathlib
    from connectonion.cli.commands import browser_commands as bc

    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(bc, "send", lambda *a, **k: 0)
    monkeypatch.setattr(bc.sys.stdout, "isatty", lambda: True)

    code = bc.handle_browser(["go_to", "x.com"])
    out = capsys.readouterr().out
    assert code == 0
    assert "💡" in out


def test_handle_browser_no_args_is_usage_error(capsys):
    from connectonion.cli.commands.browser_commands import handle_browser
    code = handle_browser([])
    err = capsys.readouterr().err
    assert code == 1
    assert "co browser [-t TAB] <function>" in err


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


class LaunchFailBrowser(StubBrowser):
    """A browser whose launch aborts (e.g. Chrome SIGABRT): commands raise a huge
    patchright-style Call log, the context never comes up, and _launch_failed is True."""

    def go_to(self, url: str, purpose: str = "", who: str = "", hours: float = 0.0) -> str:
        raise RuntimeError("Target page, context or browser has been closed\n" +
                           "Call log:\n" + "  - <launching> chrome ...\n" * 20)

    def _browser_is_usable(self) -> bool:
        return False

    def _launch_failed(self) -> bool:
        return True


def test_launch_failure_makes_daemon_exit(short_sock, monkeypatch, capsys):
    """A daemon that can never open a browser must exit (release the socket), not linger
    as a zombie that every later `co browser` reuses."""
    sock_path = short_sock
    monkeypatch.setenv("CO_BROWSER_SOCK", sock_path)

    daemon = make_daemon(sock_path, stub=LaunchFailBrowser())
    t = threading.Thread(target=daemon.serve, daemon=True)
    t.start()
    _wait_until_listening(sock_path)

    code = c.send("go_to example.com", headless=True)
    assert code == 1
    t.join(timeout=2)
    assert not t.is_alive()  # serve loop broke out → daemon is exiting


def test_launch_failure_message_is_actionable(short_sock, monkeypatch, capsys):
    """The ERR payload for a failed launch is a short, actionable hint — not the raw
    multi-line patchright Call log dumped to the shell."""
    sock_path = short_sock
    monkeypatch.setenv("CO_BROWSER_SOCK", sock_path)

    daemon = make_daemon(sock_path, stub=LaunchFailBrowser())
    threading.Thread(target=daemon.serve, daemon=True).start()
    _wait_until_listening(sock_path)

    code = c.send("go_to example.com", headless=True)
    err = capsys.readouterr().err
    assert code == 1
    assert "Chrome failed to start" in err
    assert "~/.co/browser.log" in err
    assert "<launching> chrome" not in err  # the giant Call log is not dumped


# --- the -t / tab noun grammar (one task = one tab) ---

def test_tab_open_prints_only_the_name(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, payload = daemon.dispatch('tab open pr-142 --who claude-a --for "review PR"')
    assert ok is True
    assert payload == "pr-142"
    assert daemon.browser._tab_meta["pr-142"]["who"] == "claude-a"
    assert daemon.browser._tab_meta["pr-142"]["purpose"] == "review PR"


def test_tab_open_autogenerates_name_and_defaults_who_to_caller(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, name = daemon.dispatch("%codex-b tab open")
    assert ok is True
    assert daemon.browser._tab_meta[name]["who"] == "codex-b"


def test_targeting_unknown_tab_is_exit_3_and_teaches_lifecycle(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, payload = daemon.dispatch("@nope go_to x.com")
    assert ok == 3
    assert "no tab named 'nope'" in payload
    assert "tab open nope" in payload
    assert "-t nope" in payload
    assert "tab close nope" in payload


def test_targeting_registered_tab_binds_its_session(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    daemon.dispatch("tab open mytask --who me --for work")
    ok, _ = daemon.dispatch("@mytask go_to x.com")
    assert ok is True
    assert daemon.browser._session == "mytask"


def test_main_alias_needs_no_registration(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, _ = daemon.dispatch("@main go_to x.com")
    assert ok is True
    assert daemon.browser._session is None


def test_second_agent_on_main_is_exit_4_and_taught_to_open_a_tab(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    ok, _ = daemon.dispatch("%agent-a go_to x.com")
    assert ok is True
    ok, payload = daemon.dispatch("%agent-b go_to y.com")
    assert ok == 4
    assert "in use by agent-a" in payload
    assert "tab open" in payload
    ok, _ = daemon.dispatch("%agent-a go_to z.com")  # the owner keeps working
    assert ok is True


def test_same_agent_keeps_main_and_status_is_never_blocked(tmp_path):
    daemon = make_daemon(str(tmp_path / "s.sock"))
    daemon.dispatch("%agent-a go_to x.com")
    ok, _ = daemon.dispatch("%agent-a take_screenshot")
    assert ok is True
    ok, _ = daemon.dispatch("%agent-b status")  # read-only: always allowed
    assert ok is True


def test_tab_ls_json(tmp_path):
    import json as _json
    daemon = make_daemon(str(tmp_path / "s.sock"))
    daemon.dispatch("tab open jobx --who codex --for publish")
    ok, payload = daemon.dispatch("tab ls --json")
    assert ok is True
    board = _json.loads(payload)
    assert {"tab": "jobx", "who": "codex", "purpose": "publish", "last_line": None, "last_at": None} == board[0]
