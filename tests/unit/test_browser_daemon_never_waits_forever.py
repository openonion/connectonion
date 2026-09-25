"""The browser daemon answers every command, even when Chrome does not answer it.

Found on 1.8.8b7 (and already true of 1.8.7): after every reply the daemon asked
Chrome whether it was still alive by reading its cookies, with no deadline, and
kept the client's connection open until Chrome answered. On a Mac whose cookie
store was waiting on the Keychain, Chrome never answered. Each command left one
connection behind, the 32-client limit filled after about thirty commands, and
from then on every command failed with "browser daemon closed or rejected the
OIP stream" — while `co browser status` hung for minutes on the same question.

The fakes here stand in for exactly that Chrome: its cookie store never returns.
No real browser is needed to show the daemon must not wait on it forever.

The rest of the file covers the smaller things the same tester hit: action
failures that exited 0, a flag value read as a file name, a URL rewritten into
nonsense and then waited on for 30 seconds, and messages that said the wrong
thing.
"""

import asyncio
import json
import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path

import pytest

from connectonion.cli.browser_agent import client as browser_client
from connectonion.cli.browser_agent import daemon as daemon_module
from connectonion.cli.browser_agent.client import _oip_command
from connectonion.cli.browser_agent.daemon import BrowserDaemon, _split_tokens
from connectonion.useful_tools.browser_tools import _async_network as network_log
from connectonion.useful_tools.browser_tools._async_browser import AsyncBrowserCore


def envelope(line: str, *, caller: str = "tester", tab=None) -> str:
    return json.dumps({"v": 1, "caller": caller, "account": "", "tab": tab, "line": line})


class FakePage:
    def __init__(self, url="https://example.com/"):
        self.url = url
        self.closed = False

    def is_closed(self):
        return self.closed

    def on(self, *_args):
        return None

    async def close(self):
        self.closed = True

    def locator(self, _selector):
        return FakeLocator()


class FakeLocator:
    async def count(self):
        return 0


class StalledCookieStore:
    """A persistent context whose cookie store is waiting on the macOS Keychain."""

    def __init__(self):
        self.pages = [FakePage()]
        self.cookie_calls = 0

    async def cookies(self, *_args):
        self.cookie_calls += 1
        await asyncio.Event().wait()  # never set: the Keychain prompt nobody answers

    async def close(self):
        return None


def stalled_core() -> AsyncBrowserCore:
    core = AsyncBrowserCore(headless=True)
    core.browser = StalledCookieStore()
    core._pages[None] = core.browser.pages[0]
    return core


def open_core() -> AsyncBrowserCore:
    """A core with one live page whose selectors match nothing."""
    core = stalled_core()
    return core


# ---- 1. a stalled liveness probe never costs a connection -------------------


@pytest.fixture
def short_dir():
    # AF_UNIX paths are capped near 104 bytes; pytest's tmp_path can exceed it.
    directory = tempfile.mkdtemp(prefix="cow")
    yield Path(directory)
    shutil.rmtree(directory, ignore_errors=True)


def test_forty_commands_against_a_stalled_cookie_store_all_succeed(short_dir, monkeypatch):
    sock = str(short_dir / "b.sock")
    monkeypatch.setenv("CO_BROWSER_SOCK", sock)
    monkeypatch.setattr(daemon_module, "LIVENESS_TIMEOUT", 0.2, raising=False)
    server = BrowserDaemon(sock, headless=True)
    server.browser = stalled_core()
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not os.path.exists(sock) and time.monotonic() < deadline:
        time.sleep(0.02)

    try:
        codes, most_in_flight = [], 0
        for _ in range(40):
            code, payload = browser_client._request_with_identity(
                "get_current_url", caller="tester", account=""
            )
            codes.append((code, payload))
            most_in_flight = max(most_in_flight, len(server._client_tasks))

        assert all(code == 0 for code, _ in codes), codes[-3:]
        assert codes[-1][1] == "https://example.com/"
        # Before the fix every command left its connection open behind a
        # cookie read that never returned; 32 of them filled the daemon.
        assert most_in_flight <= 2
        # One question to Chrome at a time, not one more per command.
        assert server.browser.browser.cookie_calls <= 2
    finally:
        server._loop.call_soon_threadsafe(server._begin_shutdown)
        thread.join(timeout=10)
    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_a_liveness_probe_that_times_out_does_not_stop_the_daemon(monkeypatch):
    monkeypatch.setattr(daemon_module, "LIVENESS_TIMEOUT", 0.05, raising=False)
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    server.browser = stalled_core()

    started = time.monotonic()
    stop = await server._should_stop(True, "https://example.com/")

    assert stop is False, "a slow cookie store is not a dead browser"
    assert time.monotonic() - started < 1
    server._alive_probe.cancel()


