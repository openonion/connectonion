"""Revoking access must affect a socket that has already passed CONNECT."""

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from connectonion import address
from connectonion.cli.commands.trust_commands import handle_trust_block, handle_trust_remove
from connectonion.network.connect import RemoteAgent
from connectonion.network.host.auth import extract_and_authenticate
from connectonion.network.host.session import ActiveSessionRegistry, SessionStorage
from connectonion.network.host.ws_router import dashboard, run_ws_session
from connectonion.network.trust import TrustAgent

REVOKED = "Your access to this agent was revoked by its admin."
HOST = "0x" + "a1" * 32


class Socket:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()
        self.sent = []

    async def send(self, frame):
        self.sent.append(frame)
        await self.outgoing.put(frame)

    async def receive(self):
        return await self.incoming.get()

    async def until(self, frame_type):
        async def find():
            while True:
                frame = await self.outgoing.get()
                if frame["type"] == frame_type:
                    return frame
        return await asyncio.wait_for(find(), 3)


@pytest.fixture
def host(tmp_path, monkeypatch):
    co_dir = tmp_path / ".co"
    co_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    # Home rendering is unrelated; keep the real signature and trust gates.
    monkeypatch.setattr(
        dashboard, "send_dashboard", AsyncMock()
    )
    keys = address.generate()
    client = RemoteAgent(HOST, keys=keys)
    trust = TrustAgent("careful", co_dir=co_dir)
    trust.promote_to_contact(keys["address"])
    return client, trust, SessionStorage(co_dir / "sessions.jsonl")


def connect_frame(client, signed_commands):
    frame = client._build_connect_message(is_direct=True)
    if not signed_commands:
        frame["payload"].pop("signed_commands")
        canonical = json.dumps(frame["payload"], sort_keys=True, separators=(",", ":"))
        frame["signature"] = address.sign(client._keys, canonical.encode()).hex()
    return frame


@asynccontextmanager
async def connected_socket(host, ws_input, signed_commands=True, registry=None):
    client, trust, storage = host
    socket = Socket()
    registry = registry or ActiveSessionRegistry()
    task = asyncio.create_task(run_ws_session(
        socket.send, socket.receive,
        route_handlers={"trust_agent": trust, "ws_input": ws_input,
                        "auth": extract_and_authenticate, "replay": lambda frame: False},
        storage=storage, registry=registry, trust=trust, enable_ping=False,
    ))
    try:
        await socket.incoming.put(connect_frame(client, signed_commands))
        await socket.until("CONNECTED")
        yield socket, registry, task
    finally:
        for sid in registry.list_active():
            registry.get(sid).io.request_interrupt()
        await socket.incoming.put(None)
        await asyncio.wait_for(task, 3)
        for sid in registry.list_active():
            registry.get(sid).thread.join(3)


@pytest.mark.asyncio
@pytest.mark.parametrize("signed_commands", [False, True])
@pytest.mark.parametrize("revoke", [handle_trust_block, handle_trust_remove])
async def test_revoked_contact_cannot_start_another_turn(host, signed_commands, revoke):
    client, trust, _ = host
    ran = []

    def ws_input(storage, prompt, io, session, images, files, requester_address=None):
        ran.append(prompt)
        return {"result": "done", "session": session, "duration_ms": 1}

    async with connected_socket(host, ws_input, signed_commands) as (socket, _, task):
        before = {"type": "INPUT", "prompt": "before"}
        after = {"type": "INPUT", "prompt": "after"}
        if signed_commands:
            before = client._build_command_message(before)
            after = client._build_command_message(after)
        await socket.incoming.put(before)
        await socket.until("OUTPUT")
        revoke(client._keys["address"])
        assert trust.get_level(client._keys["address"]) in {"stranger", "blocked"}
        await socket.incoming.put(after)
        # Old code emits OUTPUT and runs 'after'; fixed code refuses and exits.
        frame = await asyncio.wait_for(socket.outgoing.get(), 3)
        assert frame == {"type": "ERROR", "code": "ACCESS_REVOKED", "message": REVOKED}
        await asyncio.wait_for(task, 3)
        assert ran == ["before"]


