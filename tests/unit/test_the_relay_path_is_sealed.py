"""The relay path is sealed the same way a direct socket is, and a sealed
socket does not need the replay ledger.

1.8.0 sealed direct sockets (#1393) and left the relay path bare: TLS to a
relay that terminates it, plaintext to the relay, and a signed CONNECT that a
relay could capture and replay inside its five-minute window. The only thing
standing in the way of that replay was `.co/replay.sqlite3`, a shared file the
host cannot recreate at runtime. On 2026-09-03 a deploy's `rsync --delete`
removed it, the deploy helper died before restarting the service, and the
Melbourne rental host refused every signed request for 2h44m (#1402, #1403).

Two changes, one consequence. The client offers SEAL on the relay socket too;
the host seals a relay session with the same handshake. Inside a seal nobody
but the sealed peer can produce a frame, so once the CONNECT is bound to the
peer that opened the seal, the ledger has nothing left to protect and is not
consulted. A `co host` process runs one worker, so the ledger it keeps for
unsealed 1.7 clients lives in memory; the SQLite file is for `create_app()`
deployments that fork workers, and it now heals if the file goes away.
"""

import asyncio
import json
from functools import partial
from unittest.mock import Mock

import pytest

from connectonion import address
from connectonion.network import sealed
from connectonion.network.connect import RemoteAgent

RELAY = "wss://relay.test"


def _pair():
    return address.generate(), address.generate()


@pytest.fixture
def create_mock_agent():
    from connectonion import Agent
    from connectonion.core.llm import LLMResponse
    from connectonion.core.usage import TokenUsage

    llm = Mock()
    llm.model = "test-model"
    llm.complete.return_value = LLMResponse(content="ok", tool_calls=[], raw_response=None, usage=TokenUsage())

    def factory():
        return Agent("test_agent", llm=llm, quiet=True)
    return factory


class _SealingRelayHost:
    """The far end of a relay socket: a host that seals, seen through the proxy.

    The relay adds `session_id` to every client frame it forwards and to every
    host frame it returns; the stand-in does the same so the frames on the
    wire have the shape a real relay produces.
    """

    def __init__(self, host_identity, reply_to_connect, *, seals=True):
        self.host = host_identity
        self.reply_to_connect = reply_to_connect
        self.seals = seals
        self.channel = None
        self.inbox = []
        self.seen_clear = []
        self.raw = []
        self.closed = False

    async def send(self, raw):
        frame = json.loads(raw)
        frame["session_id"] = "relay-1"
        self.raw.append(frame)
        if frame.get("type") == "SEAL":
            if not self.seals:
                self.inbox.append(json.dumps({"type": "ERROR", "message": "unknown message type: 'SEAL'", "session_id": "relay-1"}))
                return
            reply, self.channel = sealed.host_accept(frame, self.host)
            reply["session_id"] = "relay-1"
            self.inbox.append(json.dumps(reply))
            return
        if self.channel is None:
            self.seen_clear.append(frame)
            if frame["type"] == "CONNECT":
                self.inbox.append(json.dumps({**self.reply_to_connect, "session_id": "relay-1"}))
            return
        clear = self.channel.open(frame)
        self.seen_clear.append(clear)
        if clear["type"] == "CONNECT":
            out = self.channel.seal(self.reply_to_connect)
            out["session_id"] = "relay-1"
            self.inbox.append(json.dumps(out))

    async def recv(self):
        return self.inbox.pop(0)

    async def close(self, *a, **k):
        self.closed = True

    def __await__(self):
        async def _self():
            return self
        return _self().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class TestTheClientSealsTheRelaySocket:

    def test_connect_travels_sealed_through_the_relay(self, monkeypatch):
        import websockets

        client, host = _pair()
        socket = _SealingRelayHost(host, {"type": "CONNECTED", "session_id": "relay-1"})
        monkeypatch.setattr(websockets, "connect", lambda *a, **k: socket)
        remote = RemoteAgent(host["address"], keys=client, relay_url=RELAY)
        remote._endpoint_resolved = True          # nothing direct to try

        async def run():
            connection, is_direct = await remote._open_best_connection(websockets)
            async with connection as ws:
                await ws.send(json.dumps(remote._build_connect_message(is_direct)))
                return is_direct, json.loads(await ws.recv())

        is_direct, answer = asyncio.run(run())
        assert is_direct is False
        assert answer["type"] == "CONNECTED"
        assert socket.raw[0]["type"] == "SEAL" and socket.raw[0]["to"] == host["address"]
        assert all(f["type"] == "SEALED" for f in socket.raw[1:]), [f["type"] for f in socket.raw]
        assert socket.seen_clear[0]["type"] == "CONNECT"

    def test_an_older_host_behind_the_relay_gets_a_fresh_bare_socket(self, monkeypatch):
        """A 1.8.0 host answers SEAL with an unknown-type ERROR. The relay
        link is TLS to the relay, which is what every client had before; the
        client keeps that, but on a fresh socket, not the one whose first
        frame the old host already consumed."""
        import websockets

        client, host = _pair()
        sockets = []

        def connect(url, *a, **k):
            socket = _SealingRelayHost(host, {"type": "CONNECTED", "session_id": "relay-1"}, seals=(False if not sockets else False))
            sockets.append(socket)
            return socket

        monkeypatch.setattr(websockets, "connect", connect)
        remote = RemoteAgent(host["address"], keys=client, relay_url=RELAY)
        remote._endpoint_resolved = True

        async def run():
            connection, is_direct = await remote._open_best_connection(websockets)
            async with connection as ws:
                await ws.send(json.dumps(remote._build_connect_message(is_direct)))
                return is_direct, json.loads(await ws.recv())

        is_direct, answer = asyncio.run(run())
        assert is_direct is False
        assert answer["type"] == "CONNECTED"
        assert len(sockets) == 2
        assert sockets[0].closed and [f["type"] for f in sockets[0].raw] == ["SEAL"]
        assert [f["type"] for f in sockets[1].raw] == ["CONNECT"]

    def test_the_relay_keepalive_passes_through_a_sealed_socket(self):
        """The relay PINGs the client in the clear every 30s; it holds no key.
        The PING carries nothing, so it is handed up as-is and the PONG goes
        back sealed like every other frame."""
        client, host = _pair()
        hello, eph = sealed.client_hello(client, host["address"])
        reply, host_channel = sealed.host_accept(hello, host)
        channel = sealed.client_finish(reply, hello, eph)

        class Wire:
            def __init__(self):
                self.sent = []
                self.inbox = [json.dumps({"type": "PING"})]

            async def send(self, raw):
                self.sent.append(json.loads(raw))

            async def recv(self):
                return self.inbox.pop(0)

        wire = Wire()
        socket = sealed.SealedSocket(wire, channel)

        async def run():
            ping = json.loads(await socket.recv())
            await socket.send(json.dumps({"type": "PONG"}))
            return ping

        assert asyncio.run(run()) == {"type": "PING"}
        assert wire.sent[0]["type"] == "SEALED"
        assert host_channel.open(wire.sent[0]) == {"type": "PONG"}


