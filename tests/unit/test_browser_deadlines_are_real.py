"""Every browser command ends, and the ways out of a stuck browser stay open.

Found re-testing main at 1f38204 on a Mac whose cookie store waited on the
Keychain. `co browser cookies --all` and `save_state` never returned. Killing
the client freed nothing: the request stayed on `tab ls --json` under
active_requests fifteen minutes later, every later command on that tab queued
behind it with no deadline, and after about thirty of them even `status` and
`close` were answered "busy at connection capacity". The docs promised
120-second deadlines, and that entries leave the board on disconnect.

The fakes stand in for that Chrome: a context whose cookies() and
storage_state() never return. The rest of the file covers what the same
tester found alongside it.
"""

import asyncio
import json
import os
import re
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest

from connectonion.cli.browser_agent import client as browser_client
from connectonion.cli.browser_agent import daemon as daemon_module
from connectonion.cli.browser_agent.client import _oip_command
from connectonion.cli.browser_agent.daemon import BrowserDaemon, _result_code
from connectonion.network.oip.framing import encode_frame
from connectonion.useful_tools.browser_tools._async_browser import AsyncBrowserCore


def envelope(line: str, *, caller: str = "tester", tab=None) -> str:
    return json.dumps({"v": 1, "caller": caller, "account": "", "tab": tab, "line": line})


class FakePage:
    url = "https://example.com/"

    def is_closed(self):
        return False

    def on(self, *_args):
        return None

    async def close(self):
        return None


class KeychainStalledContext:
    """A persistent context whose cookie store waits on a Keychain prompt nobody answers."""

    def __init__(self):
        self.pages = [FakePage()]

    async def cookies(self, *_args):
        await asyncio.Event().wait()

    async def storage_state(self, **_kwargs):
        await asyncio.Event().wait()

    async def close(self):
        return None


def stalled_core() -> AsyncBrowserCore:
    core = AsyncBrowserCore(headless=True)
    core.browser = KeychainStalledContext()
    core._pages[None] = core.browser.pages[0]
    return core


@pytest.fixture
def short_dir():
    directory = tempfile.mkdtemp(prefix="cod")  # AF_UNIX paths are capped near 104 bytes
    yield Path(directory)
    shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture
def quick(monkeypatch):
    monkeypatch.setattr(daemon_module, "LIVENESS_TIMEOUT", 0.05, raising=False)
    monkeypatch.setattr(daemon_module, "STATUS_STEP_TIMEOUT", 0.3, raising=False)
    monkeypatch.setattr(daemon_module, "CANCEL_GRACE", 1.0, raising=False)
    monkeypatch.setattr(daemon_module, "DISCONNECT_POLL", 0.02, raising=False)


def serve(sock: str, monkeypatch) -> tuple:
    monkeypatch.setenv("CO_BROWSER_SOCK", sock)
    server = BrowserDaemon(sock, headless=True)
    server.browser = stalled_core()
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not os.path.exists(sock) and time.monotonic() < deadline:
        time.sleep(0.02)
    return server, thread


def stop(server, thread) -> None:
    if thread.is_alive():
        server._loop.call_soon_threadsafe(server._begin_shutdown)
        thread.join(timeout=15)


def raw_send(sock: str, line: str, tab=None) -> socket.socket:
    """A client that sends one command and then waits, as a stuck `co browser` does."""
    frame, _ = _oip_command(line, caller="tester", account="", tab=tab, engine="auto")
    # The daemon listens with a backlog of MAX_IN_FLIGHT (32). macOS refuses an
    # AF_UNIX connect outright once that backlog is full, instead of blocking
    # as Linux does, so forty connects fired in a tight loop at a daemon whose
    # loop is starved of CPU (a loaded `-n auto` run) got ECONNREFUSED on the
    # 33rd. The real client (`_connect_posix`) retries refusals for about two
    # seconds for exactly this reason; this stand-in for a stuck client does
    # the same, with a wider window because it is the test harness, not what
    # is under test.
    deadline = time.monotonic() + 10
    while True:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            conn.connect(sock)
            break
        except ConnectionRefusedError:
            conn.close()
            if time.monotonic() > deadline:
                raise
            time.sleep(0.02)
    conn.sendall(encode_frame(frame))
    return conn


def active(server) -> list:
    code, payload = browser_client._request_with_identity("tab ls --json", caller="t", account="")
    assert code == 0, payload
    return [request for tab in json.loads(payload) for request in tab["active_requests"]]


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


