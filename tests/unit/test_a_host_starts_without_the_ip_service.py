"""An outside IP lookup must not decide whether an agent can be reached.

`get_ips()` appends the public address from a third-party service with nothing
around the call:

    ips.append(httpx.get("https://api.ipify.org", timeout=5).text)

The module header says otherwise, in the same breath as describing the call:

    Errors: ... ipify timeout returns without public IP

It does not. A timeout, a DNS failure, or ipify answering 502 raises out of
`get_ips()`, out of `get_endpoints()`, and into whatever was starting the host —
so an agent on a LAN, whose local addresses were already collected and are the
ones its neighbours would use, publishes nothing because a service on the
internet was briefly unavailable.

ipify was returning 520 while this was found, which is what prompted looking.

The local addresses are the part this project owns and they are already in the
list before the call. Losing the public one costs reachability from outside NAT;
losing all of them costs the agent. So the call is allowed to fail and the rest
is kept — which is what the header already claimed.
"""

import asyncio

import httpx
import pytest

from connectonion.network import announce


def raise_when_called(error):
    def fail(*args, **kwargs):
        raise error

    return fail


class TestTheLookupIsAllowedToFail:

    @pytest.fixture
    def ipify_down(self, monkeypatch):
        def refuse(*args, **kwargs):
            raise httpx.ConnectTimeout("ipify unreachable")

        monkeypatch.setattr(announce.httpx, "get", refuse)

    def test_get_ips_still_returns(self, ipify_down):
        assert announce.get_ips()

    def test_localhost_survives(self, ipify_down):
        assert "localhost" in announce.get_ips()

    def test_the_local_addresses_survive(self, ipify_down):
        """The ones a neighbour on the same LAN would actually use."""
        ips = announce.get_ips()

        assert [ip for ip in ips if ip != "localhost"], (
            "every local address was lost because an outside service was down"
        )

    def test_endpoints_are_still_published(self, ipify_down):
        endpoints = announce.get_endpoints(8000)

        assert endpoints, "the agent would announce no endpoint at all"

    @pytest.mark.parametrize(
        "failure",
        [
            httpx.ConnectTimeout("timeout"),
            httpx.ReadTimeout("read timeout"),
            httpx.ConnectError("dns"),
            httpx.HTTPStatusError("502", request=None, response=None),
        ],
    )
    def test_any_transport_failure_is_survived(self, monkeypatch, failure):
        def refuse(*args, **kwargs):
            raise failure

        monkeypatch.setattr(announce.httpx, "get", refuse)

        assert announce.get_ips()


