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


# ── An answer names the request it answers ─────────────────────────────────
#
# Reproduced in review against 1.8.8b5: the laptop approved request #1 while
# the phone still showed it; the phone's "approve" then landed on request #2,
# a command nobody had seen:
#
#     agent saw: [('read_file', True), ('bash rm -rf', True)]
#
# The Host handed the next answer to whatever was waiting. One device could
# never answer twice, so before the fan-out that never mattered.


def _two_approvals(decisions):
    """A hosted agent that asks for two approvals, one after the other."""

    def ws_input(storage, prompt, io, session, images, files, requester_address=None):
        for tool in ("read_file", "bash rm -rf"):
            decisions.append((tool, io.request_approval(tool, {})))
        return {"result": "done", "duration_ms": 1,
                "session": {"session_id": SESSION, "turn": 1}}

    return ws_input


async def _run_agent(devices, script, monkeypatch, ws_input):
    async def connect(data, send_msg, conn, *args, **kwargs):
        _connect_as_self(data, send_msg, conn)
        return None

    monkeypatch.setattr(ws_session, "handle_connect", connect)
    registry = ActiveSessionRegistry()
    route_handlers = {"ws_input": ws_input, "viewers": SessionViewers()}
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
        for d in devices:
            d.inbox.put_nowait(None)
        await asyncio.wait_for(asyncio.gather(*loops), 5)


async def _nth(device, frame_type, n, timeout=5):
    async def seen():
        while len([f for f in device.sent if f["type"] == frame_type]) < n:
            await asyncio.sleep(0.01)
    await asyncio.wait_for(seen(), timeout)
    return [f for f in device.sent if f["type"] == frame_type][n - 1]


def _stale_answer_is_dropped(monkeypatch, stale_answer):
    laptop, phone = Device(), Device()
    decisions = []

    async def script():
        for d in (laptop, phone):
            await d.inbox.put({"type": "CONNECT", "as": d.address})
        await asyncio.sleep(0.05)
        await laptop.inbox.put({"type": "INPUT", "prompt": "tidy up"})
        first = await _nth(phone, "approval_needed", 1)
        await laptop.inbox.put({
            "type": "APPROVAL_RESPONSE", "request_id": first["id"],
            "approved": True, "scope": "once",
        })
        second = await _nth(phone, "approval_needed", 2)
        assert second["id"] != first["id"]
        # The phone still shows #1 and approves it.
        await phone.inbox.put(stale_answer(first))
        await _nth(phone, "ERROR", 1)
        # The laptop, which can see #2, refuses it.
        await laptop.inbox.put({
            "type": "APPROVAL_RESPONSE", "request_id": second["id"],
            "approved": False, "mode": "reject_soft",
        })
        await laptop.wait_for("OUTPUT")

    asyncio.run(_run_agent([laptop, phone], script, monkeypatch, _two_approvals(decisions)))

    assert decisions == [("read_file", True), ("bash rm -rf", False)]
    stale = [f for f in phone.sent if f["type"] == "ERROR"][0]
    assert stale["code"] == "STALE_ANSWER"


def test_an_approval_naming_an_answered_request_is_not_applied_to_the_next(monkeypatch):
    _stale_answer_is_dropped(monkeypatch, lambda first: {
        "type": "APPROVAL_RESPONSE", "request_id": first["id"],
        "approved": True, "scope": "once",
    })


def test_an_approval_naming_nothing_is_refused_while_two_devices_can_answer(monkeypatch):
    """What the shipped React client sends today: no id at all."""
    _stale_answer_is_dropped(monkeypatch, lambda first: {
        "type": "APPROVAL_RESPONSE", "approved": True, "scope": "once",
    })


def test_one_device_may_still_answer_without_naming_the_request(monkeypatch):
    """A single client that predates `request_id` keeps working: with nobody
    else able to answer, there is no other answer its reply could be."""
    laptop = Device()
    decisions = []

    async def script():
        await laptop.inbox.put({"type": "CONNECT", "as": laptop.address})
        await asyncio.sleep(0.05)
        await laptop.inbox.put({"type": "INPUT", "prompt": "tidy up"})
        await _nth(laptop, "approval_needed", 1)
        await laptop.inbox.put({"type": "APPROVAL_RESPONSE", "approved": True})
        await _nth(laptop, "approval_needed", 2)
        await laptop.inbox.put({"type": "APPROVAL_RESPONSE", "approved": False})
        await laptop.wait_for("OUTPUT")

    asyncio.run(_run_agent([laptop], script, monkeypatch, _two_approvals(decisions)))

    assert decisions == [("read_file", True), ("bash rm -rf", False)]


