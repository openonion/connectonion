"""What the client hears when the agent's own config is broken.

#585 made an unreadable trust list raise instead of quietly answering "not
blocked". That was right — a blocklist that cannot be read was admitting
everyone on it — but it moved the failure somewhere with no exit.

`auth.py` documents its contract as:

    Errors: returns error strings: "unauthorized: ...", "forbidden: ..."
            | does NOT raise exceptions

and the WebSocket session loop documents the other side of it:

    other exceptions propagate out (transport-level errors, programmer bugs)

So a GBK-saved blocklist.txt now kills the connection with nothing sent. The
client sees a socket close and no reason — which is exactly the shape of #434,
arriving by a new route.

An agent whose config it cannot read should say so, to the person holding the
other end of the socket, and refuse. Not guess, and not vanish.
"""

import importlib
import json
import time

import pytest

from connectonion.network.host.auth import extract_and_authenticate

tools = importlib.import_module('connectonion.network.trust.tools')


def _signed_request(tmp_path):
    """A properly signed CONNECT, so the failure under test is the list read."""
    from nacl.signing import SigningKey

    key = SigningKey.generate()
    address = "0x" + key.verify_key.encode().hex()
    payload = {"prompt": "hello", "timestamp": time.time()}
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return {
        "payload": payload,
        "from": address,
        "signature": key.sign(canonical.encode()).signature.hex(),
    }


@pytest.fixture
def agent_with_a_broken_blocklist(tmp_path, monkeypatch):
    co = tmp_path / '.co'
    co.mkdir()
    # What a Windows editor saving as GBK leaves behind.
    (co / 'blocklist.txt').write_bytes(b'\xd6\xd0\xce\xc4\n')
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestTheClientIsToldRatherThanDropped:

    def test_it_does_not_raise_out_of_the_auth_boundary(
            self, agent_with_a_broken_blocklist):
        """The module's documented contract, and the socket's only chance to
        say anything."""
        from connectonion.network.trust import TrustAgent

        prompt, address, sig_ok, error = extract_and_authenticate(
            _signed_request(agent_with_a_broken_blocklist), TrustAgent('careful'))

        assert error, "a broken blocklist produced no error for the client"

    def test_the_error_names_the_file(self, agent_with_a_broken_blocklist):
        from connectonion.network.trust import TrustAgent

        _, _, _, error = extract_and_authenticate(
            _signed_request(agent_with_a_broken_blocklist), TrustAgent('careful'))

        assert 'blocklist' in error, (
            f"the operator has to know which file to fix; got: {error!r}"
        )

    def test_it_refuses_rather_than_admits(self, agent_with_a_broken_blocklist):
        """Fail closed. The list that could not be read is a deny list."""
        from connectonion.network.trust import TrustAgent

        prompt, _, _, error = extract_and_authenticate(
            _signed_request(agent_with_a_broken_blocklist), TrustAgent('careful'))

        assert prompt is None
        assert error


class TestAWorkingAgentIsUnaffected:

    def test_a_readable_list_still_authenticates(self, tmp_path, monkeypatch):
        from connectonion.network.trust import TrustAgent

        co = tmp_path / '.co'
        co.mkdir()
        (co / 'blocklist.txt').write_text('')
        monkeypatch.setenv('HOME', str(tmp_path / 'home'))
        monkeypatch.chdir(tmp_path)

        _, _, sig_ok, error = extract_and_authenticate(
            _signed_request(tmp_path), TrustAgent('open'))

        assert sig_ok
        assert error is None