# ---- 1. every command ends within its deadline ------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("line", ["cookies --all", "save_state /tmp/never-written.json"])
async def test_a_stalled_cookie_store_is_a_timeout_that_names_it(line, quick, monkeypatch):
    monkeypatch.setattr(daemon_module, "OPERATION_TIMEOUT", 0.3, raising=False)
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    server.browser = stalled_core()

    started = time.monotonic()
    ok, payload = await asyncio.wait_for(server.dispatch_async(envelope(line)), 10)

    assert time.monotonic() - started < 3
    assert ok == 1, payload
    assert "did not finish within 0.3s" in payload
    assert "cookie store" in payload and "Keychain" in payload
    assert "Next:" in payload and "co browser close" in payload
    # It let go of the tab: nothing on the board, and the next command runs.
    assert "active_requests" not in server.browser._tab_meta.get(None, {})
    ok, url = await asyncio.wait_for(server.dispatch_async(envelope("get_current_url")), 5)
    assert (ok, url) == (True, "https://example.com/")


@pytest.mark.asyncio
async def test_a_longer_timeout_of_its_own_extends_the_deadline(monkeypatch):
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    server.browser = stalled_core()

    assert server._deadline_for(envelope("get_current_url")) == daemon_module.OPERATION_TIMEOUT
    assert server._deadline_for(envelope("wait_for_text Done --timeout 300")) == 315
    assert server._deadline_for(envelope("wait_for_text Done 300")) == 315
    assert server._deadline_for(envelope("wait_for_text Done 30")) == daemon_module.OPERATION_TIMEOUT


# ---- 2. a client that leaves takes its request with it ----------------------


def test_a_client_that_disconnects_frees_its_request_and_its_tab(short_dir, quick, monkeypatch):
    sock = str(short_dir / "b.sock")
    server, thread = serve(sock, monkeypatch)
    try:
        conn = raw_send(sock, "cookies --all")
        assert wait_until(lambda: len(active(server)) == 1)
        conn.close()  # the client is killed; the deadline is still two minutes away

        assert wait_until(lambda: active(server) == [], timeout=5), active(server)
        code, url = browser_client._request_with_identity(
            "get_current_url", caller="tester", account=""
        )
        assert (code, url) == (0, "https://example.com/")
    finally:
        stop(server, thread)


# ---- 3. status and close are never refused ----------------------------------


def test_forty_stuck_requests_leave_status_and_close_working(short_dir, quick, monkeypatch):
    sock = str(short_dir / "b.sock")
    server, thread = serve(sock, monkeypatch)
    stuck = []
    try:
        # The forty arrive while the daemon's loop is busy and accepting
        # nothing, which is what a loaded machine did to this test now and
        # then. Making it happen every run means the listen backlog overflows
        # every run, so the retry in raw_send is exercised rather than lucky.
        stalled = threading.Event()

        def stall_the_loop():
            stalled.set()
            time.sleep(0.5)

        server._loop.call_soon_threadsafe(stall_the_loop)
        assert stalled.wait(5)
        for _ in range(40):
            stuck.append(raw_send(sock, "cookies --all"))
        assert wait_until(
            lambda: len(server._client_tasks) == daemon_module.MAX_IN_FLIGHT, timeout=10
        )

        started = time.monotonic()
        code, payload = browser_client._request_with_identity("status", caller="t", account="")
        assert code == 0, payload
        assert payload.startswith("Browser:"), payload
        assert time.monotonic() - started < 10

        code, payload = browser_client._request_with_identity("close", caller="t", account="")
        assert code == 0, payload
        assert "busy" not in payload
        thread.join(timeout=15)
        assert not thread.is_alive(), "close must stop a daemon whose commands are stuck"
    finally:
        for conn in stuck:
            conn.close()
        stop(server, thread)


# ---- 4. a frozen daemon is reported, not waited on --------------------------


@pytest.mark.parametrize("line", ["status", "tab ls"])
def test_status_against_a_frozen_daemon_says_so_and_names_close(line, short_dir, monkeypatch):
    sock = str(short_dir / "b.sock")
    monkeypatch.setenv("CO_BROWSER_SOCK", sock)
    monkeypatch.setattr(browser_client, "QUICK_REPLY_DEADLINE", 0.5)
    # kill -STOP: the kernel still accepts the connection; nothing ever answers.
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(sock)
    listener.listen(8)
    Path(sock + ".pid").write_text(str(os.getpid()), encoding="utf-8")
    try:
        started = time.monotonic()
        code, payload = browser_client._request_with_identity(line, caller="t", account="")
        assert time.monotonic() - started < 5
        assert code == 1
        assert "not answer" in payload and "stopped or stuck" in payload
        assert "co browser close" in payload
    finally:
        listener.close()


