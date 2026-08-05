"""Every agent sells access for 10 without its operator asking.

The shipped `careful` policy is the default for every agent, and it carries a
payment door as a bare literal:

    onboard:
      # Read from the environment, so every agent has its own. A literal here
      # would be one password for every deployment, published in this repo.
      invite_code: [$CO_INVITE_CODE]
      payment: 10

Measured on an agent created by `co init` and hosted with defaults, whose
host.yaml has no `onboard:` block at all:

    GET /info    "onboard": {"invite_code": true, "payment": 10}

The door is wired end to end — ONBOARD_SUBMIT -> verify_payment ->
_verify_transfer_via_api -> promote_to_contact — and on `careful` contacts are
allowed. So a stranger who transfers 10 to the operator's address is admitted
to an agent whose operator never asked for payment onboarding. Paid to an
address that, for a project with no key of its own, is the machine's inherited
identity rather than the one the operator thinks of as this agent's (#642).

The two lines are not written to the same standard. `invite_code` reads from
the environment *specifically so a shipped literal is not one password for
every deployment* — the lesson of #561 — and resolves to nothing when unset, so
it is opt-in and fails closed. `payment` is a literal: nothing to set, nothing
to unset, on for everyone.

Aaron's call: which door an agent opens is a decision made when it is
published, in its trust config. Some deployments take payment, some take an
invite code, most take neither. So payment gets the switch invite_code already
has, and the shipped default resolves to no door.

An operator who wants to charge still writes a number in their own policy —
that path is tested here too, because removing a default that nobody can turn
back on is the same bug in the other direction.
"""

import os

import pytest

from connectonion.network.trust.ws_admin import doors_that_open


SELF = "0x" + "a" * 64


@pytest.fixture(autouse=True)
def no_ambient_env(monkeypatch):
    """This machine has CO_INVITE_CODE set; the shipped default must be judged
    without it."""
    monkeypatch.delenv("CO_INVITE_CODE", raising=False)
    monkeypatch.delenv("CO_PAYMENT", raising=False)


def _shipped_careful_onboard() -> dict:
    """The onboard block of the policy every agent gets, parsed as shipped."""
    from connectonion.network.trust.factory import PROMPTS_DIR
    from connectonion.network.trust import parse_policy

    text = (PROMPTS_DIR / "careful.md").read_text(encoding="utf-8")
    config, _ = parse_policy(text, source="careful.md")
    return config.get("onboard", {})


class TestTheDefaultAgentSellsNothing:

    def test_a_fresh_agent_advertises_no_door(self):
        assert doors_that_open(_shipped_careful_onboard(), SELF) is None

    def test_the_shipped_policy_carries_no_bare_amount(self):
        """A literal is on for everyone and cannot be turned off."""
        payment = _shipped_careful_onboard().get("payment")

        assert not isinstance(payment, (int, float)), (
            f"careful.md ships payment: {payment!r}, which every agent charges"
        )

    def test_it_matches_how_invite_code_is_written(self):
        """Both doors opt in from the environment, or neither should."""
        onboard = _shipped_careful_onboard()

        assert str(onboard.get("payment", "")).startswith("$"), onboard


class TestAnOperatorWhoWantsToCharge:

    def test_the_environment_switch_opens_it(self, monkeypatch):
        monkeypatch.setenv("CO_PAYMENT", "25")

        doors = doors_that_open(_shipped_careful_onboard(), SELF)

        assert doors and "payment" in doors["methods"]
        assert doors["payment_amount"] == 25

    def test_a_number_in_their_own_policy_still_works(self):
        """The publish-time decision: a trust config that names a price."""
        doors = doors_that_open({"payment": 10}, SELF)

        assert doors and doors["methods"] == ["payment"]
        assert doors["payment_amount"] == 10

    def test_the_price_reaches_the_stranger_with_an_address(self):
        doors = doors_that_open({"payment": 10}, SELF)

        assert doors["payment_address"] == SELF


