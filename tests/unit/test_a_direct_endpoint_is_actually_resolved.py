"""Every call goes through the relay, because the gate is on a field nobody sends.

`resolve_endpoint` picks the best way to reach an agent — localhost, then LAN,
then public — and falls back to the relay when it finds nothing. It has never
found anything:

    if not agent_info.get("online") or not agent_info.get("endpoints"):
        return None

The relay does not return `online`. Measured against a live agent announced on
`wss://oo.openonion.ai`:

    GET https://oo.openonion.ai/api/agents/0xe8eab6d…
    {
      "endpoints": ["http://10.5.27.133:8797", "ws://10.5.27.133:8797/ws",
                    "http://129.94.128.29:8797", "ws://129.94.128.29:8797/ws"],
      "relay": "wss://oo.openonion.ai",
      "last_seen": "2026-08-04T01:42:26.777916",
      "profile": {"alias": "proj-e2e", "model": "gemini-2.5-flash", "tools": ["ping"]}
    }

    >>> resolve_endpoint(addr, "wss://oo.openonion.ai")
    None

    >>> GET http://10.5.27.133:8797/info
    {"address": "0xe8eab6d…", "name": "proj-e2e"}      # answering the whole time

So `_sort_endpoints` and its localhost-first ordering have never run, and an
agent on the same machine as its caller is reached over the public relay. It
works, which is why nobody noticed — it is slower than it needs to be, and it
depends on a relay that this session watched drop connections for twenty
minutes at a time.

`online` is not required now. It is still honoured when the relay says it
explicitly: a `False` means the relay knows the agent is gone, and trying four
endpoints to rediscover that costs a timeout each. Absent means no opinion.

The check that actually establishes liveness was never `online` anyway — each
candidate is fetched and its `/info` address must match the agent being looked
for. That is stronger than a flag, and it stays.
"""

import asyncio

import pytest

import importlib

# `connectonion.network.connect` names both a module and the function inside it,
# and `from connectonion.network import connect` gives the function. The module
# is what has the httpx attribute this patches.
connect_module = importlib.import_module("connectonion.network.connect")
resolve_endpoint = connect_module.resolve_endpoint
_sort_endpoints = connect_module._sort_endpoints


AGENT = "0x" + "c" * 64
OTHER = "0x" + "d" * 64


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeClient:
    """Answers /api/agents/{addr} with `directory`, and /info per host."""

    def __init__(self, directory, info_by_host):
        self.directory = directory
        self.info_by_host = info_by_host
        self.asked = []

    async def get(self, url, *a, **k):
        self.asked.append(url)
        if "/api/agents/" in url:
            return FakeResponse(self.directory)
        host = url.rsplit("/info", 1)[0]
        if host in self.info_by_host:
            return FakeResponse(self.info_by_host[host])
        return FakeResponse({}, status_code=404)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _resolve(monkeypatch, directory, info_by_host=None):
    client = FakeClient(directory, info_by_host or {})
    monkeypatch.setattr(connect_module.httpx, "AsyncClient", lambda *a, **k: client)
    result = asyncio.run(resolve_endpoint(AGENT, "wss://relay.test", timeout=1))
    return result, client


# Served over TLS. Since #649 a signed CONNECT is only sent to loopback in
# plaintext, so a bare `http://` LAN or public endpoint is skipped and these
# tests -- which are about ordering and resolution mechanics, not schemes --
# would be testing the refusal instead. `test_a_captured_connect_opens_nothing_twice.py`
# is where the refusal itself is pinned.
LAN = "https://10.0.0.5:8797"
PUBLIC = "https://203.0.113.9:8797"
LOCAL = "http://localhost:8797"


class TestWhatTheRelayActuallyReturns:
    """No `online` key — the shape measured against the production relay."""

    DIRECTORY = {
        "endpoints": [LAN, "ws://10.0.0.5:8797/ws"],
        "relay": "wss://relay.test",
        "last_seen": "2026-08-04T01:42:26.777916",
        "profile": {"alias": "a"},
    }

    def test_an_endpoint_is_resolved(self, monkeypatch):
        result, _ = _resolve(monkeypatch, self.DIRECTORY, {LAN: {"address": AGENT}})

        assert result is not None

    def test_it_is_the_websocket_form(self, monkeypatch):
        result, _ = _resolve(monkeypatch, self.DIRECTORY, {LAN: {"address": AGENT}})

        assert result == "wss://10.0.0.5:8797/ws"


class TestAnExplicitNoIsStillHonoured:
    """A relay that does say `online` is not being second-guessed."""

    def test_online_false_resolves_nothing(self, monkeypatch):
        result, _ = _resolve(monkeypatch,
                             {"online": False, "endpoints": [LAN]},
                             {LAN: {"address": AGENT}})

        assert result is None

    def test_online_false_does_not_even_probe(self, monkeypatch):
        _, client = _resolve(monkeypatch,
                             {"online": False, "endpoints": [LAN]},
                             {LAN: {"address": AGENT}})

        assert not [u for u in client.asked if u.endswith("/info")]

    def test_online_true_still_resolves(self, monkeypatch):
        result, _ = _resolve(monkeypatch,
                             {"online": True, "endpoints": [LAN]},
                             {LAN: {"address": AGENT}})

        assert result is not None


class TestTheChecksThatMustStay:

    def test_no_endpoints_is_nothing_to_resolve(self, monkeypatch):
        result, _ = _resolve(monkeypatch, {"endpoints": []})

        assert result is None

    def test_an_endpoint_answering_for_another_agent_is_refused(self, monkeypatch):
        """The real liveness-and-identity check: /info must name this agent."""
        result, _ = _resolve(monkeypatch, {"endpoints": [LAN]}, {LAN: {"address": OTHER}})

        assert result is None

    def test_an_endpoint_that_does_not_answer_is_skipped(self, monkeypatch):
        result, _ = _resolve(monkeypatch, {"endpoints": [LAN, PUBLIC]},
                             {PUBLIC: {"address": AGENT}})

        assert result == "wss://203.0.113.9:8797/ws"

    def test_a_short_address_is_not_looked_up(self, monkeypatch):
        client = FakeClient({}, {})
        monkeypatch.setattr(connect_module.httpx, "AsyncClient", lambda *a, **k: client)

        assert asyncio.run(resolve_endpoint("0xshort", "wss://relay.test")) is None
        assert not client.asked


class TestTheOrderingThatHasNeverRun:
    """localhost before LAN before public — dead code until now."""

    def test_localhost_wins(self, monkeypatch):
        result, _ = _resolve(monkeypatch, {"endpoints": [PUBLIC, LOCAL, LAN]},
                             {LOCAL: {"address": AGENT}, LAN: {"address": AGENT},
                              PUBLIC: {"address": AGENT}})

        assert "localhost" in result

    def test_lan_beats_public(self, monkeypatch):
        result, _ = _resolve(monkeypatch, {"endpoints": [PUBLIC, LAN]},
                             {LAN: {"address": AGENT}, PUBLIC: {"address": AGENT}})

        assert "10.0.0.5" in result

    def test_the_sort_itself(self):
        assert _sort_endpoints([PUBLIC, LAN, LOCAL])[0] == LOCAL