# ---- 5. failures exit non-zero -----------------------------------------------


@pytest.mark.parametrize(
    "verb,payload",
    [
        ("run_page_script", "Script not found: /work/missing.js"),
        ("run_frame_script", "Script not found: /work/missing.js"),
        ("switch_page", "no page 99; the browser has 1:\n  0: https://example.com/"),
        ("upload_file_by_selector", "No file input found for selector: #nope"),
        ("upload_file_by_selector", "Selector matched 1 file input(s); index 3 is out of range"),
    ],
)
def test_these_failures_exit_1(verb, payload):
    assert _result_code(verb, payload, None)[0] is False


def test_a_page_script_that_returns_the_same_words_is_still_an_answer():
    # The page's value comes back as JSON, so its string starts with a quote.
    assert _result_code("run_page_script", '"Script not found: x"', None)[0] is True


# ---- 6. no browser, no daemon; and --headless is not ignored in silence -------


def test_a_read_with_nothing_running_does_not_start_a_daemon(short_dir, monkeypatch):
    monkeypatch.setenv("CO_BROWSER_SOCK", str(short_dir / "none.sock"))

    def must_not_spawn(*_args, **_kwargs):
        raise AssertionError("a daemon was started to answer that no browser is open")

    monkeypatch.setattr(browser_client, "_spawn_daemon", must_not_spawn)
    monkeypatch.setattr(browser_client, "_ensure_browser_ready", must_not_spawn)

    code, payload = browser_client._request_with_identity(
        "get_current_url", caller="c", account="", tab="U"
    )

    assert code == 3
    assert "Next: co browser -t U go_to <url>" in payload


def test_headless_against_a_headed_daemon_is_reported(monkeypatch, capsys):
    monkeypatch.setattr(browser_client, "_mode_warned", False)
    monkeypatch.setattr(browser_client, "_owner_pid", lambda _sock: 424242)
    monkeypatch.setattr(browser_client, "_daemon_headless", lambda _pid: False)
    monkeypatch.setenv("DISPLAY", ":0")

    browser_client._warn_if_headed("/tmp/x.sock")

    err = capsys.readouterr().err
    assert "--headless has no effect" in err and "co browser close" in err


def test_headless_against_a_headless_daemon_says_nothing(monkeypatch, capsys):
    monkeypatch.setattr(browser_client, "_mode_warned", False)
    monkeypatch.setattr(browser_client, "_owner_pid", lambda _sock: 424242)
    monkeypatch.setattr(browser_client, "_daemon_headless", lambda _pid: True)

    browser_client._warn_if_headed("/tmp/x.sock")

    assert capsys.readouterr().err == ""


# ---- 7. errors without exception class names ----------------------------------


class PatchrightTimeout(Exception):
    pass


PatchrightTimeout.__name__ = "TimeoutError"
PatchrightTimeout.__module__ = "patchright._impl._errors"


class PatchrightError(Exception):
    pass


PatchrightError.__name__ = "Error"
PatchrightError.__module__ = "patchright._impl._errors"


class RaisingCore(AsyncBrowserCore):
    async def get_text(self):
        raise PatchrightTimeout(
            "Page.goto: Timeout 30000ms exceeded.\nCall log:\n  - navigating to x"
        )

    async def run_page_script(self, script_path: str, args_json: str = "{}"):
        raise PatchrightError("Page.evaluate: SyntaxError: Unexpected token '}'")


@pytest.mark.asyncio
async def test_a_driver_timeout_reads_as_a_sentence_and_keeps_the_tab():
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    server.browser = RaisingCore(headless=True)
    await server.dispatch_async(envelope("tab open U"))

    ok, payload = await server.dispatch_async(envelope("get_text", tab="U"))

    assert ok is False
    assert payload.startswith("get_text timed out: Timeout 30000ms exceeded.")
    assert "TimeoutError" not in payload and "Call log" not in payload and "Page.goto" not in payload
    assert "-t U" in payload