def _relay_host_session(first_frames, host_identity, connect_auth, *, replay=None, identity=True):
    """Run one relay session on the host through relay._run_session."""
    from connectonion.network import relay
    from connectonion.network.host.session import ActiveSessionRegistry
    from connectonion.network.host.ws_router import run_ws_session

    sent = []

    class RelayWs:
        async def send(self, raw):
            sent.append(json.loads(raw))

    handlers = {"connect_auth": connect_auth, "trust_agent": Mock(config={})}
    if replay is not None:
        handlers["replay"] = replay
    storage = Mock()
    storage.get.return_value = None
    runner = partial(run_ws_session, route_handlers=handlers, storage=storage,
                     registry=ActiveSessionRegistry(), trust="open", enable_ping=False,
                     transport="relay")

    async def run():
        sessions = {"relay-1": asyncio.Queue()}
        # _run_session queues the first frame itself; the rest follow it.
        task = asyncio.create_task(relay._run_session(
            "relay-1", first_frames[0], sessions, RelayWs(), runner,
            identity=host_identity if identity else None))
        await asyncio.sleep(0.01)
        queue = sessions.get("relay-1")
        if queue is not None:
            for frame in first_frames[1:]:
                await queue.put(frame)
            await queue.put({"type": "close", "session_id": "relay-1"})
        await task

    asyncio.run(run())
    return sent