class FakeTransport:
    def __init__(self):
        self.aborted = False

    def abort(self):
        self.aborted = True


class RecordingWriter:
    def __init__(self):
        self.transport = FakeTransport()
        self.payload = b""
        self.closed = False

    def write(self, payload: bytes):
        self.payload += payload

    async def drain(self):
        return None

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None


@pytest.mark.asyncio
async def test_at_capacity_the_client_is_told_busy_not_dropped():
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    blockers = {
        asyncio.create_task(asyncio.sleep(30)) for _ in range(daemon_module.MAX_IN_FLIGHT)
    }
    server._client_tasks.update(blockers)
    frame, _ = _oip_command("get_text", caller="c", account="", tab=None, engine="auto")
    reader = asyncio.StreamReader()
    from connectonion.network.oip.framing import decode_frame, encode_frame

    reader.feed_data(encode_frame(frame))
    reader.feed_eof()
    writer = RecordingWriter()

    server._accept_posix_client(reader, writer)
    await asyncio.gather(*server._shed_tasks)

    reply = decode_frame(writer.payload)
    assert reply.WhichOneof("frame") == "failure"
    assert "busy at connection capacity" in reply.failure.message
    assert reply.request_id == frame.request_id
    assert writer.closed is True
    assert server._client_tasks == blockers, "a shed client must not take a slot"
    for task in blockers:
        task.cancel()
    await asyncio.gather(*blockers, return_exceptions=True)


# ---- 2. status has a deadline and says what it waited on -------------------


@pytest.mark.asyncio
async def test_status_answers_when_chrome_does_not(monkeypatch):
    monkeypatch.setattr(daemon_module, "LIVENESS_TIMEOUT", 0.05, raising=False)
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    server.browser = stalled_core()

    ok, payload = await asyncio.wait_for(server.dispatch_async(envelope("status")), 10)

    assert ok is True
    first = payload.splitlines()[0]
    assert "did not answer" in first
    assert "cookie" in first.lower()
    server._alive_probe.cancel()


# ---- 3. an action that failed exits 1 ---------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "line",
    ["click_element_by_selector '#nope'", "type_text_by_selector '#nope' x",
     "fill_text_by_selector '#nope' x", "get_element_text_by_selector '#nope'"],
)
async def test_a_selector_that_matches_nothing_is_a_failure(line):
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    server.browser = open_core()

    ok, payload = await server.dispatch_async(envelope(line))

    assert ok is False, payload
    assert payload.startswith("No element found for selector: #nope")


@pytest.mark.asyncio
async def test_a_count_of_zero_is_an_answer_not_a_failure():
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    server.browser = open_core()

    ok, payload = await server.dispatch_async(envelope("count_elements_by_selector '#nope'"))

    assert ok is True
    assert payload.startswith("0 elements")


