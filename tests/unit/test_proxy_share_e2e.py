"""A laptop share attached over a real WebSocket, carrying a real request.

Everything that runs in production runs here, in one process: the host's
`run_ws_session` behind a `websockets` server, `ProxyShare` dialing it with a
signed CONNECT and PROXY_ATTACH, the host-private `EgressGateway` fed by the
attached channel, and a browser stand-in doing an HTTP GET through that
gateway. The bytes go host → laptop → origin and back; the origin records who
arrived. Only the laptop's DNS and dial are stubbed, so the "internet" is a
local socket.
"""

import asyncio
import base64
import json

import pytest
import websockets

from connectonion import address
from connectonion.network.host.proxy_channel import ProxyChannelRegistry
from connectonion.network.host.ws_router import session
from connectonion.network.proxy_egress import ProxyShare, shared_egress_gateway

pytestmark = pytest.mark.slow


class _Trust:
    def is_admin(self, _address):
        return False

    def get_level(self, _address):
        return "contact"


async def _serve_host(host_keys, registry, monkeypatch, laptop_address):
    async def fake_connect(data, send, conn, *args):
        conn.update(
            authenticated=True,
            agent_address=laptop_address,
            signed_commands=True,
            recipient_address=host_keys["address"],
            session_id="oip-session",
        )
        await send({"type": "CONNECTED"})

    monkeypatch.setattr(session, "handle_connect", fake_connect)

    async def handler(ws):
        async def recv():
            try:
                return json.loads(await ws.recv())
            except websockets.exceptions.ConnectionClosed:
                return None

        async def send(message):
            await ws.send(json.dumps(message))

        await session.run_ws_session(
            send,
            recv,
            route_handlers={
                "proxy_channels": registry,
                "trust_agent": _Trust(),
                "agent_metadata": {"address": host_keys["address"]},
            },
            storage=None,
            registry=None,
            trust=None,
            enable_ping=False,
            transport="direct",
        )

    return await websockets.serve(handler, "127.0.0.1", 0)


async def _origin():
    seen = []

    async def handler(reader, writer):
        seen.append(writer.get_extra_info("peername")[0])
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 14\r\nConnection: close\r\n\r\nthrough laptop")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1], seen


async def _get_through(endpoint) -> bytes:
    reader, writer = await asyncio.open_connection(endpoint.host, endpoint.port)
    auth = base64.b64encode(f"{endpoint.username}:{endpoint.password}".encode()).decode()
    writer.write(
        (
            "GET http://example.com/ HTTP/1.1\r\nHost: example.com\r\n"
            f"Proxy-Authorization: Basic {auth}\r\nConnection: close\r\n\r\n"
        ).encode("ascii")
    )
    await writer.drain()
    response = await asyncio.wait_for(reader.read(), timeout=10)
    writer.close()
    return response


async def _until(condition, timeout=10):
    async def poll():
        while not condition():
            await asyncio.sleep(0.02)

    await asyncio.wait_for(poll(), timeout=timeout)


@pytest.mark.asyncio
async def test_a_page_fetched_on_the_host_leaves_from_the_laptop(monkeypatch):
    laptop, host = address.generate(), address.generate()
    registry = ProxyChannelRegistry()
    ws_server = await _serve_host(host, registry, monkeypatch, laptop["address"])
    ws_port = ws_server.sockets[0].getsockname()[1]
    origin, origin_port, seen = await _origin()

    async def laptop_dns(name, port):
        return ("8.8.8.8",)

    async def laptop_dial(endpoint, timeout):
        assert endpoint.address == "8.8.8.8"
        return await asyncio.open_connection("127.0.0.1", origin_port)

    states = []
    share = ProxyShare(
        host["address"],
        keys=laptop,
        ttl=60,
        resolver=laptop_dns,
        dialer=laptop_dial,
        on_state=lambda state, detail: states.append((state, detail)),
    )
    # No relay lookup in a test: the host is right here.
    share.remote._resolved_endpoint = f"ws://127.0.0.1:{ws_port}"
    share.remote._endpoint_resolved = True

    stop = asyncio.Event()
    serving = asyncio.create_task(share.serve(stop))
    await _until(lambda: registry.endpoint_for(laptop["address"]) is not None)

    gateway = shared_egress_gateway(registry.endpoint_for(laptop["address"]), allowed_ports=(80,))
    endpoint = await gateway.start()
    try:
        response = await _get_through(endpoint)
    finally:
        await gateway.stop()

    stop.set()
    await asyncio.wait_for(serving, timeout=10)
    await _until(lambda: registry.endpoint_for(laptop["address"]) is None)
    ws_server.close()
    await ws_server.wait_closed()
    origin.close()
    await origin.wait_closed()

    assert response.endswith(b"through laptop"), response
    assert seen == ["127.0.0.1"], "the origin was not reached from the laptop side"
    assert share.handled_requests >= 2, "resolve and connect both go to the laptop"
    assert [state for state, _ in states] == ["connecting", "attached", "stopped"]
