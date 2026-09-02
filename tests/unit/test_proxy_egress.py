"""Lending this computer's connection must change the address, not the policy."""

import asyncio
import base64
import json
import os
import stat

import pytest

from connectonion import address
from connectonion.network.host.egress_gateway import EgressGateway, GatewayRefusal
from connectonion.network.proxy_egress import (
    ProxyShare,
    ShareEndpoint,
    remote_proxy_dialer,
    remote_proxy_resolver,
)


def _auth(endpoint) -> str:
    raw = f"{endpoint.username}:{endpoint.password}".encode("ascii")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def test_proxy_registry_is_atomic_and_private(tmp_path, monkeypatch):
    from connectonion.cli.commands import proxy_commands

    path = tmp_path / ".co" / "proxy-shares.json"
    monkeypatch.setattr(proxy_commands, "STATE_PATH", path)
    proxy_commands._save({"0xtest": {"state": "attached"}})

    assert json.loads(path.read_text()) == {"0xtest": {"state": "attached"}}
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_share_signs_a_grant_the_host_can_hold():
    """The grant is what the host checks; it must name that host and be signed
    by this computer, or an attach from anyone else with the grant in hand would
    be accepted."""
    laptop, host = address.generate(), address.generate()
    share = ProxyShare(host["address"], keys=laptop, ttl=60)

    grant = share._grant()
    assert grant["holder"] == host["address"]
    assert grant["grantor"] == laptop["address"]
    assert grant["expires_at"].endswith("Z")
    # Re-minted on every reconnect, but never with a later expiry.
    assert share._grant()["expires_at"] == grant["expires_at"]


class _Socket:
    """A host that pushes its profile before answering the attach."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.sent = []

    async def recv(self):
        return json.dumps(self.frames.pop(0))

    async def send(self, raw):
        self.sent.append(json.loads(raw))


@pytest.mark.asyncio
async def test_the_attach_answer_is_read_past_the_hosts_other_frames():
    """A real host sends AGENT_PROFILE (and pings) right after CONNECTED. The
    first frame after PROXY_ATTACH is not the answer; the first PROXY_ATTACHED
    or ERROR is. Taking the profile as a refusal broke the very first
    two-machine run."""
    laptop, host = address.generate(), address.generate()
    share = ProxyShare(host["address"], keys=laptop, ttl=60)
    ws = _Socket([
        {"type": "AGENT_PROFILE", "name": "host"},
        {"type": "PING"},
        {"type": "PROXY_ATTACHED", "expires_at": "2030-01-01T00:00:00Z"},
    ])

    reply = await share._attach_reply(ws)

    assert reply["type"] == "PROXY_ATTACHED"
    assert ws.sent == [{"type": "PONG"}]

    refused = _Socket([{"type": "AGENT_PROFILE"}, {"type": "ERROR", "message": "proxy attach refused: no"}])
    assert (await share._attach_reply(refused))["message"] == "proxy attach refused: no"


@pytest.mark.asyncio
async def test_a_share_still_refuses_the_sharer_s_own_network():
    """Lending a connection must not lend the network behind it.

    This is the whole reason the share reuses the gateway's destination policy
    rather than being a plain forwarder: someone who lends their laptop's
    connection is not offering their router, their NAS, or whatever else
    answers on their LAN.
    """
    share = ProxyShare(address.generate()["address"], keys=address.generate())

    with pytest.raises(GatewayRefusal, match="DESTINATION_ADDRESS_DENIED"):
        await share._policy.connect_destination("192.168.0.1", 80)
    with pytest.raises(GatewayRefusal, match="DESTINATION_ADDRESS_DENIED"):
        await share._policy.connect_destination("127.0.0.1", 443)


@pytest.mark.asyncio
async def test_laptop_dns_refuses_a_name_that_resolves_into_its_lan():
    async def private_answer(_host, _port):
        return ("192.168.0.1",)

    share = ProxyShare(
        address.generate()["address"], keys=address.generate(), resolver=private_answer
    )
    with pytest.raises(GatewayRefusal, match="DESTINATION_ADDRESS_DENIED"):
        await share._policy.resolve_destination("public-looking.example.net", 443)


@pytest.mark.asyncio
async def test_dns_runs_on_the_laptop_then_the_host_asks_for_one_numeric_address():
    """The browser host never resolves a target; the Laptop does, then both
    sides classify the complete answer set before a numeric CONNECT."""
    requests = []

    async def recorder(reader, writer):
        request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
        requests.append(request)
        if request.startswith(b"CORESOLVE "):
            body = b"8.8.8.8\n"
            writer.write(
                b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 8\r\n\r\n"
                + body
            )
        else:
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        writer.close()

    fake_share = await asyncio.start_server(recorder, "127.0.0.1", 0)
    port = fake_share.sockets[0].getsockname()[1]

    share = ShareEndpoint("127.0.0.1", port, "u", "p")
    gateway = EgressGateway(
        resolver=remote_proxy_resolver(share),
        dialer=remote_proxy_dialer(share),
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

    assert len(requests) == 2, "the host did not resolve and connect through the share"
    resolve_line = requests[0].decode("ascii").split("\r\n")[0]
    connect_line = requests[1].decode("ascii").split("\r\n")[0]
    assert resolve_line.startswith("CORESOLVE ")
    assert "example.com" not in resolve_line
    assert connect_line == "CONNECT 8.8.8.8:443 HTTP/1.1"


def test_the_share_command_needs_an_identity_to_sign_with(tmp_path, monkeypatch, capsys):
    """Without keys there is nothing to sign the grant with, so the command
    says so and stops instead of dialing a host it could never attach to."""
    import importlib

    from connectonion.cli.commands import proxy_commands

    connect_module = importlib.import_module("connectonion.network.connect")
    monkeypatch.setattr(proxy_commands, "STATE_PATH", tmp_path / "proxy-shares.json")
    monkeypatch.setattr(connect_module, "_this_callers_identity", lambda: None)

    assert proxy_commands._share("0xtest", False, None) == 2
    assert "co init" in capsys.readouterr().err