@pytest.mark.asyncio
async def test_a_script_error_names_the_script_not_the_driver():
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    server.browser = RaisingCore(headless=True)

    ok, payload = await server.dispatch_async(envelope("run_page_script x.js"))

    assert ok is False
    assert payload.startswith("run_page_script failed in the page: SyntaxError")
    assert not payload.startswith("Error:") and "Page.evaluate" not in payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "line,expected",
    [("get_text extra", "usage: co browser get_text()"),
     ("wait abc", "seconds is a number"),
     ("go_to", "usage: co browser go_to(url")],
)
async def test_wrong_arguments_are_a_usage_error_with_the_signature(line, expected):
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    server.browser = stalled_core()

    ok, payload = await server.dispatch_async(envelope(line))

    assert ok == 2, payload
    assert expected in payload
    assert "TypeError" not in payload and "could not convert" not in payload


@pytest.mark.asyncio
async def test_a_refused_address_keeps_the_tab_in_its_next_step():
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    await server.dispatch_async(envelope("tab open U"))

    ok, payload = await server.dispatch_async(envelope("go_to htp://example.com", tab="U"))

    assert ok == 2
    assert "Next: co browser -t U go_to https://example.com" in payload


# ---- 8. tab close of a tab that is not there ----------------------------------


@pytest.mark.asyncio
async def test_closing_an_unknown_tab_says_there_is_nothing_to_close():
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    server.browser = stalled_core()
    await server.dispatch_async(envelope("tab open A"))

    ok, payload = await server.dispatch_async(envelope("tab close Y"))

    assert ok == 3
    assert "nothing to close" in payload
    assert "[A]" in payload
    assert "create it first" not in payload and "tab open Y" not in payload


# ---- 9. co proxy ------------------------------------------------------------


def test_proxy_diagnose_help_through_the_cli_is_its_own():
    from typer.testing import CliRunner

    from connectonion.cli.main import app

    result = CliRunner().invoke(app, ["proxy", "diagnose", "--help"])
    text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)

    assert result.exit_code == 0
    assert "co proxy diagnose <address>" in text


def test_proxy_help_through_the_cli_is_the_proxy_usage():
    from typer.testing import CliRunner

    from connectonion.cli.main import app

    result = CliRunner().invoke(app, ["proxy", "--help"])
    text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)

    assert result.exit_code == 0
    assert "co proxy share" in text


def test_proxy_stop_rejects_something_that_is_not_an_address(capsys):
    from connectonion.cli.commands import proxy_commands

    code = proxy_commands.handle_proxy(["stop", "notanaddress"])

    text = capsys.readouterr().err
    assert code == 2
    assert "notanaddress" in text and "0x" in text


# ---- 10. papercuts --------------------------------------------------------------


class ContextThatWillNotClose(KeychainStalledContext):
    async def close(self):
        raise asyncio.TimeoutError()


@pytest.mark.asyncio
async def test_a_cleanup_warning_always_says_why():
    core = AsyncBrowserCore(headless=True)
    core.browser = ContextThatWillNotClose()

    message = await core.close()

    assert "close context failed: " in message
    assert not re.search(r"close context failed: ($|;)", message)


@pytest.mark.asyncio
async def test_no_browser_open_is_one_sentence_everywhere():
    server = BrowserDaemon("/tmp/unused.sock", headless=True)

    _ok, payload = await server.dispatch_async(envelope("close"))

    assert payload.startswith("No browser is open")


@pytest.mark.asyncio
async def test_the_board_shows_what_was_typed():
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    server.browser = stalled_core()
    await server.dispatch_async(envelope("tab open A"))
    await server.dispatch_async(envelope("tab close A"))

    assert server.last_command["line"] == "tab close A"


@pytest.mark.asyncio
async def test_the_rival_tab_error_quotes_nothing_it_does_not_have():
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    server.browser = stalled_core()
    await server.dispatch_async(envelope("tab open U", caller="alice"))

    ok, payload = await server.dispatch_async(envelope("tab close U", caller="bob"))

    assert ok == 4
    assert 'last: ""' not in payload
    assert "no command yet" in payload


def test_a_closed_page_future_is_not_logged_as_never_retrieved():
    class TargetClosedError(Exception):
        pass

    logged = []

    class Loop:
        def default_exception_handler(self, context):
            logged.append(context)

    closed = {"message": "Future exception was never retrieved",
              "exception": TargetClosedError("Target page, context or browser has been closed")}
    other = {"message": "Future exception was never retrieved", "exception": KeyError("x")}

    daemon_module._quiet_closed_targets(Loop(), closed)
    daemon_module._quiet_closed_targets(Loop(), other)

    assert logged == [other]