@pytest.mark.asyncio
@pytest.mark.parametrize("revoke", [handle_trust_block, handle_trust_remove])
@pytest.mark.parametrize("frame_type", ["INPUT", "APPROVAL_RESPONSE", "ASK_USER_RESPONSE"])
async def test_revoked_requester_cannot_feed_a_running_turn(host, revoke, frame_type):
    client, _, _ = host
    received = []

    def ws_input(storage, prompt, io, session, images, files, requester_address=None):
        event_type = "ask_user" if frame_type == "ASK_USER_RESPONSE" else "approval_needed"
        io.send({"type": event_type, "tool": "shell", "question": "continue?"})
        received.append(io.receive())
        return {"result": "stopped", "session": session, "duration_ms": 1}

    async with connected_socket(host, ws_input) as (socket, registry, task):
        await socket.incoming.put(client._build_input_message("wait", "one"))
        event_type = "ask_user" if frame_type == "ASK_USER_RESPONSE" else "approval_needed"
        request = await socket.until(event_type)
        active = registry.get(request["session_id"])
        revoke(client._keys["address"])
        command = {"type": frame_type, "prompt": "after", "approved": True,
                   "answer": "yes", "request_id": request["id"]}
        await socket.incoming.put(client._build_command_message(command))
        frame = await asyncio.wait_for(socket.outgoing.get(), 3)
        assert frame == {"type": "ERROR", "code": "ACCESS_REVOKED", "message": REVOKED}
        await asyncio.wait_for(task, 3)
        await asyncio.to_thread(active.thread.join, 3)
        assert not active.thread.is_alive()
        assert received == [{"type": "INTERRUPT"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_level", ["stranger", "contact", "whitelist", "admin"])
async def test_default_allow_keeps_callers_until_their_access_is_revoked(host, initial_level):
    client, old_trust, storage = host
    caller = client._keys["address"]
    trust = TrustAgent("open", co_dir=old_trust._co_dir)
    trust.demote_to_stranger(caller)
    if initial_level == "contact":
        trust.promote_to_contact(caller)
    if initial_level == "whitelist":
        trust.promote_to_whitelist(caller)
    if initial_level == "admin":
        trust.promote_to_contact(caller)
        trust.add_admin(caller)
    ran = []

    def ws_input(storage, prompt, io, session, images, files, requester_address=None):
        ran.append(prompt)
        return {"result": "done", "session": session, "duration_ms": 1}

    async with connected_socket((client, trust, storage), ws_input) as (socket, _, task):
        for prompt in ("first", "second"):
            await socket.incoming.put(client._build_input_message(prompt, prompt))
            await socket.until("OUTPUT")
        # A default-allowed stranger is welcome until explicitly blocked.
        if initial_level == "stranger":
            handle_trust_block(caller)
        elif initial_level == "admin":
            trust.remove_admin(caller)
        else:
            handle_trust_remove(caller)
        await socket.incoming.put(client._build_input_message("after", "three"))
        frame = await socket.until("ERROR")
        assert frame["message"] == REVOKED
        await asyncio.wait_for(task, 3)
        assert ran == ["first", "second"]


@pytest.mark.asyncio
async def test_revocation_closes_the_direct_websocket(host):
    from connectonion.network.asgi.websocket import handle_websocket

    client, trust, storage = host
    socket = Socket()
    native_sent = []

    async def send(event):
        native_sent.append(event)
        if event["type"] == "websocket.send":
            await socket.send(json.loads(event["text"]))

    async def receive():
        frame = await socket.receive()
        return {"type": "websocket.receive", "text": json.dumps(frame)}

    task = asyncio.create_task(handle_websocket(
        {"path": "/ws"}, receive, send,
        route_handlers={"trust_agent": trust, "replay": lambda frame: False},
        storage=storage, registry=ActiveSessionRegistry(), trust=trust,
    ))
    try:
        await socket.incoming.put(connect_frame(client, True))
        await socket.until("CONNECTED")
        handle_trust_block(client._keys["address"])
        await socket.incoming.put(client._build_input_message("revoked", "one"))
        assert (await socket.until("ERROR"))["message"] == REVOKED
        await asyncio.wait_for(task, 3)
        assert native_sent[-1] == {"type": "websocket.close", "code": 1008}
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_strict_whitelist_demotion_revokes_even_if_contact_remains(host):
    client, old_trust, storage = host
    trust = TrustAgent("strict", co_dir=old_trust._co_dir)
    trust.promote_to_whitelist(client._keys["address"])
    def ws_input(storage, prompt, io, session, images, files, requester_address=None):
        return {"result": "should not run", "session": session, "duration_ms": 1}

    async with connected_socket((client, trust, storage), ws_input) as (socket, _, task):
        trust.demote_to_contact(client._keys["address"])
        assert not trust.should_allow(client._keys["address"]).allow
        await socket.incoming.put(client._build_input_message("after", "one"))
        assert (await socket.until("ERROR"))["message"] == REVOKED
        await asyncio.wait_for(task, 3)


@pytest.mark.asyncio
async def test_revocation_stops_all_requester_turns_but_leaves_other_callers_alone(host):
    client, trust, storage = host
    other_keys = address.generate()
    other_client = RemoteAgent(HOST, keys=other_keys)
    trust.promote_to_contact(other_keys["address"])
    registry = ActiveSessionRegistry()
    received = {}

    def ws_input(storage, prompt, io, session, images, files, requester_address=None):
        io.send({"type": "thinking", "content": prompt})
        received[prompt] = io.receive()
        return {"result": "stopped", "session": session, "duration_ms": 1}

    async with connected_socket(host, ws_input, registry=registry) as first:
        async with connected_socket(host, ws_input, registry=registry) as second:
            async with connected_socket((other_client, trust, storage), ws_input,
                                        registry=registry) as other:
                running = []
                for (socket, _, _), caller, prompt in (
                    (first, client, "first"), (second, client, "second"),
                    (other, other_client, "other"),
                ):
                    await socket.incoming.put(caller._build_input_message(prompt, prompt))
                    frame = await socket.until("thinking")
                    running.append(registry.get(frame["session_id"]))
                handle_trust_remove(client._keys["address"])
                await first[0].incoming.put(client._build_input_message("revoked", "four"))
                assert (await first[0].until("ERROR"))["message"] == REVOKED
                await asyncio.wait_for(first[2], 3)
                for active in running[:2]:
                    await asyncio.to_thread(active.thread.join, 3)
                    assert not active.thread.is_alive()
                assert received == {"first": {"type": "INTERRUPT"},
                                    "second": {"type": "INTERRUPT"}}
                assert running[2].thread.is_alive()


@pytest.mark.asyncio
async def test_relay_revocation_discards_the_authenticated_logical_session(host):
    from functools import partial
    from connectonion.network.relay import _run_session

    client, trust, storage = host
    socket = Socket()
    relay_frames = []

    class Relay:
        async def send(self, raw):
            frame = json.loads(raw)
            relay_frames.append(frame)
            await socket.send(frame)

    handler = partial(
        run_ws_session, route_handlers={"trust_agent": trust, "replay": lambda frame: False},
        storage=storage, registry=ActiveSessionRegistry(), trust=trust, enable_ping=False,
    )
    sessions = {"route": asyncio.Queue()}
    connect = {**connect_frame(client, True), "session_id": "chat", "conn_id": "browser"}
    task = asyncio.create_task(_run_session("route", connect, sessions, Relay(), handler))
    try:
        await socket.until("CONNECTED")
        handle_trust_block(client._keys["address"])
        command = {**client._build_input_message("after", "one"),
                   "session_id": "chat", "conn_id": "browser"}
        await sessions["route"].put(command)
        assert (await socket.until("ERROR"))["message"] == REVOKED
        await asyncio.wait_for(task, 3)
        assert sessions == {}
        assert relay_frames[-1]["conn_id"] == "browser"
        # A later frame is routed to a fresh loop with no authenticated caller.
        sessions["route"] = asyncio.Queue()
        task = asyncio.create_task(_run_session("route", command, sessions, Relay(), handler))
        assert (await socket.until("ERROR"))["message"] == "authenticate first (send CONNECT)"
    finally:
        if "route" in sessions:
            await sessions["route"].put(None)
        await asyncio.wait_for(task, 3)


@pytest.mark.asyncio
async def test_block_waits_for_requesters_next_frame_before_stopping_running_turn(host):
    client, _, _ = host
    received = []

    def ws_input(storage, prompt, io, session, images, files, requester_address=None):
        io.send({"type": "waiting"})
        received.append(io.receive())
        return {"result": "stopped", "session": session, "duration_ms": 1}

    async with connected_socket(host, ws_input) as (socket, registry, task):
        await socket.incoming.put(client._build_input_message("wait", "one"))
        waiting = await socket.until("waiting")
        active = registry.get(waiting["session_id"])
        handle_trust_block(client._keys["address"])
        # Let the reader run: editing a file alone does not wake recv_msg.
        await asyncio.sleep(0)
        assert not task.done()
        assert active.thread.is_alive()
        assert received == []
        # Any next frame triggers revocation, even a heartbeat.
        await socket.incoming.put(client._build_command_message({"type": "PING"}))
        assert (await socket.until("ERROR"))["code"] == "ACCESS_REVOKED"
        await asyncio.wait_for(task, 3)
        await asyncio.to_thread(active.thread.join, 3)
        assert not active.thread.is_alive()
        assert received == [{"type": "INTERRUPT"}]
