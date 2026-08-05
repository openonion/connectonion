"""One captured CONNECT is five minutes of the whole whitelisted tool surface.

#649, measured against a live agent. `CONNECT` carries a signed payload;
`EXEC` carries no signature at all:

    exec_msg = {"type": "EXEC", "exec_id": exec_id, "tool": tool, "args": args}

So the signature authenticates the *connection*, and every command on it is
trusted because of who opened it. `SIGNATURE_EXPIRY_SECONDS = 300`, and nothing
marked a signature as used. The EXEC frames in that measurement were written by
the attacker, not captured:

    1st (legitimate)                 -> ran 1 times
    2nd (CONNECT replayed verbatim)  -> ran 2 times
    3rd (replayed again)             -> ran 3 times

Two things are fixed here, neither of them a protocol change.

**A CONNECT signature opens one connection.** Seen once, refused after. The
attack needs to *open* a connection; without a MITM position an attacker cannot
inject into someone else's existing socket. Legitimate clients build a fresh
CONNECT with a fresh timestamp every time, and the one place this codebase
re-establishes a connection deliberately avoids replaying the frame -- the
comment in connect.py says so: "no CONNECT replay -- its signature may have
aged past the 5-minute window".

**Nothing signed goes onto a network in plaintext.** #643 made direct
resolution work, and a self-hosted agent announces plain `ws://`. On a LAN
anyone who can observe the traffic can capture a CONNECT. Plaintext is now used
only for loopback, where there is no network to observe; a `wss://` endpoint is
preferred when offered, and otherwise the relay carries it.

What is *not* fixed here is signing each command (#649's option 3). That is the
complete answer and a protocol change: every EXEC and INPUT carrying its own
signature over its own contents. These two close the route without breaking a
single client.
"""

import time

import pytest

from connectonion import address


@pytest.fixture
def keys():
    return address.generate()


def _connect_frame(keys, to: str, timestamp=None):
    import json

    payload = {"to": to, "timestamp": int(timestamp or time.time())}
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return {"type": "CONNECT", "payload": payload, "from": keys["address"],
            "signature": address.sign(keys, canonical.encode()).hex()}


class TestASignatureOpensOneConnection:

    def test_the_first_use_is_accepted(self, keys):
        from connectonion.network.host.auth import signature_already_used

        frame = _connect_frame(keys, "0x" + "a" * 64)

        assert signature_already_used(frame) is False

    def test_the_second_use_is_refused(self, keys):
        """The measurement in the issue: replayed verbatim, ran again."""
        from connectonion.network.host.auth import signature_already_used

        frame = _connect_frame(keys, "0x" + "a" * 64)
        signature_already_used(frame)

        assert signature_already_used(frame) is True

    def test_a_fresh_frame_from_the_same_caller_is_fine(self, keys):
        """What every legitimate reconnect looks like."""
        from connectonion.network.host.auth import signature_already_used

        signature_already_used(_connect_frame(keys, "0x" + "a" * 64, time.time() - 2))

        assert signature_already_used(
            _connect_frame(keys, "0x" + "a" * 64, time.time())) is False

    def test_two_callers_do_not_collide(self, keys):
        from connectonion.network.host.auth import signature_already_used

        other = address.generate()
        signature_already_used(_connect_frame(keys, "0x" + "a" * 64))

        assert signature_already_used(_connect_frame(other, "0x" + "a" * 64)) is False

    def test_an_unsigned_frame_is_not_tracked(self, keys):
        """It is refused earlier, by the signature check itself."""
        from connectonion.network.host.auth import signature_already_used

        assert signature_already_used({"type": "CONNECT"}) is False

    def test_the_cache_does_not_grow_without_bound(self, keys):
        """Entries past the freshness window cannot be replayed anyway, so
        keeping them is memory an agent never gets back.

        The cache stamps *insertion* time, not the frame's timestamp -- so a
        far-future timestamp cannot pin an entry there. Ageing the recorded
        times is therefore how this is exercised; my first version pushed
        old-looking frames instead and kept 51 entries, proving nothing.
        """
        from connectonion.network.host.auth import (SIGNATURE_EXPIRY_SECONDS,
                                                    _seen_signatures,
                                                    signature_already_used)

        _seen_signatures.clear()
        for _ in range(50):
            signature_already_used(_connect_frame(address.generate(), "0x" + "a" * 64))
        aged = time.time() - SIGNATURE_EXPIRY_SECONDS - 60
        for sig in _seen_signatures:
            _seen_signatures[sig] = aged

        signature_already_used(_connect_frame(keys, "0x" + "a" * 64))

        assert len(_seen_signatures) == 1, f"{len(_seen_signatures)} entries kept"


class TestNothingSignedGoesOntoALanInPlaintext:
    """#643 made direct resolution work; a self-hosted agent announces ws://."""

    def test_loopback_plaintext_is_fine(self):
        from connectonion.network.connect import endpoint_is_safe

        assert endpoint_is_safe("http://localhost:8000") is True
        assert endpoint_is_safe("http://127.0.0.1:8000") is True

    def test_a_lan_address_in_plaintext_is_not(self):
        """The exact shape from the issue's measurement."""
        from connectonion.network.connect import endpoint_is_safe

        assert endpoint_is_safe("http://10.5.27.133:8797") is False

    def test_a_public_address_in_plaintext_is_not(self):
        from connectonion.network.connect import endpoint_is_safe

        assert endpoint_is_safe("http://129.94.128.29:8000") is False

    def test_tls_anywhere_is_fine(self):
        from connectonion.network.connect import endpoint_is_safe

        assert endpoint_is_safe("https://agent.example.com") is True
        assert endpoint_is_safe("https://10.5.27.133:8797") is True

    def test_ipv6_loopback_counts(self):
        from connectonion.network.connect import endpoint_is_safe

        assert endpoint_is_safe("http://[::1]:8000") is True


class TestWhichEndpointIsChosen:
    """The preference order, given what a relay actually returns."""

    def _resolve(self, endpoints, agent_address="0x" + "b" * 64):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        import importlib

        # `connectonion.network.connect` is also the name of a function the
        # package re-exports, so the dotted attribute is that function and not
        # this module. Same shadowing that made a monkeypatch land nowhere in
        # #687's tests.
        connect_mod = importlib.import_module("connectonion.network.connect")

        directory = MagicMock()
        directory.status_code = 200
        directory.json.return_value = {"endpoints": endpoints}

        info = MagicMock()
        info.status_code = 200
        info.json.return_value = {"address": agent_address}

        async def get(url, *a, **kw):
            return directory if "/api/agents/" in url else info

        client = MagicMock()
        client.get = AsyncMock(side_effect=get)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(connect_mod.httpx, "AsyncClient", return_value=client):
            return asyncio.run(connect_mod.resolve_endpoint(agent_address,
                                                            "wss://relay.example"))

    def test_a_lan_plaintext_endpoint_is_not_used(self):
        assert self._resolve(["http://10.5.27.133:8797"]) is None

    def test_localhost_still_wins(self):
        assert self._resolve(["http://10.5.27.133:8797",
                              "http://localhost:8000"]) == "ws://localhost:8000/ws"

    def test_tls_is_used_over_the_relay(self):
        assert self._resolve(["https://agent.example.com"]) == "wss://agent.example.com/ws"

    def test_tls_is_preferred_over_lan_plaintext(self):
        assert self._resolve(["http://10.5.27.133:8797",
                              "https://agent.example.com"]) == "wss://agent.example.com/ws"