@pytest.mark.asyncio
@pytest.mark.parametrize("tab,flag", [(None, ""), ("X", " -t X")])
async def test_a_command_with_no_browser_open_exits_3_with_a_next_step(tab, flag):
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    if tab is not None:
        ok, _ = await server.dispatch_async(envelope(f"tab open {tab}"))
        assert ok is True

    ok, payload = await server.dispatch_async(envelope("get_current_url", tab=tab))

    assert ok == 3
    assert "not open" in payload
    assert f"Next: co browser{flag} go_to <url>" in payload


# ---- 4. a boolean flag takes its value either way ----------------------------


@pytest.mark.parametrize(
    "line", ["take_screenshot --full-page true", "take_screenshot --full-page=true"]
)
def test_full_page_true_is_a_flag_value_not_a_file_name(line):
    frame, destination = _oip_command(line, caller="c", account="", tab=None, engine="auto")

    assert destination is None
    positional, kwargs = _split_tokens(
        list(frame.command.argv[1:]),
        __import__("inspect").signature(AsyncBrowserCore.take_screenshot).parameters.values(),
    )
    assert positional == []
    assert daemon_module._coerce(kwargs["full_page"], bool) is True


def test_a_bool_flag_followed_by_an_ordinary_word_is_still_a_switch():
    import inspect

    params = inspect.signature(AsyncBrowserCore.take_screenshot).parameters.values()
    positional, kwargs = _split_tokens(["--full-page", "shot.png"], params)

    assert kwargs == {"full_page": True}
    assert positional == ["shot.png"]


def test_a_path_after_full_page_true_still_names_the_file():
    _frame, destination = _oip_command(
        "take_screenshot --full-page false shot.png", caller="c", account="", tab=None, engine="auto"
    )

    assert destination == "shot.png"


# ---- 5. a flag and its value in one token ------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "line,expected",
    [
        ("network requests '--status 4x'", "--status takes 200, 2xx or 400-499, not '4x'"),
        ("network requests --status 4x", "--status takes 200, 2xx or 400-499, not '4x'"),
        ("network requests --status=4x", "--status takes 200, 2xx or 400-499, not '4x'"),
        ("network requests '--type bogus'", "--type takes"),
        ("network requests --type=bogus", "--type takes"),
    ],
)
async def test_network_filters_are_validated_in_every_spelling(line, expected):
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    server.browser = open_core()

    ok, payload = await server.dispatch_async(envelope(line))

    assert ok is False
    assert payload.startswith(expected), payload
    assert "TypeError" not in payload and "ValueError" not in payload


# ---- 6. go_to refuses what is not a web address, at once ---------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url", ["htp://example.com", "not a url", "javascript:alert(1)", "", "mailto:a@b.c", "http://"]
)
async def test_go_to_refuses_a_malformed_or_non_web_url_quickly(url):
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    opened = []

    async def must_not_open(*_args, **_kwargs):
        opened.append(True)
        raise AssertionError("a browser was launched for an address that cannot load")

    server.browser.open_browser = must_not_open
    started = time.monotonic()

    ok, payload = await server.dispatch_async(envelope(f"go_to {json.dumps(url)}"))

    assert ok == 2, payload
    assert time.monotonic() - started < 1
    assert not opened
    assert "Next:" in payload


@pytest.mark.parametrize(
    "url,expected",
    [
        ("example.com", "https://example.com"),
        ("localhost:8000", "http://localhost:8000"),
        ("127.0.0.1:5000/x", "https://127.0.0.1:5000/x"),
        ("https://example.com/a b", "https://example.com/a b"),
        ("data:text/html,<p>x</p>", "data:text/html,<p>x</p>"),
        ("about:blank", "about:blank"),
        ("chrome://version", "chrome://version"),
        ("file:///tmp/x.html", "file:///tmp/x.html"),
        ("HTTPS://Example.com", "HTTPS://Example.com"),
    ],
)
def test_go_to_still_accepts_every_address_that_worked(url, expected):
    from connectonion.useful_tools.browser_tools._async_browser import _normalize_url

    assert _normalize_url(url) == expected


