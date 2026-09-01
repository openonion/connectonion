"""The laptop dials the host; the host sends its resolve/connect work back down.

Both ends are real here — `ProxyChannel` (host) and `ProxyShare` (laptop) —
joined by two in-process functions instead of a WebSocket. The laptop's frames
still go through its signing path, so what the host receives is the signed
payload it would see on the wire.
"""

import asyncio
import socket
from datetime import datetime, timedelta, timezone

import pytest

from connectonion import address
from connectonion.network.host.egress_gateway import NumericEndpoint
from connectonion.network.host.proxy_channel import ProxyChannel, ProxyChannelRegistry
from connectonion.network.proxy import GrantError, issue_grant, verify
from connectonion.network.proxy import stream as wire
from connectonion.network.proxy_egress import ProxyShare


def _in(seconds: int) -> str:
    when = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return when.isoformat().replace("+00:00", "Z")


@pytest.fixture(scope="module")
def keys():
    return {"laptop": address.generate(), "host": address.generate()}


def _claims(keys, **grant_overrides):
    grant = issue_grant(
        keys["laptop"],
        holder=keys["host"]["address"],
        expires_at=_in(3600),
        **grant_overrides,
    )
    return verify(grant, None, presenter=keys["host"]["address"], now=datetime.now(timezone.utc))


class _Pair:
    """A host channel and a laptop share wired to each other directly."""

    def __init__(self, keys, claims=None, **share_kwargs):
        self.laptop = ProxyShare(keys["host"]["address"], keys=keys["laptop"], **share_kwargs)
        self.host = ProxyChannel(self._to_laptop, claims or _claims(keys))
        self.laptop._ws = self
        self.to_host = []

    async def _to_laptop(self, frame):
        await self.laptop._handle(frame)

    async def send(self, raw):
        import json

        signed = json.loads(raw)
        self.to_host.append(signed)
        await self.host.receive(signed["payload"])


async def _echo_server():
    async def handler(reader, writer):
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


@pytest.mark.asyncio
async def test_bytes_go_down_the_channel_and_come_back(keys):
    server, port = await _echo_server()

    async def to_echo(endpoint, timeout):
        assert endpoint.address == "8.8.8.8"
        return await asyncio.open_connection("127.0.0.1", port)

    pair = _Pair(keys, dialer=to_echo, allowed_ports=(port,))
    reader, writer = await pair.host.dial(NumericEndpoint(socket.AF_INET, "8.8.8.8", port), 5)
    payload = bytes(range(256)) * 300  # crosses the chunk bound, so several frames
    writer.write(payload)
    await writer.drain()
    echoed = await asyncio.wait_for(reader.readexactly(len(payload)), timeout=5)
    writer.close()
    await writer.wait_closed()
    server.close()
    await server.wait_closed()

    assert echoed == payload
    ops = [frame["payload"]["op"] for frame in pair.to_host]
    assert ops[0] == "connect"
    assert ops.count("data") >= 3
    assert not pair.laptop._streams, "the laptop kept the socket after close"
    assert not pair.host._streams, "the host kept the stream after close"
    assert pair.host.bytes_used == 2 * len(payload)


@pytest.mark.asyncio
async def test_the_laptop_resolves_and_still_refuses_its_own_lan(keys):
    async def answers(host, port):
        return ("192.168.0.1",) if host.startswith("nas") else ("8.8.8.8",)

    pair = _Pair(keys, resolver=answers)

    assert await pair.host.resolve("example.com", 443) == ("8.8.8.8",)
    with pytest.raises(OSError, match="DESTINATION_ADDRESS_DENIED"):
        await pair.host.resolve("nas.example.com", 443)
    with pytest.raises(OSError, match="DESTINATION_ADDRESS_DENIED"):
        await pair.host.dial(NumericEndpoint(socket.AF_INET, "192.168.0.1", 443), 5)
    assert pair.laptop.handled_requests == 3
    assert not pair.host._streams


@pytest.mark.asyncio
async def test_a_spent_or_expired_grant_opens_nothing(keys):
    spent = _Pair(keys, claims=_claims(keys, max_bytes=10))
    spent.host.bytes_used = 10
    with pytest.raises(OSError, match="budget"):
        await spent.host.resolve("example.com", 443)

    expired = _Pair(keys)
    expired.host._expires_at = 0
    with pytest.raises(OSError, match="expired"):
        await expired.host.resolve("example.com", 443)


@pytest.mark.asyncio
async def test_detaching_ends_every_open_stream(keys):
    server, port = await _echo_server()

    async def to_echo(endpoint, timeout):
        return await asyncio.open_connection("127.0.0.1", port)

    pair = _Pair(keys, dialer=to_echo, allowed_ports=(port,))
    reader, _writer = await pair.host.dial(NumericEndpoint(socket.AF_INET, "8.8.8.8", port), 5)
    await pair.host.close()
    server.close()
    await server.wait_closed()

    assert await asyncio.wait_for(reader.read(), timeout=5) == b""
    with pytest.raises(OSError, match="detached"):
        await pair.host.resolve("example.com", 443)


