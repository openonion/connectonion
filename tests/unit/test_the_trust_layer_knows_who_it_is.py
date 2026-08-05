"""A project without its own key cannot take payment, and does not know its address.

Two places in the trust layer load the agent's key straight from the project
directory. For the projects `co init` and `co create` produce — neither writes a
project key — both come back empty.

**Paid onboarding could never succeed.** `_verify_transfer_via_api` loads keys
to sign the request to oo-api:

    co_dir = project_co_dir()
    keys = addr.load(co_dir)
    if not keys:
        return False

Measured on `main`, in a keyless project:

    project_co_dir(): …/keyless/.co
    address.load(...): None
    => verify_payment returns False before any oo-api call

So a stranger who really did transfer the money was refused, on the agent
configuration that is the common one — and the refusal is indistinguishable
from "you did not pay".

**And the address to pay was not the agent's.** `get_self_address` has the same
shape, so `doors_that_open` advertised either no payment door at all (nothing to
send to) or a stale one from `address.json`.

The answer is the machine identity — the same one `resolve_agent_identity` falls
back to and the host serves under. Not a per-project derived one: an address is
what an OpenOnion account is keyed on (`authenticate` signs with it and the
backend issues the token for that public key), so minting one per project would
give every project an empty balance. That was #715, and Aaron stopped it.
"""

from pathlib import Path

import pytest

from connectonion import address


@pytest.fixture
def keyless_project(tmp_path, monkeypatch):
    """What `co init` leaves: a `.co/` with no keys, beside a machine identity."""
    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    machine = address.generate()
    address.save(machine, home / ".co")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    project = tmp_path / "keyless"
    (project / ".co").mkdir(parents=True)
    monkeypatch.chdir(project)
    return project, machine


class TestItKnowsItsOwnAddress:

    def test_get_self_address_is_not_empty(self, keyless_project):
        from connectonion.network.trust.tools import get_self_address

        assert get_self_address()

    def test_it_is_the_machine_identity(self, keyless_project):
        from connectonion.network.trust.tools import get_self_address

        _, machine = keyless_project

        assert get_self_address() == machine["address"]

    def test_it_is_the_address_the_host_serves(self, keyless_project):
        """The property that matters: what a stranger is told to pay is the
        agent they are paying."""
        from connectonion.network.host.server import resolve_agent_identity
        from connectonion.network.trust.tools import get_self_address

        project, _ = keyless_project

        assert get_self_address() == resolve_agent_identity(project / ".co")["address"]


class TestItCanSignForPaymentVerification:

    def test_a_transfer_check_reaches_the_api(self, keyless_project, monkeypatch):
        """It returned False before making the call at all, so a stranger who
        really had paid was refused."""
        # httpx, not requests — _verify_transfer_via_api imports httpx and
        # fails closed if it is missing. Patching the wrong library made this
        # look like the code still gave up early when it was my fake that was
        # never called.
        import httpx

        from connectonion.network.trust.trust_agent import TrustAgent

        asked = {}

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"verified": True}

        def fake_post(url, **kwargs):
            asked["url"] = url
            return FakeResponse()

        monkeypatch.setattr(httpx, "post", fake_post)

        agent = TrustAgent("careful")
        agent._config = {"onboard": {"payment": 10}}
        monkeypatch.setattr(TrustAgent, "promote_to_contact", lambda self, c: None)

        agent.verify_payment("0x" + "c" * 64, 10)

        assert asked, "no request was made — it gave up before asking oo-api"


class TestAProjectWithItsOwnKeyIsUnchanged:

    def test_its_own_address_wins(self, keyless_project):
        from connectonion.network.trust.tools import get_self_address

        project, _ = keyless_project
        own = address.generate()
        address.save(own, project / ".co")

        assert get_self_address() == own["address"]

    def test_nothing_anywhere_is_not_a_crash(self, tmp_path, monkeypatch):
        from connectonion.network.trust.tools import get_self_address

        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "empty"))
        project = tmp_path / "bare"
        (project / ".co").mkdir(parents=True)
        monkeypatch.chdir(project)

        assert get_self_address() in (None, "")
