"""The buyer names the price, and the agent accepts it.

`handle_onboard_submit` takes the amount out of the client's own frame:

    payload = data.get("payload", {})
    payment = payload.get("payment", 0)
    ...
    if payment > 0:
        if trust_agent.verify_payment(agent_address, payment):

and `verify_payment` prefers it over the configured one:

    required = self._config.get('onboard', {}).get('payment')
    if not required:
        return False
    # Use configured amount if not specified
    min_amount = amount if amount > 0 else required

The comment says "if not specified", but the caller above only reaches this
when `payment > 0`, so `amount` is *always* specified and `required` is never
the minimum. It survives only as a truthiness check for whether payment
onboarding is configured at all.

So an agent advertising 10 is opened by a transfer of 0.01, from a stranger who
sends `{"payment": 0.01}` and makes that transfer. oo-api confirms it honestly
— it was asked to confirm 0.01 — and `promote_to_contact` runs. On `careful`,
contacts are allowed.

The price is the operator's to set. What the client sends is at most a claim
about what they did, and a claim is not an authorisation.

Found while removing the shipped default price (#672): the two halves of one
gate, the same shape as #561 and #571 — a value that is advertised and a value
that is enforced, resolved in two places, and the enforcing one reads something
the operator never wrote.
"""

from unittest.mock import patch

import pytest

from connectonion.network.trust.trust_agent import TrustAgent


CLIENT = "0x" + "c" * 64
SELF = "0x" + "a" * 64


@pytest.fixture
def agent_charging_ten(tmp_path):
    """An agent whose operator set the price at 10."""
    agent = TrustAgent("careful")
    agent._config = {"onboard": {"payment": 10}}
    return agent


@pytest.fixture
def transfers_seen():
    """Record what oo-api was asked to confirm, and confirm it."""
    seen = []

    def fake_verify(self, from_addr, to_addr, min_amount):
        seen.append(min_amount)
        return True

    with patch.object(TrustAgent, "_verify_transfer_via_api", fake_verify), \
         patch.object(TrustAgent, "get_self_address", lambda self: SELF), \
         patch.object(TrustAgent, "promote_to_contact", lambda self, c: None):
        yield seen


class TestTheOperatorSetsThePrice:

    def test_a_penny_does_not_open_a_ten_door(self, agent_charging_ten, transfers_seen):
        agent_charging_ten.verify_payment(CLIENT, 0.01)

        assert transfers_seen == [10], (
            f"oo-api was asked to confirm {transfers_seen} — the buyer's number"
        )

    def test_paying_the_asking_price_works(self, agent_charging_ten, transfers_seen):
        assert agent_charging_ten.verify_payment(CLIENT, 10) is True
        assert transfers_seen == [10]

    def test_offering_more_does_not_raise_the_bar(self, agent_charging_ten, transfers_seen):
        """The operator asked for 10. A client that says 500 has still only
        agreed to 10, and requiring 500 would refuse a valid payment."""
        agent_charging_ten.verify_payment(CLIENT, 500)

        assert transfers_seen == [10]

    def test_saying_nothing_still_charges_the_asking_price(self, agent_charging_ten,
                                                           transfers_seen):
        agent_charging_ten.verify_payment(CLIENT, 0)

        assert transfers_seen == [10]


class TestNoPriceConfiguredIsNoSale:

    def test_an_agent_that_charges_nothing_refuses(self, transfers_seen):
        agent = TrustAgent("careful")
        agent._config = {"onboard": {}}

        assert agent.verify_payment(CLIENT, 50) is False
        assert transfers_seen == [], "it asked oo-api about an agent with no price"

    def test_an_unresolved_switch_is_no_sale(self, transfers_seen, monkeypatch):
        """What careful.md now ships. An unset $CO_PAYMENT is not a price."""
        monkeypatch.delenv("CO_PAYMENT", raising=False)
        agent = TrustAgent("careful")
        agent._config = {"onboard": {"payment": "$CO_PAYMENT"}}

        assert agent.verify_payment(CLIENT, 50) is False
        assert transfers_seen == []

    def test_a_configured_switch_charges_what_it_resolves_to(self, transfers_seen,
                                                             monkeypatch):
        monkeypatch.setenv("CO_PAYMENT", "25")
        agent = TrustAgent("careful")
        agent._config = {"onboard": {"payment": "$CO_PAYMENT"}}

        assert agent.verify_payment(CLIENT, 1) is True
        assert transfers_seen == [25]


class TestTheAdvertisedPriceIsTheChargedPrice:
    """Two places resolve this. They have to agree, or the stranger pays what
    they were told and is refused."""

    def test_what_is_advertised_is_what_is_required(self, transfers_seen, monkeypatch):
        from connectonion.network.trust.ws_admin import doors_that_open

        monkeypatch.setenv("CO_PAYMENT", "25")
        onboard = {"payment": "$CO_PAYMENT"}

        advertised = doors_that_open(onboard, SELF)["payment_amount"]

        agent = TrustAgent("careful")
        agent._config = {"onboard": onboard}
        agent.verify_payment(CLIENT, advertised)

        assert transfers_seen == [advertised]
