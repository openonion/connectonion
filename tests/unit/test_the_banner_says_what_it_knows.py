"""The startup banner states what is configured, not what has succeeded.

Two lines assert more than the process knows at the moment they print:

    ↳ chat.openonion.ai ↗
    ✓ relay

`✓ relay` is `"✓ relay" if relay_url else "no relay"` — a green tick for
"a URL is set", printed before any connection is attempted. Against a relay
that refuses instantly it still printed the tick, and the operator reading it
has been told their agent is reachable.

`chat_url` is `f"https://chat.openonion.ai/{address}"` regardless of which
relay the agent announces on. That was accidentally true while every agent was
on the public relay; #626 made a private `relay_url` in host.yaml actually
work, so now it can point at a site that has never heard of the agent.

Neither is a lie the code could have caught: the banner prints during startup,
before the relay loop has connected to anything. So it should say what it has —
the relay it is about to use — and leave success to the lines that know:
`relay connection error …`, `relay reconnected`, and the `♥` for a terminal.
"""

import re

import pytest

from connectonion.network.host.server import DEFAULT_RELAY_URL, _print_host_banner


ADDRESS = "0x" + "a" * 64
PRIVATE = "wss://relay.example.internal/ws"


def _banner(capsys, relay_url) -> str:
    _print_host_banner(port=8000, address=ADDRESS, relay_url=relay_url,
                       trust="careful", trust_config={}, co_dir=None)
    out = capsys.readouterr()
    return out.out + out.err


class TestNoTickForSomethingUntried:

    def test_the_public_relay_gets_no_success_mark(self, capsys):
        banner = _banner(capsys, DEFAULT_RELAY_URL)

        assert "✓ relay" not in banner, banner

    def test_a_private_relay_gets_no_success_mark(self, capsys):
        banner = _banner(capsys, PRIVATE)

        assert "✓ relay" not in banner, banner


class TestItStillSaysWhichRelay:

    def test_the_public_one_is_named(self, capsys):
        banner = _banner(capsys, DEFAULT_RELAY_URL)

        assert "oo.openonion.ai" in banner

    def test_a_private_one_is_named(self, capsys):
        banner = _banner(capsys, PRIVATE)

        assert "relay.example.internal" in banner

    def test_no_relay_still_says_so(self, capsys):
        banner = _banner(capsys, None)

        assert "no relay" in banner


class TestTheChatLinkMatchesTheRelay:

    def test_it_is_shown_for_the_public_relay(self, capsys):
        """That is the site that can find an agent announced there."""
        banner = _banner(capsys, DEFAULT_RELAY_URL)

        assert "chat.openonion.ai" in banner

    def test_it_is_not_shown_for_a_private_relay(self, capsys):
        """chat.openonion.ai cannot reach an agent that never announced to it."""
        banner = _banner(capsys, PRIVATE)

        assert "chat.openonion.ai" not in banner, banner

    def test_it_is_not_shown_without_a_relay(self, capsys):
        banner = _banner(capsys, None)

        assert "chat.openonion.ai" not in banner, banner


class TestWhatTheBannerIsFor:

    def test_the_address_is_still_there(self, capsys):
        assert ADDRESS in _banner(capsys, DEFAULT_RELAY_URL)

    def test_the_local_url_is_still_there(self, capsys):
        assert "localhost:8000" in _banner(capsys, DEFAULT_RELAY_URL)