@pytest.mark.asyncio
async def test_more_streams_than_the_bound_are_refused(keys):
    pair = _Pair(keys)
    pair.host._streams = {index: object() for index in range(wire.MAX_STREAMS)}
    with pytest.raises(OSError, match="streams open"):
        await pair.host.resolve("example.com", 443)


def test_the_registry_finds_a_share_by_its_owner(keys):
    class Channel:
        def __init__(self, owner):
            self.owner = owner
            self.endpoint = f"endpoint-of-{owner}"

    registry = ProxyChannelRegistry()
    first = Channel("0xlaptop")
    assert registry.attach(first) is None
    assert registry.endpoint_for("0xlaptop") == "endpoint-of-0xlaptop"
    assert registry.endpoint_for("0xother") is None

    # A reconnect displaces the stale channel; a late detach of the stale one
    # must not remove the live one.
    second = Channel("0xlaptop")
    assert registry.attach(second) is first
    registry.detach(first)
    assert registry.get("0xlaptop") is second
    registry.detach(second)
    assert registry.endpoint_for("0xlaptop") is None


# --- attaching: who may lend what to whom ------------------------------------


class _Trust:
    def __init__(self, level="contact"):
        self.level = level

    def is_admin(self, _address):
        return False

    def get_level(self, _address):
        return self.level


def _attach(keys, grant, *, level="contact", transport="direct", signed=True, connected=None):
    from connectonion.network.host.ws_router.proxy import _attach_claims

    conn = {
        "authenticated": True,
        "signed_commands": signed,
        "agent_address": connected or keys["laptop"]["address"],
        "transport": transport,
    }
    route_handlers = {
        "proxy_channels": ProxyChannelRegistry(),
        "trust_agent": _Trust(level),
        "agent_metadata": {"address": keys["host"]["address"]},
    }
    return _attach_claims({"grant": grant}, conn, route_handlers)


def test_a_grant_for_this_host_from_the_connected_laptop_attaches(keys):
    grant = issue_grant(keys["laptop"], holder=keys["host"]["address"], expires_at=_in(60))
    claims = _attach(keys, grant)
    assert claims["grantor"] == keys["laptop"]["address"]


def test_grants_are_refused_when_they_do_not_bind_this_socket_to_this_host(keys):
    stranger = address.generate()
    for_someone_else = issue_grant(keys["laptop"], holder=stranger["address"], expires_at=_in(60))
    with pytest.raises(GrantError, match="not the grant holder"):
        _attach(keys, for_someone_else)

    expired = issue_grant(keys["laptop"], holder=keys["host"]["address"], expires_at=_in(-1))
    with pytest.raises(GrantError, match="expired"):
        _attach(keys, expired)

    # Signed by a laptop other than the one on this socket: someone
    # presenting a grant they found, not one they issued.
    someone_elses = issue_grant(stranger, holder=keys["host"]["address"], expires_at=_in(60))
    with pytest.raises(GrantError, match="not the connected agent"):
        _attach(keys, someone_elses)

    good = issue_grant(keys["laptop"], holder=keys["host"]["address"], expires_at=_in(60))
    with pytest.raises(GrantError, match="direct connection"):
        _attach(keys, good, transport="relay")
    with pytest.raises(GrantError, match="contact or admin"):
        _attach(keys, good, level="stranger")
    with pytest.raises(GrantError, match="signed CONNECT"):
        _attach(keys, good, signed=False)


@pytest.mark.asyncio
async def test_the_session_registers_on_attach_and_forgets_on_disconnect(keys, monkeypatch):
    from connectonion.network.connect import RemoteAgent
    from connectonion.network.host.ws_router import session

    host = keys["host"]["address"]
    grant = issue_grant(keys["laptop"], holder=host, expires_at=_in(60))
    attach = RemoteAgent(host, keys=keys["laptop"])._build_command_message(
        {"type": wire.ATTACH, "grant": grant}, True
    )
    frames = [{"type": "CONNECT", "from": keys["laptop"]["address"]}, attach]
    registry = ProxyChannelRegistry()
    attached = asyncio.Event()
    seen_while_attached = []
    sent = []

    async def fake_connect(data, send, conn, *args):
        conn.update(
            authenticated=True,
            agent_address=keys["laptop"]["address"],
            signed_commands=True,
            recipient_address=host,
            session_id="oip-session",
        )

    async def recv():
        if frames:
            return frames.pop(0)
        await attached.wait()
        seen_while_attached.append(registry.endpoint_for(keys["laptop"]["address"]))
        return None

    async def send(message):
        sent.append(message)
        if message.get("type") == wire.ATTACHED:
            attached.set()

    monkeypatch.setattr(session, "handle_connect", fake_connect)
    await session.run_ws_session(
        send,
        recv,
        route_handlers={
            "proxy_channels": registry,
            "trust_agent": _Trust(),
            "agent_metadata": {"address": host},
        },
        storage=None,
        registry=None,
        trust=None,
        enable_ping=False,
        transport="direct",
    )

    assert sent[-1]["type"] == wire.ATTACHED
    endpoint = seen_while_attached[0]
    assert endpoint is not None and endpoint.host == "127.0.0.1"
    assert registry.endpoint_for(keys["laptop"]["address"]) is None