# ---- 7. papercuts -------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_with_nothing_open_says_so():
    server = BrowserDaemon("/tmp/unused.sock", headless=True)

    ok, payload = await server.dispatch_async(envelope("close"))

    assert ok is True
    assert "Session saved" not in payload
    assert "No browser is open" in payload
    assert await server._should_stop(ok, payload) is True


def test_close_with_no_daemon_does_not_start_one(monkeypatch, short_dir):
    monkeypatch.setenv("CO_BROWSER_SOCK", str(short_dir / "none.sock"))

    def must_not_spawn(*_args, **_kwargs):
        raise AssertionError("a daemon was started only to be closed")

    monkeypatch.setattr(browser_client, "_spawn_daemon", must_not_spawn)
    monkeypatch.setattr(browser_client, "_ensure_browser_ready", must_not_spawn)

    code, payload = browser_client._request_with_identity("close", caller="c", account="")

    assert code == 0
    assert "No browser is open" in payload


@pytest.mark.asyncio
async def test_tab_close_says_it_once():
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    server.browser = open_core()
    await server.dispatch_async(envelope("tab open Y"))

    ok, payload = await server.dispatch_async(envelope("tab close Y"))

    assert ok is True
    assert payload == "Closed tab Y."


@pytest.mark.asyncio
async def test_errors_carry_no_exception_class_and_keep_the_tab():
    server = BrowserDaemon("/tmp/unused.sock", headless=True)
    await server.dispatch_async(envelope("tab open X"))

    ok, payload = await server.dispatch_async(envelope("cookies", tab="X"))

    assert ok == 3  # no browser open: the same code as every other verb
    assert not payload.startswith("ValueError")
    assert "Next: co browser -t X go_to <url>" in payload


def _record(n, status):
    return {
        "n": n, "method": "GET", "url": f"https://e.com/{n}", "kind": "fetch",
        "status": status, "resp_size": None, "duration_ms": None, "error": None,
        "req_headers": {}, "req_body": None, "resp_headers": {}, "resp_body": None,
        "truncated": False,
    }


def test_the_request_list_header_comes_first():
    text = network_log.render_list([_record(1, 200), _record(2, 404)])

    assert text.splitlines()[0].startswith("#\tmethod\tstatus")
    assert text.splitlines()[1].startswith("1\t")


def test_a_request_without_a_response_says_so():
    text = network_log.render_one(_record(3, None))

    assert "status=None" not in text
    assert "no response" in text


def test_browser_help_points_at_the_full_list():
    from typer.testing import CliRunner

    from connectonion.cli.commands.browser_commands import USAGE
    from connectonion.cli.main import app

    result = CliRunner().invoke(app, ["browser", "--help"])
    text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)

    assert "co browser help" in text
    assert "tab" in text and "status" in text
    assert "co browser status" in USAGE


# ---- 8. co proxy diagnose ------------------------------------------------------


def test_proxy_diagnose_without_an_address_explains_itself(monkeypatch, capsys):
    from connectonion.cli.commands import proxy_commands, remote_browser_commands

    monkeypatch.setattr(remote_browser_commands, "configured_address", lambda: None)

    code = proxy_commands.handle_proxy(["diagnose"])

    err = capsys.readouterr()
    text = err.out + err.err
    assert code == 2
    assert "remote browser configured" not in text
    assert "co proxy diagnose <address>" in text
    assert "attached" in text


def test_proxy_diagnose_help_is_its_own(capsys):
    from connectonion.cli.commands import proxy_commands

    assert proxy_commands.handle_proxy(["diagnose", "--help"]) == 0
    assert "co proxy diagnose <address>" in capsys.readouterr().out


def test_proxy_diagnose_rejects_something_that_is_not_an_address(capsys):
    from connectonion.cli.commands import proxy_commands

    code = proxy_commands.handle_proxy(["diagnose", "notanaddress"])

    text = capsys.readouterr().err
    assert code == 2
    assert "notanaddress" in text and "0x" in text