class TestTheHostSealsARelaySession:

    def test_seal_is_answered_and_connect_travels_sealed(self):
        client, host = _pair()
        hello, eph = sealed.client_hello(client, host["address"])
        hello["session_id"] = "relay-1"
        holder = {}

        # The CONNECT is sealed with the channel the client only has after
        # SEALED_OK, so it is produced lazily by a frame that seals itself.
        class LazyConnect(dict):
            pass

        def connect_auth(data, *a, **k):
            holder["clear"] = data
            return ("hello", client["address"], True, None)

        from connectonion.network import relay
        from connectonion.network.host.session import ActiveSessionRegistry
        from connectonion.network.host.ws_router import run_ws_session

        sent = []
        queue = asyncio.Queue() if False else None

        class RelayWs:
            async def send(self, raw):
                frame = json.loads(raw)
                sent.append(frame)
                if frame["type"] == "SEALED_OK":
                    channel = sealed.client_finish(frame, hello, eph)
                    holder["channel"] = channel
                    connect = {"type": "CONNECT", "payload": {"timestamp": 1}, "from": client["address"], "signature": "00"}
                    out = channel.seal(connect)
                    out["session_id"] = "relay-1"
                    await holder["queue"].put(out)
                    await holder["queue"].put({"type": "close", "session_id": "relay-1"})

        handlers = {"connect_auth": connect_auth, "trust_agent": Mock(config={})}
        storage = Mock()
        storage.get.return_value = None
        runner = partial(run_ws_session, route_handlers=handlers, storage=storage,
                         registry=ActiveSessionRegistry(), trust="open", enable_ping=False,
                         transport="relay")

        async def run():
            sessions = {"relay-1": asyncio.Queue()}
            holder["queue"] = sessions["relay-1"]
            await relay._run_session("relay-1", hello, sessions, RelayWs(), runner, identity=host)

        asyncio.run(run())
        assert holder["clear"]["type"] == "CONNECT"
        assert sent[0]["type"] == "SEALED_OK" and sent[0]["session_id"] == "relay-1"
        assert all(f["type"] == "SEALED" and f["session_id"] == "relay-1" for f in sent[1:]), sent
        opened = [holder["channel"].open(f) for f in sent[1:]]
        assert "CONNECTED" in [f["type"] for f in opened]

    def test_a_bad_seal_ends_the_relay_session_without_a_connect(self):
        client, host = _pair()
        hello, _ = sealed.client_hello(client, address.generate()["address"])
        hello["session_id"] = "relay-1"
        sent = _relay_host_session([hello], host, lambda *a, **k: ("hello", client["address"], True, None))
        assert sent[0]["type"] == "ERROR" and "seal refused" in sent[0]["message"]
        assert "CONNECTED" not in [f["type"] for f in sent]

    def test_an_unsealed_relay_client_still_gets_through(self):
        client, host = _pair()
        connect = {"type": "CONNECT", "payload": {"timestamp": 1}, "from": client["address"], "signature": "00", "session_id": "relay-1"}
        sent = _relay_host_session([connect], host, lambda *a, **k: ("hello", client["address"], True, None))
        assert "CONNECTED" in [f["type"] for f in sent]


def _direct_host_session(receive_frames, host_identity, handlers, *, trust="open"):
    """Run the ASGI adapter; frames may be callables that seal themselves
    once the host's SEALED_OK is on the wire."""
    from connectonion.network.asgi import handle_websocket
    from connectonion.network.host.session import ActiveSessionRegistry

    sent = []
    inbox = list(receive_frames)

    async def receive():
        if inbox:
            item = inbox.pop(0)
            if callable(item):
                item = item(sent)
            return {"type": "websocket.receive", "text": json.dumps(item)}
        await asyncio.sleep(0.05)
        return {"type": "websocket.disconnect"}

    async def send(msg):
        sent.append(msg)

    storage = Mock()
    storage.get.return_value = None
    asyncio.run(handle_websocket(
        {"path": "/ws", "type": "websocket"}, receive, send,
        route_handlers={"identity": host_identity, "trust_agent": Mock(config={}), **handlers},
        storage=storage, registry=ActiveSessionRegistry(), trust=trust,
    ))
    return [json.loads(m["text"]) for m in sent if m["type"] == "websocket.send"]


def _sealed_connect(client, hello, eph, connect):
    def make(sent):
        reply = json.loads(sent[1]["text"])   # sent[0] is websocket.accept
        channel = sealed.client_finish(reply, hello, eph)
        make.channel = channel
        return channel.seal(connect)
    return make


