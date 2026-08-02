"""A relay connection that ends gets closed.

From a deployed agent, twenty-five minutes and two disconnects after boot:

    ESTAB       0   0  …:58944  35.197.139.111:443  fd=6
    CLOSE-WAIT  25  0  …:52190  35.197.139.111:443  fd=8

CLOSE-WAIT means the relay sent FIN and this side never called close(). The
process is meant to run for weeks, and there is no symptom until the
descriptor limit — where the failure will look like something else entirely.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from connectonion.network import relay


class FakeWS:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


def test_a_clean_disconnect_closes_the_socket(monkeypatch):
    ws = FakeWS()
    monkeypatch.setattr(relay, "connect", AsyncMock(return_value=ws))
    monkeypatch.setattr(relay, "serve_loop", AsyncMock(return_value=None))

    asyncio.run(relay.serve_once("wss://example", lambda: {},
                                 addr_data=None, session_handler=None))

    assert ws.closed


def test_an_error_mid_serve_closes_the_socket(monkeypatch):
    """The other exit, and the one the supervisor retries on."""
    ws = FakeWS()
    monkeypatch.setattr(relay, "connect", AsyncMock(return_value=ws))
    monkeypatch.setattr(relay, "serve_loop",
                        AsyncMock(side_effect=OSError("network went away")))

    with pytest.raises(OSError):
        asyncio.run(relay.serve_once("wss://example", lambda: {},
                                     addr_data=None, session_handler=None))

    assert ws.closed, "a socket dropped by an exception leaks the same way"


def test_the_error_still_reaches_the_supervisor(monkeypatch):
    """Closing must not swallow the failure — the backoff depends on it."""
    monkeypatch.setattr(relay, "connect", AsyncMock(return_value=FakeWS()))
    monkeypatch.setattr(relay, "serve_loop",
                        AsyncMock(side_effect=OSError("boom")))

    with pytest.raises(OSError, match="boom"):
        asyncio.run(relay.serve_once("wss://example", lambda: {},
                                     addr_data=None, session_handler=None))


def test_a_failed_connect_is_not_a_close(monkeypatch):
    """Nothing was opened, so there is nothing to close and no AttributeError."""
    monkeypatch.setattr(relay, "connect",
                        AsyncMock(side_effect=OSError("dns")))

    with pytest.raises(OSError):
        asyncio.run(relay.serve_once("wss://example", lambda: {},
                                     addr_data=None, session_handler=None))


def test_a_close_that_itself_fails_does_not_mask_the_real_error(monkeypatch):
    """A socket already torn down can raise on close. The serve failure is
    the one worth reporting."""
    class BadWS(FakeWS):
        async def close(self):
            raise OSError("already gone")

    monkeypatch.setattr(relay, "connect", AsyncMock(return_value=BadWS()))
    monkeypatch.setattr(relay, "serve_loop",
                        AsyncMock(side_effect=RuntimeError("the real problem")))

    with pytest.raises(RuntimeError, match="the real problem"):
        asyncio.run(relay.serve_once("wss://example", lambda: {},
                                     addr_data=None, session_handler=None))


def test_the_supervisor_goes_through_serve_once(monkeypatch):
    """The fix only helps if host()'s loop actually calls it."""
    import inspect
    from connectonion.network.host import server

    src = inspect.getsource(server)
    body = src[src.index("async def relay_loop"):
               src.index("relay_task = asyncio.create_task")]

    assert "serve_once" in body
