"""A direct OIP socket is private without TLS.

#649: a signed CONNECT captured on a plaintext link could be replayed within
its freshness window, so direct connections were limited to TLS or loopback,
and every self-hosted agent needed a domain, a certificate and Caddy. The
Melbourne rental host announced http://34.129.161.131:8001 and the 1.8.0b1
laptop refused it. Sealing the socket with one-time keys signed by both long
term identities removes the TLS requirement without reopening #649.
"""

import asyncio
import json

import pytest

from connectonion import address
from connectonion.network import sealed


def _pair():
    return address.generate(), address.generate()


class TestTheHandshake:

    def test_both_sides_derive_the_same_channel(self):
        client, host = _pair()
        hello, eph = sealed.client_hello(client, host["address"])
        reply, host_channel = sealed.host_accept(hello, host)
        client_channel = sealed.client_finish(reply, hello, eph)

        frame = client_channel.seal({"type": "CONNECT", "timestamp": 1})
        assert frame["type"] == "SEALED"
        assert "CONNECT" not in json.dumps(frame)
        assert host_channel.open(frame) == {"type": "CONNECT", "timestamp": 1}
        back = host_channel.seal({"type": "CONNECTED"})
        assert client_channel.open(back) == {"type": "CONNECTED"}

    def test_a_replayed_sealed_frame_does_not_open(self):
        """The whole point: a captured frame is worth nothing to whoever has it."""
        client, host = _pair()
        hello, eph = sealed.client_hello(client, host["address"])
        reply, host_channel = sealed.host_accept(hello, host)
        client_channel = sealed.client_finish(reply, hello, eph)

        frame = client_channel.seal({"type": "EXEC", "tool": "bash"})
        host_channel.open(frame)
        with pytest.raises(sealed.SealError, match="out of order"):
            host_channel.open(frame)

    def test_a_captured_hello_cannot_be_finished_by_a_stranger(self):
        """Whoever replays the SEAL does not hold its one-time private key, so
        the host's answer opens nothing for them."""
        client, host = _pair()
        hello, _ = sealed.client_hello(client, host["address"])
        reply, host_channel = sealed.host_accept(hello, host)
        from nacl.public import PrivateKey
        strangers_channel = sealed.client_finish(reply, hello, PrivateKey.generate())

        with pytest.raises(sealed.SealError, match="does not open"):
            host_channel.open(strangers_channel.seal({"type": "EXEC"}))

    def test_a_hello_from_someone_who_is_not_who_they_say_is_refused(self):
        client, host = _pair()
        hello, _ = sealed.client_hello(client, host["address"])
        hello["from"] = address.generate()["address"]
        with pytest.raises(sealed.SealRefused, match="does not verify"):
            sealed.host_accept(hello, host)

    def test_a_stale_hello_is_refused(self):
        client, host = _pair()
        hello, _ = sealed.client_hello(client, host["address"], now=1_000)
        with pytest.raises(sealed.SealRefused, match="stale"):
            sealed.host_accept(hello, host, now=1_000 + 301)

    def test_a_hello_for_another_host_is_refused(self):
        client, host = _pair()
        hello, _ = sealed.client_hello(client, address.generate()["address"])
        with pytest.raises(sealed.SealRefused, match="another host"):
            sealed.host_accept(hello, host)

    def test_an_answer_from_the_wrong_host_is_refused(self):
        """A SEALED_OK signed by anyone but the address that was dialed."""
        client, host = _pair()
        impostor = address.generate()
        hello, eph = sealed.client_hello(client, host["address"])
        reply, _ = sealed.host_accept({**hello, "to": impostor["address"]} | {
            "signature": address.sign(client, json.dumps(
                {k: ({**hello, "to": impostor["address"]})[k] for k in ("type", "to", "from", "ephemeral", "timestamp")},
                sort_keys=True, separators=(",", ":")).encode()).hex()
        }, impostor)
        with pytest.raises(sealed.SealRefused, match="not from the host"):
            sealed.client_finish(reply, hello, eph)

    def test_an_answer_to_a_different_hello_is_refused(self):
        client, host = _pair()
        hello1, eph1 = sealed.client_hello(client, host["address"])
        hello2, _ = sealed.client_hello(client, host["address"])
        reply_to_2, _ = sealed.host_accept(hello2, host)
        with pytest.raises(sealed.SealRefused, match="different SEAL"):
            sealed.client_finish(reply_to_2, hello1, eph1)


