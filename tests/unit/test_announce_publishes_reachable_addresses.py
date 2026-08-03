"""What an agent tells a public directory about where to find it.

`get_endpoints` published a URL for every address on the machine, loopback
included. Fetched from the relay for a live agent, by anyone who asks:

    http://localhost:8001          ws://localhost:8001/ws
    http://10.152.0.16:8001        ws://10.152.0.16:8001/ws
    http://34.151.137.226:8001     ws://34.151.137.226:8001/ws

`localhost` is not a place another machine can go. Published to a public
directory it is worse than useless: a browser client that walks the list probes
port 8001 on **the reader's own machine**, and the address check is the only
thing that stopped it talking to whatever answered. That was fixed on the
client side in @connectonion/react 0.3.2; this is the same bug at the source.

The private address is left in on purpose — two agents in one VPC or on one LAN
can use it, and that is a real connection the relay would otherwise have to
carry. It is a judgement call rather than an oversight, so it is written down
here.
"""

import pytest

from connectonion.network import announce


class TestLoopbackIsNotAPlaceToVisit:

    def test_it_is_not_in_the_published_endpoints(self, monkeypatch):
        monkeypatch.setattr(announce, 'get_ips',
                            lambda: ['localhost', '10.0.0.5', '203.0.113.9'])

        published = announce.get_endpoints(8001)

        assert not [e for e in published if 'localhost' in e], published

    @pytest.mark.parametrize("loopback", ['localhost', '127.0.0.1', '::1',
                                          '127.0.1.1'])
    def test_every_spelling_of_it(self, monkeypatch, loopback):
        monkeypatch.setattr(announce, 'get_ips', lambda: [loopback, '203.0.113.9'])

        published = announce.get_endpoints(8001)

        assert all('203.0.113.9' in e for e in published), published


class TestWhatIsStillPublished:

    def test_the_public_address_is(self, monkeypatch):
        monkeypatch.setattr(announce, 'get_ips', lambda: ['localhost', '203.0.113.9'])

        published = announce.get_endpoints(8001)

        assert 'http://203.0.113.9:8001' in published
        assert 'ws://203.0.113.9:8001/ws' in published

    def test_a_private_address_still_is(self, monkeypatch):
        """Deliberate: two agents in one VPC can use it, and the relay would
        otherwise carry a connection that did not need it."""
        monkeypatch.setattr(announce, 'get_ips', lambda: ['localhost', '10.0.0.5'])

        assert 'http://10.0.0.5:8001' in announce.get_endpoints(8001)

    def test_a_configured_domain_still_wins_outright(self, monkeypatch):
        monkeypatch.setenv('AGENT_PUBLIC_DOMAIN', 'agent.example.com')

        assert announce.get_endpoints(8001) == ['https://agent.example.com',
                                                'wss://agent.example.com/ws']

    def test_an_agent_with_only_loopback_publishes_nothing(self, monkeypatch):
        """A laptop with no route out announces no direct endpoint and is
        reached through the relay — which is what already happens when every
        published endpoint fails, only without the wasted probes."""
        monkeypatch.setattr(announce, 'get_ips', lambda: ['localhost'])

        assert announce.get_endpoints(8001) == []
