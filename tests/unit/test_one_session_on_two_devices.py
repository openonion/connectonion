"""One conversation open on a laptop and a phone at the same time (#1606).

A session used to be a connection. The turn's output went to whichever socket
sent the INPUT and nowhere else, so a second device that had the conversation
open watched nothing happen until it reloaded — and through the relay it was
refused outright. These drive two real connection loops against one Host
registry, stubbing only the signature check in CONNECT.
"""

import asyncio
import threading

from connectonion.network.host.session import ActiveSessionRegistry, SessionViewers
from connectonion.network.host.ws_router import session as ws_session

SESSION = "session-1"
OWNER = "0xowner"


class Device:
    """One socket: frames it will send, frames it received."""

    def __init__(self, address=OWNER):
        self.address = address
        self.inbox = asyncio.Queue()
        self.sent = []

    async def send_msg(self, data):
        self.sent.append(dict(data))

    async def recv_msg(self):
        return await self.inbox.get()

    def types(self):
        return [frame["type"] for frame in self.sent]

    async def wait_for(self, frame_type, timeout=5):
        async def seen():
            while frame_type not in self.types():
                await asyncio.sleep(0.01)
        await asyncio.wait_for(seen(), timeout)


def _connect_as_self(data, send_msg, conn, *args, **kwargs):
    """The real CONNECT verifies a signature; the address travels in the stub frame."""
    conn.update({
        "authenticated": True,
        "agent_address": data["as"],
        "session_id": SESSION,
        "session": {},
    })


def _agent(release):
    """A hosted agent that streams two events, then waits to be let go."""

    def ws_input(storage, prompt, io, session, images, files, requester_address=None):
        io.send({"type": "thinking", "content": f"reading: {prompt}"})
        io.send({"type": "tool_call", "name": "search", "id": "t1"})
        release.wait(5)
        return {"result": f"answer to {prompt}", "duration_ms": 1,
                "session": {"session_id": SESSION, "turn": 1}}

    return ws_input


async def _run(devices, script, monkeypatch, release):
    async def connect(data, send_msg, conn, *args, **kwargs):
        _connect_as_self(data, send_msg, conn)
        return None

    monkeypatch.setattr(ws_session, "handle_connect", connect)
    registry = ActiveSessionRegistry()
    route_handlers = {"ws_input": _agent(release), "viewers": SessionViewers()}
    loops = [
        asyncio.create_task(ws_session.run_ws_session(
            d.send_msg, d.recv_msg, route_handlers=route_handlers, storage=None,
            registry=registry, trust=None, enable_ping=False,
        ))
        for d in devices
    ]
    try:
        await script()
    finally:
        release.set()
        for d in devices:
            d.inbox.put_nowait(None)
        await asyncio.wait_for(asyncio.gather(*loops), 5)


def test_a_turn_started_on_the_laptop_streams_to_the_phone(monkeypatch):
    laptop, phone = Device(), Device()
    release = threading.Event()

    async def script():
        for d in (laptop, phone):
            await d.inbox.put({"type": "CONNECT", "as": d.address})
        await asyncio.sleep(0.05)
        await laptop.inbox.put({"type": "INPUT", "prompt": "find flights"})
        await phone.wait_for("tool_call")
        release.set()
        await phone.wait_for("OUTPUT")
        await laptop.wait_for("OUTPUT")

    asyncio.run(_run([laptop, phone], script, monkeypatch, release))

    # The phone sees the question it did not type, then the same turn.
    assert phone.sent[0] == {"type": "user_message", "content": "find flights", "session_id": SESSION}
    assert phone.types()[1:4] == ["thinking", "tool_call", "OUTPUT"]
    assert [f for f in phone.sent if f["type"] == "OUTPUT"][0]["result"] == "answer to find flights"
    # The laptop typed it, so it is not echoed back; it gets the turn once.
    assert "user_message" not in laptop.types()
    assert laptop.types().count("tool_call") == 1
    assert laptop.types().count("OUTPUT") == 1


def test_a_different_identity_naming_the_session_sees_nothing(monkeypatch):
    """#696's rule, held again at the fan-out: owner only, whatever the id says."""
    laptop, stranger = Device(), Device(address="0xstranger")
    release = threading.Event()

    async def script():
        for d in (laptop, stranger):
            await d.inbox.put({"type": "CONNECT", "as": d.address})
        await asyncio.sleep(0.05)
        await laptop.inbox.put({"type": "INPUT", "prompt": "private"})
        await laptop.wait_for("tool_call")
        release.set()
        await laptop.wait_for("OUTPUT")
        await asyncio.sleep(0.1)

    asyncio.run(_run([laptop, stranger], script, monkeypatch, release))

    assert stranger.sent == []


def test_the_phone_can_stop_a_turn_the_laptop_started(monkeypatch):
    laptop, phone = Device(), Device()
    release = threading.Event()

    async def script():
        for d in (laptop, phone):
            await d.inbox.put({"type": "CONNECT", "as": d.address})
        await asyncio.sleep(0.05)
        await laptop.inbox.put({"type": "INPUT", "prompt": "long job"})
        await phone.wait_for("tool_call")
        await phone.inbox.put({"type": "INTERRUPT"})
        await asyncio.sleep(0.1)

    asyncio.run(_run([laptop, phone], script, monkeypatch, release))

    refused = [f for f in phone.sent if f["type"] == "ERROR"]
    assert refused == [], refused


def test_a_device_that_closes_stops_being_sent_the_turn(monkeypatch):
    laptop, phone = Device(), Device()
    release = threading.Event()

    async def script():
        for d in (laptop, phone):
            await d.inbox.put({"type": "CONNECT", "as": d.address})
        await asyncio.sleep(0.05)
        await phone.inbox.put(None)          # the phone goes away
        await asyncio.sleep(0.05)
        await laptop.inbox.put({"type": "INPUT", "prompt": "still here?"})
        await laptop.wait_for("tool_call")
        release.set()
        await laptop.wait_for("OUTPUT")

    asyncio.run(_run([laptop, phone], script, monkeypatch, release))

    assert phone.sent == []
