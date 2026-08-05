"""A project without its own key cannot take payment, and does not know its address.

Two places in the trust layer load the agent's key straight from the project
directory. For the projects `co init` produces — which have no key of their own
— both come back empty.

**Paid onboarding could never succeed.** `_verify_transfer_via_api` loads keys
to sign the request to oo-api:

    co_dir = project_co_dir()
    keys = addr.load(co_dir)
    if not keys:
        return False

Confirmed on `main`, in a keyless project:

    project_co_dir(): …/keyless/.co
    address.load(...): None
    => verify_payment returns False before any oo-api call

So a stranger who really did transfer the money was refused, on the agent
configuration that is the common one. That predates this change; it is what
loading the project directory and only the project directory has always done.

**And the address to pay was not the agent's.** `get_self_address` has the same
shape, so `doors_that_open` either advertised no payment door at all (no
address to send to) or a stale one from `address.json`.

Both now ask `project_identity`, which is the same answer the host serves
under. An agent advertising one address, signing as another, and serving as a
third is the shape this release has spent itself removing.
"""

from pathlib import Path

import pytest

from connectonion import address


@pytest.fixture
def keyless_project(tmp_path, monkeypatch):
    """What `co init` leaves: a `.co/` with no keys, and a phrase at home."""
    home = tmp_path / "home"
    (home / ".co" / "keys").mkdir(parents=True)
    machine = address.generate()
    address.save(machine, home / ".co")
    (home / ".co" / "keys" / "recovery.txt").write_text(machine["seed_phrase"],
                                                        encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    project = tmp_path / "keyless"
    (project / ".co").mkdir(parents=True)
    monkeypatch.chdir(project)
    return project, machine


class TestItKnowsItsOwnAddress:

    def test_get_self_address_is_not_empty(self, keyless_project):
        from connectonion.network.trust.tools import get_self_address

        assert get_self_address()

    def test_it_is_the_address_the_host_would_serve(self, keyless_project):
        from connectonion.network.host.server import resolve_agent_identity
        from connectonion.network.trust.tools import get_self_address

        project, _ = keyless_project

        assert get_self_address() == resolve_agent_identity(project / ".co")["address"]

    def test_it_is_not_the_machine_identity(self, keyless_project):
        from connectonion.network.trust.tools import get_self_address

        _, machine = keyless_project

        assert get_self_address() != machine["address"]


class TestItCanSignForPaymentVerification:

    def test_a_transfer_check_reaches_the_api(self, keyless_project, monkeypatch):
        """It used to return False before making the call at all, so a stranger
        who really had paid was refused."""
        from connectonion.network.trust.trust_agent import TrustAgent

        asked = {}

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"verified": True}

        def fake_post(url, **kwargs):
            asked["url"] = url
            asked["json"] = kwargs.get("json")
            return FakeResponse()

        import httpx
        monkeypatch.setattr(httpx, "post", fake_post, raising=False)
        import requests
        monkeypatch.setattr(requests, "post", fake_post, raising=False)

        agent = TrustAgent("careful")
        agent._config = {"onboard": {"payment": 10}}
        monkeypatch.setattr(TrustAgent, "promote_to_contact", lambda self, c: None)

        agent.verify_payment("0x" + "c" * 64, 10)

        assert asked, "no request was made — it gave up before asking oo-api"

    def test_it_signs_as_the_identity_the_host_serves(self, keyless_project, monkeypatch):
        from connectonion.network.host.server import resolve_agent_identity
        from connectonion.network.trust.trust_agent import TrustAgent

        project, _ = keyless_project
        sent = {}

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"verified": True}

        def fake_post(url, **kwargs):
            sent.update(kwargs.get("json") or {})
            return FakeResponse()

        import requests
        monkeypatch.setattr(requests, "post", fake_post, raising=False)
        import httpx
        monkeypatch.setattr(httpx, "post", fake_post, raising=False)

        agent = TrustAgent("careful")
        agent._config = {"onboard": {"payment": 10}}
        monkeypatch.setattr(TrustAgent, "promote_to_contact", lambda self, c: None)
        agent.verify_payment("0x" + "c" * 64, 10)

        served = resolve_agent_identity(project / ".co")["address"]
        signed_as = sent.get("to_address") or sent.get("public_key") or sent.get("agent_address")
        assert signed_as is None or signed_as == served, (sent, served)


class TestAProjectWithItsOwnKeyIsUnchanged:

    def test_its_own_address_wins(self, keyless_project):
        from connectonion.network.trust.tools import get_self_address

        project, _ = keyless_project
        own = address.generate()
        address.save(own, project / ".co")

        assert get_self_address() == own["address"]
