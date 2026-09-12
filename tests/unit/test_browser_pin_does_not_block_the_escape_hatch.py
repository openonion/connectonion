"""A pinned daemon must never refuse the command it tells you to run.

#1510: the daemon pins its engine at startup, and every request carries the
engine the client resolved. Once pinned to the paid engine, a bare
`co browser <verb>` resolves to `auto` and is refused — including `tab ls`,
`status` and `close`, none of which drive or create a page. The printed remedy
was `co browser close`, which is refused by the same guard, so following the
instruction literally loops forever and the browser cannot be recovered at all.

Two properties are tested here:

  1. The verbs that neither drive nor create a page are answered whatever the
     pin says. Closing is the escape hatch; it cannot be behind the lock.
  2. Every command the refusal names would itself be admitted. A remedy that
     the guard rejects is worse than no remedy: it sends the reader in a circle
     with the confidence of an instruction.
"""

import json
import re

import pytest

from connectonion.cli.browser_agent.daemon import BrowserDaemon
from connectonion.useful_tools.browser_tools._async_browser import AsyncBrowserCore


def envelope(line: str, *, engine: str, caller: str = "agent", tab=None) -> str:
    return json.dumps(
        {
            "v": 1,
            "caller": caller,
            "account": "",
            "tab": tab,
            "line": line,
            "engine": engine,
        }
    )


@pytest.fixture
def pinned(tmp_path):
    """A daemon pinned to the paid engine, as the Airbnb session's was."""
    server = BrowserDaemon(
        str(tmp_path / "browser.sock"), headless=True, engine_mode="onion"
    )
    server.browser = AsyncBrowserCore(headless=True)
    return server


@pytest.fixture
def live(pinned):
    """The same daemon with its paid browser still open."""

    async def alive():
        return True

    pinned.browser.is_alive = alive
    return pinned


def _refusal(payload) -> bool:
    return isinstance(payload, str) and "pinned to engine" in payload


@pytest.mark.asyncio
@pytest.mark.parametrize("line", ["close", "status", "tab ls", "tab close probe"])
async def test_a_pin_never_blocks_a_verb_that_touches_no_page(pinned, line):
    ok, payload = await pinned.dispatch_async(envelope(line, engine="auto"))

    assert not _refusal(payload), f"`{line}` must be answered whatever the pin says"


@pytest.mark.asyncio
@pytest.mark.parametrize("line", ["go_to example.com", "get_text", "tab open probe"])
async def test_a_bare_command_rides_a_paid_session_that_is_already_open(live, line):
    """`auto` is no preference, not a conflicting one (#1501).

    The session is up and already paid for; another tab in it charges nothing.
    Refusing here is what made every bare command fail against a daemon someone
    had once started with --engine wtf.
    """
    ok, payload = await live.dispatch_async(envelope(line, engine="auto"))

    assert not _refusal(payload), f"`{line}` costs nothing extra and must be served"


@pytest.mark.asyncio
@pytest.mark.parametrize("line", ["go_to example.com", "tab open probe"])
async def test_a_bare_command_may_not_restart_a_paid_session_that_ended(pinned, line):
    """The one case where `auto` still has to ask: it would begin a new charge."""
    ok, payload = await pinned.dispatch_async(envelope(line, engine="auto"))

    assert _refusal(payload)
    assert "bills" in payload, "say why the answer is no, not just that it is"


@pytest.mark.asyncio
async def test_a_different_named_engine_is_a_real_conflict(live):
    ok, payload = await live.dispatch_async(envelope("get_text", engine="system"))

    assert _refusal(payload), "asking for system on a paid daemon is a real conflict"


@pytest.mark.asyncio
async def test_the_refusal_names_the_engine_a_person_types(live):
    ok, payload = await live.dispatch_async(envelope("get_text", engine="system"))

    assert "wtf" in payload, "`onion` is the wire name; nobody types it"


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture,engine", [("pinned", "auto"), ("live", "system")])
async def test_every_command_a_refusal_names_would_itself_be_admitted(
    request, fixture, engine
):
    """The defect that made #1510 unrecoverable, stated as a property.

    Both refusals are checked: the pin mismatch, and the paid relaunch.
    """
    daemon = request.getfixturevalue(fixture)
    ok, payload = await daemon.dispatch_async(envelope("get_text", engine=engine))
    assert _refusal(payload)

    suggested = re.findall(r"co browser ([^\n]+)", payload)
    assert suggested, "a refusal with no way out is not a refusal, it is a dead end"

    for command in suggested:
        if command.startswith("config"):
            continue  # answered by the CLI before the daemon is contacted
        named = re.search(r"--engine (\S+)", command)
        wire = {"wtf": "onion"}.get(named.group(1), named.group(1)) if named else "auto"
        line = re.sub(r"--engine \S+", "", command).replace("<verb> ...", "get_text")
        ok, reply = await daemon.dispatch_async(
            envelope(" ".join(line.split()), engine=wire)
        )
        assert not _refusal(reply), (
            f"the refusal tells you to run `co browser {command}`, then refuses it"
        )


@pytest.mark.asyncio
async def test_a_matching_request_is_untouched(pinned):
    """The guard's real job — a request on the pinned engine — still passes."""
    ok, payload = await pinned.dispatch_async(envelope("status", engine="onion"))

    assert not _refusal(payload)
