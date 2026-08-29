"""Lending this computer's connection must change the address, not the policy."""

import asyncio
import base64
import socket

import pytest

from connectonion.network.host.egress_gateway import EgressGateway
from connectonion.network.proxy_egress import (
    ProxyEgressService,
    local_egress_address,
    remote_proxy_dialer,
    shared_egress_gateway,
)


async def _origin(response=b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nhi"):
    """A destination that records the address its caller arrived from."""
    seen = []

    async def handler(reader, writer):
        seen.append(writer.get_extra_info("peername")[0])
        await reader.read(2048)
        writer.write(response)
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1], seen


def _auth(endpoint) -> str:
    raw = f"{endpoint.username}:{endpoint.password}".encode("ascii")
    return "Basic " + base64.b64encode(raw).decode("ascii")


@pytest.mark.asyncio
async def test_the_share_listens_where_a_peer_can_reach_it():
    """A browser on another machine has to be able to connect.

    The host-private gateway binds loopback on purpose — nothing outside that
    machine may drive the browser's proxy. A share is the opposite: it exists
    to be reached from elsewhere, and one bound to loopback is reachable by
    nothing and would fail only once a remote agent tried to use it.
    """
    async with ProxyEgressService() as share:
        endpoint = share.endpoint
        assert endpoint.host == local_egress_address()
        assert endpoint.host != "127.0.0.1"
        assert endpoint.url == f"http://{endpoint.host}:{endpoint.port}"
        # The credential is not in the address handed to the peer.
        assert endpoint.password not in endpoint.url


@pytest.mark.asyncio
async def test_a_share_still_refuses_the_sharer_s_own_network():
    """Lending a connection must not lend the network behind it.

    This is the whole reason the share reuses the gateway's destination policy
    rather than being a plain forwarder: someone who lends their laptop's
    connection is not offering their router, their NAS, or whatever else
    answers on their LAN.
    """
    async with ProxyEgressService(bind_host="127.0.0.1") as share:
        endpoint = share.endpoint
        reader, writer = await asyncio.open_connection(endpoint.host, endpoint.port)
        writer.write(
            (
                "CONNECT 192.168.0.1:80 HTTP/1.1\r\nHost: 192.168.0.1:80\r\n"
                f"Proxy-Authorization: {_auth(endpoint)}\r\n\r\n"
            ).encode("ascii")
        )
        await writer.drain()
        response = await asyncio.wait_for(reader.read(200), timeout=5)
        writer.close()

    assert b"403" in response
    assert b"DESTINATION_ADDRESS_DENIED" in response


@pytest.mark.asyncio
async def test_an_unauthenticated_neighbour_cannot_use_the_share():
    async with ProxyEgressService(bind_host="127.0.0.1") as share:
        endpoint = share.endpoint
        reader, writer = await asyncio.open_connection(endpoint.host, endpoint.port)
        writer.write(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.read(200), timeout=5)
        writer.close()

    assert b"407" in response


@pytest.mark.asyncio
async def test_traffic_leaves_through_the_share_rather_than_the_host():
    """The end-to-end property: the destination sees the sharer, not the host.

    Both hops are real here — a host-private gateway whose dialer is the share,
    and a share that dials the destination. What proves it is the origin's own
    record of who connected to it, and the share's request counter moving.
    """
    origin, port, seen = await _origin()

    async def to_origin(endpoint, timeout):
        # Stands in for the sharer's own internet: the share dials out from
        # this machine, and the origin records who arrived.
        assert endpoint.address == "8.8.8.8", endpoint
        return await asyncio.open_connection("127.0.0.1", port)

    async def public(host, port_):
        return ("8.8.8.8",)

    async with ProxyEgressService(
        bind_host="127.0.0.1", resolver=public, dialer=to_origin
    ) as share:
        gateway = shared_egress_gateway(
            share.endpoint, resolver=public, allowed_ports=(80, 443)
        )
        endpoint = await gateway.start()
        try:
            reader, writer = await asyncio.open_connection(endpoint.host, endpoint.port)
            writer.write(
                (
                    "GET http://example.com/ HTTP/1.1\r\n"
                    "Host: example.com\r\n"
                    f"Proxy-Authorization: {_auth(endpoint)}\r\n\r\n"
                ).encode("ascii")
            )
            await writer.drain()
            await asyncio.wait_for(reader.read(400), timeout=5)
            writer.close()
        finally:
            await gateway.stop()
            origin.close()
            await origin.wait_closed()
        # The share decided the request too — the policy applies on both hops,
        # so a host cannot reach through a share to somewhere the share refuses.
        assert share.handled_requests >= 1, "the host did not go through the share"
    assert seen, "the destination was never reached"