class TestASealedSocketBindsTheConnectToThePeerWhoSealedIt:

    def test_a_connect_signed_by_someone_else_is_refused_inside_a_seal(self):
        """Without this, a stranger could open its own seal and feed a CONNECT
        captured from another identity into it — exactly the replay the
        ledger existed to stop, now inside a channel the stranger controls."""
        client, host = _pair()
        other = address.generate()
        hello, eph = sealed.client_hello(client, host["address"])
        captured = {"type": "CONNECT", "payload": {"timestamp": 1}, "from": other["address"], "signature": "00"}
        make = _sealed_connect(client, hello, eph, captured)
        wire = _direct_host_session([hello, make], host, {
            "connect_auth": lambda data, *a, **k: ("hello", data["from"], True, None),
        })
        opened = [make.channel.open(f) for f in wire[1:]]
        assert "CONNECTED" not in [f["type"] for f in opened]
        assert any(f["type"] == "ERROR" and "sealed peer" in f["message"] for f in opened), opened

    def test_an_onboard_submit_from_someone_else_is_refused_inside_a_seal(self):
        """Onboarding finishes the stashed CONNECT as the identity that
        onboarded. With the ledger out of the way, a captured ONBOARD_SUBMIT
        from another identity must be refused on the peer's name alone."""
        client, host = _pair()
        other = address.generate()
        hello, eph = sealed.client_hello(client, host["address"])
        submit = {"type": "ONBOARD_SUBMIT", "payload": {"timestamp": 1, "invite_code": "x"}, "from": other["address"], "signature": "00"}
        verified = []
        make = _sealed_connect(client, hello, eph, submit)
        wire = _direct_host_session([hello, make], host, {
            "auth": lambda data, *a, **k: verified.append(data) or ("hello", data["from"], True, None),
        })
        opened = [make.channel.open(f) for f in wire[1:]]
        assert verified == []
        assert any(f["type"] == "ERROR" and "sealed peer" in f["message"] for f in opened), opened

    def test_the_replay_ledger_is_not_consulted_inside_a_seal(self):
        client, host = _pair()
        hello, eph = sealed.client_hello(client, host["address"])
        remote = RemoteAgent(host["address"], keys=client, relay_url=RELAY)
        connect = remote._build_connect_message(True)

        def ledger_is_gone(_data):
            raise AssertionError("the ledger was consulted inside a sealed socket")

        make = _sealed_connect(client, hello, eph, connect)
        wire = _direct_host_session([hello, make], host, {
            "replay": ledger_is_gone,
            "agent_metadata": {"address": host["address"]},
        })
        opened = [make.channel.open(f) for f in wire[1:]]
        assert "CONNECTED" in [f["type"] for f in opened], opened

    def test_the_replay_ledger_still_guards_an_unsealed_socket(self):
        client, host = _pair()
        remote = RemoteAgent(host["address"], keys=client, relay_url=RELAY)
        connect = remote._build_connect_message(True)
        wire = _direct_host_session([connect], host, {
            "replay": lambda _data: True,      # "seen before"
            "agent_metadata": {"address": host["address"]},
        })
        assert "CONNECTED" not in [f["type"] for f in wire]
        assert any("already used" in f.get("message", "") for f in wire), wire


class TestTheLedgerAHostKeeps:

    def test_a_single_process_ledger_rejects_the_second_use(self):
        from connectonion.network.host.replay import MemoryReplayStore

        store = MemoryReplayStore()
        frame = {"signature": "0xAB", "payload": {"timestamp": 1_000}}
        assert store.already_used(frame, now=1_000) is False
        assert store.already_used({"signature": "0xab"}, now=1_001) is True   # same bytes, other spelling
        assert store.already_used(frame, now=1_000 + 2 * 300 + 1) is False   # cryptographically expired

    def test_a_deleted_sqlite_ledger_heals_on_the_next_claim(self, tmp_path):
        """What took rental-agent-mel down: the file gone, the process alive."""
        from connectonion.network.host.replay import SignatureReplayStore

        path = tmp_path / "replay.sqlite3"
        store = SignatureReplayStore(path)
        assert store.already_used({"signature": "0x01"}) is False
        path.unlink()
        assert store.already_used({"signature": "0x02"}) is False
        assert store.already_used({"signature": "0x02"}) is True
        assert path.exists()

    def test_a_hosted_agent_writes_no_replay_ledger(self, tmp_path, create_mock_agent):
        """`co host` runs one worker; its ledger lives in memory."""
        from pathlib import Path
        from unittest.mock import AsyncMock, patch

        from connectonion.network.host import server as host_module

        keys = address.generate()
        with patch.object(Path, "cwd", return_value=tmp_path):
            with patch("connectonion.address.load", return_value=keys):
                with patch.object(host_module, "_create_relay_lifespan", return_value=(AsyncMock(), AsyncMock())):
                    with patch("uvicorn.run"):
                        with patch.object(host_module, "_print_host_banner"):
                            host_module.host(create_mock_agent, relay_url="ws://test")
        assert not list(tmp_path.rglob("replay.sqlite3"))