class TestLocalAdapterDiscoveryIsOptional:
    class PublicResponse:
        text = "203.0.113.7"

    @staticmethod
    def deny_adapters(monkeypatch, error):
        monkeypatch.setattr(announce.ifaddr, "get_adapters", raise_when_called(error))

    def test_permission_denial_keeps_the_public_address(self, monkeypatch):
        self.deny_adapters(monkeypatch, PermissionError("private interface detail"))
        monkeypatch.setattr(
            announce.httpx, "get", lambda *a, **k: self.PublicResponse()
        )

        assert announce.get_ips() == ["localhost", "203.0.113.7"]

    def test_another_os_error_is_also_a_degraded_path(self, monkeypatch):
        self.deny_adapters(monkeypatch, OSError("netlink unavailable"))
        monkeypatch.setattr(
            announce.httpx, "get", lambda *a, **k: self.PublicResponse()
        )

        assert "203.0.113.7" in announce.get_ips()

    def test_the_diagnostic_is_concise_and_does_not_leak_interfaces(
        self, monkeypatch, capsys
    ):
        self.deny_adapters(monkeypatch, PermissionError("secret-interface-name"))
        monkeypatch.setattr(
            announce.httpx, "get", lambda *a, **k: self.PublicResponse()
        )

        announce.get_ips()
        output = capsys.readouterr().out

        assert "local network discovery unavailable (PermissionError)" in output
        assert "secret-interface-name" not in output

    def test_both_sources_can_fail_without_an_endpoint_or_traceback(
        self, monkeypatch
    ):
        self.deny_adapters(monkeypatch, PermissionError("denied"))
        monkeypatch.setattr(
            announce.httpx,
            "get",
            raise_when_called(httpx.ConnectError("offline")),
        )

        assert announce.get_ips() == ["localhost"]
        assert announce.get_endpoints(8000) == []

    def test_a_local_address_survives_when_the_public_lookup_fails(
        self, monkeypatch
    ):
        local_ip = type("IP", (), {"ip": "10.0.0.8"})()
        adapter = type("Adapter", (), {"ips": [local_ip]})()
        monkeypatch.setattr(announce.ifaddr, "get_adapters", lambda: [adapter])
        monkeypatch.setattr(
            announce.httpx,
            "get",
            raise_when_called(httpx.ConnectError("offline")),
        )

        assert announce.get_ips() == ["localhost", "10.0.0.8"]
        assert "http://10.0.0.8:8000" in announce.get_endpoints(8000)

    def test_loopback_addresses_are_never_announced(self, monkeypatch):
        loopbacks = [
            type("IP", (), {"ip": "127.0.0.2"})(),
            type("IP", (), {"ip": "::1"})(),
        ]
        adapter = type("Adapter", (), {"ips": loopbacks})()
        monkeypatch.setattr(announce.ifaddr, "get_adapters", lambda: [adapter])
        monkeypatch.setattr(
            announce.httpx,
            "get",
            raise_when_called(httpx.ConnectError("offline")),
        )

        assert announce.get_endpoints(8000) == []

    @pytest.mark.asyncio
    async def test_relay_startup_reaches_its_normal_path_when_both_sources_fail(
        self, monkeypatch
    ):
        from connectonion.network import relay
        from connectonion.network.host.server import _create_relay_lifespan

        self.deny_adapters(monkeypatch, PermissionError("denied"))
        monkeypatch.setattr(
            announce.httpx,
            "get",
            raise_when_called(httpx.ConnectError("offline")),
        )
        serving = asyncio.Event()

        async def serve_until_shutdown(*args, **kwargs):
            serving.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(relay, "serve_once", serve_until_shutdown)
        on_startup, on_shutdown = _create_relay_lifespan(
            "wss://relay.example",
            {"address": "0x" + "a" * 64},
            "restricted host",
            8000,
            lambda *a, **k: None,
        )

        await on_startup()
        try:
            await asyncio.wait_for(serving.wait(), timeout=0.5)
        finally:
            await on_shutdown()


class TestAWorkingLookupIsStillUsed:

    def test_the_public_address_is_included(self, monkeypatch):
        class _Response:
            text = "203.0.113.7"

        monkeypatch.setattr(announce.httpx, "get", lambda *a, **k: _Response())

        assert "203.0.113.7" in announce.get_ips()

    def test_it_reaches_the_endpoint_list(self, monkeypatch):
        class _Response:
            text = "203.0.113.7"

        monkeypatch.setattr(announce.httpx, "get", lambda *a, **k: _Response())

        assert "http://203.0.113.7:8000" in announce.get_endpoints(8000)

    def test_a_blank_answer_is_not_published_as_an_address(self, monkeypatch):
        """ipify returning an empty body must not add "" to the list."""
        class _Response:
            text = "   "

        monkeypatch.setattr(announce.httpx, "get", lambda *a, **k: _Response())

        assert all(ip.strip() for ip in announce.get_ips())


class TestTheDomainOverrideSkipsItEntirely:
    """With AGENT_PUBLIC_DOMAIN set there is no reason to ask anyone."""

    def test_no_lookup_is_made(self, monkeypatch):
        called = []
        monkeypatch.setenv("AGENT_PUBLIC_DOMAIN", "agent.example.org")
        monkeypatch.setattr(
            announce.ifaddr, "get_adapters", lambda: called.append("local")
        )
        monkeypatch.setattr(
            announce.httpx, "get", lambda *a, **k: called.append("public")
        )

        announce.get_endpoints(8000)

        assert called == []