def test_a_stale_answer_to_a_question_is_not_the_answer_to_the_next(monkeypatch):
    laptop, phone = Device(), Device()
    answers = []

    def ws_input(storage, prompt, io, session, images, files, requester_address=None):
        for question in ("which branch?", "delete it?"):
            io.send({"type": "ask_user", "question": question, "options": []})
            answers.append((question, io.receive().get("answer")))
        return {"result": "done", "duration_ms": 1,
                "session": {"session_id": SESSION, "turn": 1}}

    async def script():
        for d in (laptop, phone):
            await d.inbox.put({"type": "CONNECT", "as": d.address})
        await asyncio.sleep(0.05)
        await laptop.inbox.put({"type": "INPUT", "prompt": "clean"})
        first = await _nth(phone, "ask_user", 1)
        await laptop.inbox.put({"type": "ASK_USER_RESPONSE", "request_id": first["id"], "answer": "main"})
        second = await _nth(phone, "ask_user", 2)
        await phone.inbox.put({"type": "ASK_USER_RESPONSE", "request_id": first["id"], "answer": "yes"})
        await _nth(phone, "ERROR", 1)
        await laptop.inbox.put({"type": "ASK_USER_RESPONSE", "request_id": second["id"], "answer": "no"})
        await laptop.wait_for("OUTPUT")

    asyncio.run(_run_agent([laptop, phone], script, monkeypatch, ws_input))

    assert answers == [("which branch?", "main"), ("delete it?", "no")]


# ── A connection that ran a normal turn can still drive a Work Room turn ────
#
# Reported by a reviewer: fan_out_turn hands every viewer the turn's io,
# including the connection that started it, and the read loop re-adopted that
# io on every frame. Once a normal turn had run, a Work Room turn this same
# connection started later was swapped for the finished turn's io on the next
# frame, so Stop, steer and approvals all went to a turn that was over.


def test_a_work_room_turn_after_a_normal_turn_can_still_be_stopped(monkeypatch):
    laptop = Device()
    release = threading.Event()
    stopped = threading.Event()

    def run(io):
        io.send({"type": "provider_invocation", "invocationId": "codex:1",
                 "provider": "codex", "status": "running", "stateRevision": 1})
        for _ in range(50):
            if io.take_provider_interrupt("codex:1"):
                stopped.set()
                return
            release.wait(0.1)

    def prepare(storage, session_id, invocation_id, text, request_id, address):
        return {"run": run, "stateRevision": 1}

    async def connect(data, send_msg, conn, *args, **kwargs):
        _connect_as_self(data, send_msg, conn)
        return None

    monkeypatch.setattr(ws_session, "handle_connect", connect)
    route_handlers = {
        "ws_input": _agent(release),
        "viewers": SessionViewers(),
        "prepare_provider_workroom_turn": prepare,
    }

    async def script():
        loop = asyncio.create_task(ws_session.run_ws_session(
            laptop.send_msg, laptop.recv_msg, route_handlers=route_handlers,
            storage=None, registry=ActiveSessionRegistry(), trust=None,
            enable_ping=False,
        ))
        await laptop.inbox.put({"type": "CONNECT", "as": laptop.address})
        await laptop.inbox.put({"type": "INPUT", "prompt": "hello"})
        release.set()
        await laptop.wait_for("OUTPUT")
        release.clear()
        await laptop.inbox.put({"type": "PROVIDER_INPUT", "invocationId": "codex:1",
                                "requestId": "r1", "stateRevision": 1, "text": "go"})
        await laptop.wait_for("provider_invocation")
        await laptop.inbox.put({"type": "PROVIDER_INTERRUPT", "invocationId": "codex:1",
                                "requestId": "r2", "stateRevision": 1})
        await laptop.wait_for("PROVIDER_INTERRUPT_ACK")
        release.set()
        laptop.inbox.put_nowait(None)
        await asyncio.wait_for(loop, 5)

    asyncio.run(script())

    ack = [f for f in laptop.sent if f["type"] == "PROVIDER_INTERRUPT_ACK"][0]
    assert ack["accepted"] is True, ack
    assert stopped.wait(2)