class TestWhatAnUnusableValueDoes:
    """A door nobody can walk through must not be advertised — the #561 shape,
    where the agent published an invite code no value opened."""

    def test_an_unset_variable_is_no_door(self):
        assert doors_that_open({"payment": "$CO_PAYMENT"}, SELF) is None

    def test_an_empty_variable_is_no_door(self, monkeypatch):
        monkeypatch.setenv("CO_PAYMENT", "")

        assert doors_that_open({"payment": "$CO_PAYMENT"}, SELF) is None

    def test_something_that_is_not_a_number_is_no_door(self, monkeypatch):
        monkeypatch.setenv("CO_PAYMENT", "ten dollars")

        assert doors_that_open({"payment": "$CO_PAYMENT"}, SELF) is None

    def test_zero_is_no_door(self, monkeypatch):
        """`payment: 0` admits anyone who sends nothing — that is `open`, and
        an operator who meant open should say so."""
        monkeypatch.setenv("CO_PAYMENT", "0")

        assert doors_that_open({"payment": "$CO_PAYMENT"}, SELF) is None

    def test_a_negative_amount_is_no_door(self, monkeypatch):
        monkeypatch.setenv("CO_PAYMENT", "-5")

        assert doors_that_open({"payment": "$CO_PAYMENT"}, SELF) is None

    def test_a_price_with_nowhere_to_pay_is_no_door(self):
        """Unchanged, and re-checked here: verify_payment refuses without an
        address, so advertising one would be telling a stranger to pay and not
        telling them where."""
        assert doors_that_open({"payment": 10}, None) is None


class TestTheOtherDoorIsUnaffected:

    def test_an_invite_code_still_opens_on_its_own(self, monkeypatch):
        monkeypatch.setenv("CO_INVITE_CODE", "letmein")

        doors = doors_that_open(_shipped_careful_onboard(), SELF)

        assert doors and doors["methods"] == ["invite_code"]

    def test_both_switches_give_both_doors(self, monkeypatch):
        monkeypatch.setenv("CO_INVITE_CODE", "letmein")
        monkeypatch.setenv("CO_PAYMENT", "25")

        doors = doors_that_open(_shipped_careful_onboard(), SELF)

        assert sorted(doors["methods"]) == ["invite_code", "payment"]


class TestTheAmountThatIsCharged:
    """doors_that_open is what /info and the client are told. Whatever it
    publishes has to be what verify_payment then requires, or the stranger pays
    the advertised price and is refused."""

    def test_the_advertised_amount_is_a_number(self, monkeypatch):
        monkeypatch.setenv("CO_PAYMENT", "25")

        amount = doors_that_open({"payment": "$CO_PAYMENT"}, SELF)["payment_amount"]

        assert isinstance(amount, (int, float)), f"published {amount!r} to pay"

    def test_a_decimal_price_survives(self, monkeypatch):
        monkeypatch.setenv("CO_PAYMENT", "2.5")

        assert doors_that_open({"payment": "$CO_PAYMENT"}, SELF)["payment_amount"] == 2.5


class TestATypoInTheSwitchClosesTheDoor:
    """CO_PAYMENT is typed by an operator. Every wrong value has to end as "no
    door" — the trust gate reads this on the path a stranger drives, so an
    exception here is a crash a stranger can cause."""

    @pytest.mark.parametrize("typed", [
        "--5", "++5", ".", "-", "10 USD", "$10", "1,000", "10.0.0",
        "  ", "nan", "inf", "1e5",
    ])
    def test_it_never_raises_and_never_opens(self, typed, monkeypatch):
        monkeypatch.setenv("CO_PAYMENT", typed)

        assert doors_that_open({"payment": "$CO_PAYMENT"}, SELF) is None

    @pytest.mark.parametrize("typed,expected", [
        ("10", 10), ("2.5", 2.5), (" 25 ", 25), ("+7", 7), ("0.01", 0.01),
        # A price, written the way a person writes one. Rejecting it would
        # close a door the operator plainly meant to open.
        ("10.", 10),
    ])
    def test_a_price_written_reasonably_is_read(self, typed, expected, monkeypatch):
        monkeypatch.setenv("CO_PAYMENT", typed)

        assert doors_that_open({"payment": "$CO_PAYMENT"}, SELF)["payment_amount"] == expected