class _Socket:
    """A host-side stand-in that answers SEAL as a sealing host would."""

    def __init__(self, host_identity, reply_to_connect):
        self.host = host_identity
        self.reply_to_connect = reply_to_connect
        self.channel = None
        self.inbox = []
        self.seen_clear = []

    async def send(self, raw):
        frame = json.loads(raw)
        if frame.get("type") == "SEAL":
            reply, self.channel = sealed.host_accept(frame, self.host)
            self.inbox.append(json.dumps(reply))
            return
        clear = self.channel.open(frame)
        self.seen_clear.append(clear)
        if clear["type"] == "CONNECT":
            self.inbox.append(json.dumps(self.channel.seal(self.reply_to_connect)))

    async def recv(self):
        return self.inbox.pop(0)

    async def close(self):
        pass

    def __await__(self):
        async def _self():
            return self
        return _self().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class TestTheClientSealsADirectSocket:

    def _remote(self, monkeypatch, socket, keys, url="ws://34.129.161.131:8001/ws"):
        import websockets
        from connectonion.network.connect import RemoteAgent

        monkeypatch.setattr(websockets, "connect", lambda *a, **k: socket)
        remote = RemoteAgent(socket.host["address"], keys=keys, relay_url="wss://relay.example")
        remote._endpoint_resolved = True
        remote._resolved_endpoint = url
        return remote

    def test_a_public_plaintext_endpoint_is_used_once_sealed(self, monkeypatch):
        client, host = _pair()
        socket = _Socket(host, {"type": "CONNECTED", "session_id": "s1"})
        remote = self._remote(monkeypatch, socket, client)

        async def run():
            import websockets
            connection, is_direct = await remote._open_best_connection(websockets)
            async with connection as ws:
                await ws.send(json.dumps(remote._build_connect_message(True)))
                return is_direct, json.loads(await ws.recv())

        is_direct, answer = asyncio.run(run())
        assert is_direct is True
        assert answer["type"] == "CONNECTED"
        assert socket.seen_clear[0]["type"] == "CONNECT"

    def test_a_host_that_does_not_seal_is_not_sent_a_signed_frame_in_the_clear(self, monkeypatch):
        """An older host answers SEAL with an error; the laptop must not then
        send its signed CONNECT on the bare public link. It moves on."""
        import websockets
        from connectonion.network.connect import RemoteAgent

        client, host = _pair()
        attempts = []

        class OldHost(_Socket):
            async def send(self, raw):
                frame = json.loads(raw)
                assert frame.get("type") != "CONNECT", "signed CONNECT went onto a plaintext public link"
                self.inbox.append(json.dumps({"type": "ERROR", "message": "unauthorized"}))

        def connect(url, *a, **k):
            attempts.append(url)
            if url.startswith("ws://34."):
                return OldHost(host, None)
            raise ConnectionRefusedError("no relay in this test")

        monkeypatch.setattr(websockets, "connect", connect)
        remote = RemoteAgent(host["address"], keys=client, relay_url="wss://relay.example")
        remote._endpoint_resolved = True
        remote._resolved_endpoint = "ws://34.129.161.131:8001/ws"

        with pytest.raises(OSError):
            asyncio.run(remote._open_best_connection(websockets))
        assert attempts == ["ws://34.129.161.131:8001/ws", "wss://relay.example/ws/input"]
        assert remote._resolved_endpoint is None


