"""When an agent offers TLS, use it.

`_sort_endpoints` orders by how close the endpoint is and nothing else:

    def priority(url):
        if "localhost" in url or "127.0.0.1" in url: return 0
        if "192.168." in url or "10." in url or "172.16." in url: return 1
        return 2

So for an agent announcing both schemes on one host, the winner is whichever
the relay happened to list first — and it lists plaintext first:

    >>> _sort_endpoints(['http://agent.example.com:8000',
    ...                  'https://agent.example.com:8000'])
    ['http://agent.example.com:8000', 'https://agent.example.com:8000']

`resolve_endpoint` then takes the first one it can verify, so the connection is
made in the clear to an agent that offered TLS.

That matters more than it used to. What travels on that connection is a signed
CONNECT, and #649 measured what a captured one is worth: `EXEC` carries no
signature of its own, so within the five-minute freshness window a replayed
CONNECT opens a session on which *any* whitelisted tool can be run with any
arguments. Before #643 this never came up, because endpoint resolution always
failed and every client went through the relay over `wss://`.

Closeness still wins over scheme: a plaintext loopback connection has no network
to be observed on, and that is the case direct resolution exists for. This only
decides between endpoints that are equally close.

The whole answer to #649 is not here — an agent that offers no TLS at all still
speaks plaintext across a LAN, and that is the trade filed there. This is the
part with no trade in it.
"""

import pytest

from connectonion.network.connect import _sort_endpoints


LOCAL_PLAIN = "http://localhost:8000"
LAN_PLAIN = "http://10.0.0.5:8000"
LAN_TLS = "https://10.0.0.5:8000"
PUBLIC_PLAIN = "http://agent.example.com:8000"
PUBLIC_TLS = "https://agent.example.com:8000"


def _first(endpoints):
    return _sort_endpoints(endpoints)[0]


class TestTlsWinsAmongEquals:

    def test_one_host_offering_both(self):
        assert _first([PUBLIC_PLAIN, PUBLIC_TLS]) == PUBLIC_TLS

    def test_the_order_they_were_announced_in_does_not_decide_it(self):
        assert _first([PUBLIC_TLS, PUBLIC_PLAIN]) == PUBLIC_TLS

    def test_on_the_local_network_too(self):
        assert _first([LAN_PLAIN, LAN_TLS]) == LAN_TLS

    def test_the_websocket_forms_sort_the_same_way(self):
        assert _first(["ws://10.0.0.5:8000/ws", "wss://10.0.0.5:8000/ws"]) == "wss://10.0.0.5:8000/ws"


class TestClosenessStillDecidesFirst:
    """A plaintext loopback connection has no network to be observed on, and
    reaching an agent on this machine is what direct resolution is for."""

    def test_plaintext_localhost_beats_tls_on_the_public_internet(self):
        assert _first([PUBLIC_TLS, LOCAL_PLAIN]) == LOCAL_PLAIN

    def test_plaintext_lan_beats_tls_public(self):
        assert _first([PUBLIC_TLS, LAN_PLAIN]) == LAN_PLAIN

    def test_the_three_tiers_are_unchanged(self):
        ordered = _sort_endpoints([PUBLIC_PLAIN, LAN_PLAIN, LOCAL_PLAIN])

        assert ordered == [LOCAL_PLAIN, LAN_PLAIN, PUBLIC_PLAIN]


class TestWhatMustNotChange:

    def test_nothing_is_dropped(self):
        endpoints = [PUBLIC_PLAIN, LAN_TLS, LOCAL_PLAIN, PUBLIC_TLS, LAN_PLAIN]

        assert sorted(_sort_endpoints(endpoints)) == sorted(endpoints)

    def test_an_empty_list_is_fine(self):
        assert _sort_endpoints([]) == []

    def test_a_single_endpoint_is_returned(self):
        assert _sort_endpoints([LAN_PLAIN]) == [LAN_PLAIN]

    def test_endpoints_of_the_same_locality_and_scheme_keep_their_order(self):
        a, b = "http://10.0.0.5:8000", "http://10.0.0.6:8000"

        assert _sort_endpoints([a, b]) == [a, b]
