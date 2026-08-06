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

import httpx
import pytest

from connectonion.network import announce


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
            announce.httpx, "get", lambda *a, **k: called.append(1)
        )

        announce.get_endpoints(8000)

        assert called == []
