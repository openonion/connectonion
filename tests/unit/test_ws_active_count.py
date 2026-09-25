"""The host log's `(N active)` counts open sockets, and goes down when they close.

It printed the session registry's size, which is not sockets: a finished
session stays registered for ten minutes after its socket closes so a client
can reattach. A tester closed every socket and watched the count climb to 8
and stay there -- a log that says eight clients are connected when none are
sends the operator looking for a leak that is not there.
"""

import asyncio
import io
import re
from unittest.mock import Mock

import pytest
from rich.console import Console

from connectonion.network.asgi import websocket as ws
from connectonion.network.host.session import ActiveSessionRegistry


@pytest.fixture
def log(monkeypatch):
    out = io.StringIO()
    monkeypatch.setattr(ws, "console", Console(file=out, force_terminal=False, width=200))
    return out


def counts(text):
    return [int(n) for n in re.findall(r"\((\d+) active\)", text)]


async def open_socket(registry, closed, first_frame=None):
    """One client: accepted, sends ``first_frame`` if given, then waits until
    ``closed`` is set and disconnects. A socket that says nothing is the common
    real case -- a probe, a client that gave up -- and it took the early return
    that never printed `ws-` at all."""
    pending = [first_frame] if first_frame else []

    async def receive():
        if pending:
            return {"type": "websocket.receive", "text": pending.pop()}
        await closed.wait()
        return {"type": "websocket.disconnect"}

    async def send(msg):
        pass

    await ws.handle_websocket({"path": "/ws", "type": "websocket", "client": ("127.0.0.1", 1)},
                              receive, send, route_handlers={}, storage=Mock(),
                              registry=registry, trust="open")


def test_the_count_returns_to_zero_when_every_socket_closes(log):
    registry = ActiveSessionRegistry()
    # A session left registered by an earlier run, as on a real host.
    registry.register("earlier", Mock(), Mock())

    async def scenario():
        closed = asyncio.Event()
        clients = [asyncio.create_task(open_socket(registry, closed)) for _ in range(3)]
        await asyncio.sleep(0.05)
        closed.set()
        await asyncio.gather(*clients)

    asyncio.run(scenario())

    seen = counts(log.getvalue())
    assert seen[:3] == [1, 2, 3], log.getvalue()
    assert seen[-1] == 0, log.getvalue()


def test_a_session_that_raises_still_closes_its_count(log, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("session failed")

    monkeypatch.setattr(ws, "run_ws_session", boom)

    async def scenario():
        closed = asyncio.Event()
        closed.set()
        with pytest.raises(RuntimeError):
            await open_socket(ActiveSessionRegistry(), closed, '{"type": "CONNECT"}')

    asyncio.run(scenario())

    assert counts(log.getvalue()) == [1, 0], log.getvalue()