class TestTheHostSealsADirectSocket:
    """Through the ASGI adapter, the way a real direct socket arrives."""

    def _run(self, frames, host_identity, connect_auth):
        from unittest.mock import Mock

        from connectonion.network.asgi import handle_websocket
        from connectonion.network.host.session import ActiveSessionRegistry

        sent = []
        inbox = list(frames)

        async def receive():
            if inbox:
                return {"type": "websocket.receive", "text": json.dumps(inbox.pop(0))}
            await asyncio.sleep(0.05)
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent.append(msg)

        handlers = {
            "identity": host_identity,
            "connect_auth": connect_auth,
            "trust_agent": Mock(config={}),
        }
        storage = Mock()
        storage.get.return_value = None
        asyncio.run(handle_websocket(
            {"path": "/ws", "type": "websocket"}, receive, send,
            route_handlers=handlers, storage=storage,
            registry=ActiveSessionRegistry(), trust="open",
        ))
        return [json.loads(m["text"]) for m in sent if m["type"] == "websocket.send"], sent

    def test_seal_is_answered_and_connect_travels_sealed(self):
        client, host = _pair()
        hello2, eph2 = sealed.client_hello(client, host["address"])
        holder = {}

        def connect_auth(data, *a, **k):
            holder["clear_connect"] = data
            return ("hello", client["address"], True, None)

        # The client's channel exists only after SEALED_OK, so the CONNECT is
        # sealed inside receive(), once the host's answer is on the wire.
        from unittest.mock import Mock
        from connectonion.network.asgi import handle_websocket
        from connectonion.network.host.session import ActiveSessionRegistry

        sent = []
        step = {"n": 0}

        async def receive():
            step["n"] += 1
            if step["n"] == 1:
                return {"type": "websocket.receive", "text": json.dumps(hello2)}
            if step["n"] == 2:
                reply = json.loads(sent[1]["text"])   # sent[0] is websocket.accept
                holder["channel"] = sealed.client_finish(reply, hello2, eph2)
                connect = {"type": "CONNECT", "payload": {"timestamp": 1}, "from": client["address"], "signature": "00"}
                return {"type": "websocket.receive", "text": json.dumps(holder["channel"].seal(connect))}
            await asyncio.sleep(0.05)
            return {"type": "websocket.disconnect"}

        async def send(msg):
            sent.append(msg)

        storage = Mock()
        storage.get.return_value = None
        asyncio.run(handle_websocket(
            {"path": "/ws", "type": "websocket"}, receive, send,
            route_handlers={"identity": host, "connect_auth": connect_auth, "trust_agent": Mock(config={})},
            storage=storage, registry=ActiveSessionRegistry(), trust="open",
        ))

        assert holder["clear_connect"]["type"] == "CONNECT"
        wire = [json.loads(m["text"]) for m in sent if m["type"] == "websocket.send"]
        assert wire[0]["type"] == "SEALED_OK"
        assert all(f["type"] == "SEALED" for f in wire[1:]), [f["type"] for f in wire]
        opened = [holder["channel"].open(f) for f in wire[1:]]
        assert "CONNECTED" in [f["type"] for f in opened]

    def test_a_bad_seal_closes_the_socket_without_a_session(self):
        client, host = _pair()
        hello, _ = sealed.client_hello(client, address.generate()["address"])
        frames_out, raw = self._run([hello], host, lambda *a, **k: ("hello", client["address"], True, None))
        assert frames_out[0]["type"] == "ERROR" and "seal refused" in frames_out[0]["message"]
        assert raw[-1] == {"type": "websocket.close", "code": 4003}

    def test_an_unsealed_client_still_gets_through(self):
        """Older clients open with CONNECT; nothing changes for them."""
        client, host = _pair()
        connect = {"type": "CONNECT", "payload": {"timestamp": 1}, "from": client["address"], "signature": "00"}
        frames_out, _ = self._run([connect], host, lambda *a, **k: ("hello", client["address"], True, None))
        assert "CONNECTED" in [f["type"] for f in frames_out]