@pytest.mark.asyncio
async def test_the_host_asks_the_share_for_a_numeric_address_only():
    """Lending a connection must not widen what the host was willing to reach.

    The host resolves and classifies the hostname itself; only the last hop
    moves. If it forwarded the name instead, the share would resolve it a
    second time and could land somewhere the host never approved.
    """
    requests = []

    async def recorder(reader, writer):
        requests.append(await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5))
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        writer.close()

    fake_share = await asyncio.start_server(recorder, "127.0.0.1", 0)
    port = fake_share.sockets[0].getsockname()[1]
    from connectonion.network.proxy_egress import ShareEndpoint

    dial = remote_proxy_dialer(ShareEndpoint("127.0.0.1", port, "u", "p"))
    gateway = EgressGateway(
        resolver=lambda host, port_: asyncio.sleep(0, result=("8.8.8.8",)),
        dialer=dial,
    )
    endpoint = await gateway.start()
    try:
        reader, writer = await asyncio.open_connection(endpoint.host, endpoint.port)
        writer.write(
            (
                "CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n"
                f"Proxy-Authorization: {_auth(endpoint)}\r\n\r\n"
            ).encode("ascii")
        )
        await writer.drain()
        await asyncio.wait_for(reader.read(200), timeout=5)
        writer.close()
    finally:
        await gateway.stop()
        fake_share.close()
        await fake_share.wait_closed()

    assert requests, "the host never reached the share"
    asked = requests[0].decode("ascii")
    assert "CONNECT 8.8.8.8:443" in asked, asked
    assert "example.com" not in asked.split("\r\n")[0]


def test_the_reachable_address_is_not_loopback():
    address = local_egress_address()
    assert address != "127.0.0.1"
    socket.inet_aton(address)


def test_the_share_command_serves_instead_of_reporting_and_exiting(tmp_path, monkeypatch):
    """`co proxy share` must still be listening when it says it is sharing.

    The share is a socket owned by this process. Printing "sharing" and
    returning closes it the moment the shell gets its prompt back, so every
    later command reads a registry entry for something nothing serves — and the
    remote browser silently falls back to failing every request. Measured that
    way once: the command reported success and a connect to its own advertised
    address answered ConnectionRefusedError.
    """
    import json
    import subprocess
    import sys
    import time

    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    env = {**__import__("os").environ, "HOME": str(home)}
    process = subprocess.Popen(
        [sys.executable, "-m", "connectonion.cli.main", "proxy", "share", "to", "0xtest"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
    )
    try:
        registry = home / ".co" / "proxy-shares.json"
        for _ in range(100):
            if registry.exists():
                break
            time.sleep(0.1)
        assert registry.exists(), "the share never registered"
        url = json.loads(registry.read_text())["0xtest"]["url"]
        host, port = url.rsplit("//", 1)[1].split(":")

        probe = socket.socket()
        probe.settimeout(3)
        try:
            probe.connect((host, int(port)))
        finally:
            probe.close()
    finally:
        process.terminate()
        process.wait(timeout=15)

    # And a stopped share does not stay in the registry claiming to be live.
    remaining = json.loads(registry.read_text()) if registry.exists() else {}
    assert "0xtest" not in remaining
