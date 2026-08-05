"""A stranger connects to a default agent and the trust gate raises.

Introduced by #691, which made the shipped price opt-in:

    onboard:
      payment: $CO_PAYMENT

Three places read `onboard.payment`. That change routed two of them through a
resolver — `doors_that_open`, which advertises the price, and `verify_payment`,
which enforces it — and missed the third:

    required_payment = onboard.get('payment')
    request_payment = request.get('payment', 0)
    if required_payment and request_payment >= required_payment:

`"$CO_PAYMENT"` is a non-empty string, so the guard passes and the comparison
runs `0 >= "$CO_PAYMENT"`. Measured against a real host on default trust, from
a client that had never connected before:

    File ".../fast_rules.py", line 226, in evaluate_request
        if required_payment and request_payment >= required_payment:
    TypeError: '>=' not supported between instances of 'int' and 'str'

    client: websockets.exceptions.ConnectionClosedError

Every stranger CONNECT died there, which is every first contact any agent ever
has. Found by driving a real host rather than by reading the code — the suite
was green, because nothing exercised the CONNECT path with the shipped policy.

The second half of this file is about what that line does when it *does* work,
which is worse than raising: see TestAClaimIsNotAPayment.
"""

import pytest

from connectonion.network.trust.fast_rules import evaluate_request


STRANGER = "0x" + "e" * 64

# `default: ask` does not return the string "ask" -- it returns None, meaning
# "the fast rules did not decide; hand this to the LLM policy". Every assertion
# below that a stranger is not admitted is an assertion of None, not 'allow'.
ASKED_ABOUT = None


@pytest.fixture(autouse=True)
def no_ambient_env(monkeypatch, tmp_path):
    monkeypatch.delenv("CO_INVITE_CODE", raising=False)
    monkeypatch.delenv("CO_PAYMENT", raising=False)

    # The trust lists go wherever `_project_co_dir()` points, which during a
    # test run is a directory shared by every test in the session -- measured
    # at /tmp/.co/contacts.txt. `promote_to_contact` is durable, so one test
    # that promotes an address changes the answer for every later test that
    # uses it, and the first red run of this file left its own stranger a
    # contact for the green one. Pinned per test.
    from connectonion.network.trust import tools

    co = tmp_path / ".co"
    co.mkdir()
    monkeypatch.setattr(tools, "_project_co_dir", lambda: co)


def _shipped_careful() -> dict:
    from connectonion.network.trust import parse_policy
    from connectonion.network.trust.factory import PROMPTS_DIR

    config, _ = parse_policy((PROMPTS_DIR / "careful.md").read_text(encoding="utf-8"),
                             source="careful.md")
    return config


class TestAStrangerCanReachTheGate:

    def test_the_shipped_policy_does_not_raise(self):
        """The whole bug: this raised TypeError on every stranger CONNECT."""
        assert evaluate_request(_shipped_careful(), STRANGER, {}) is ASKED_ABOUT

    def test_nor_when_the_stranger_mentions_a_payment(self):
        assert evaluate_request(_shipped_careful(), STRANGER, {"payment": 10}) is ASKED_ABOUT

    def test_nor_with_an_invite_code_that_opens_nothing(self):
        assert evaluate_request(_shipped_careful(), STRANGER,
                                {"invite_code": "guess"}) is ASKED_ABOUT

    def test_an_unset_switch_admits_nobody(self, monkeypatch):
        """`$CO_PAYMENT` unset is not a price, so no payment can meet it."""
        assert evaluate_request(_shipped_careful(), STRANGER,
                                {"payment": 999999}) is ASKED_ABOUT


class TestAClaimIsNotAPayment:
    """This path promoted on a number the client wrote in its own frame.

    No transfer is checked here — `verify_payment` and its oo-api call live on
    the ONBOARD_SUBMIT path, not this one. A stranger who put a large enough
    number in the request became a contact, having sent nothing.

    #690 was the same mistake one layer over: the buyer naming the price. This
    is the buyer skipping the payment entirely.
    """

    def test_a_self_declared_payment_does_not_promote(self, monkeypatch):
        monkeypatch.setenv("CO_PAYMENT", "10")

        verdict = evaluate_request(_shipped_careful(), STRANGER, {"payment": 10})

        assert verdict != "allow", (
            "a stranger was admitted for saying they paid, with nothing verified"
        )

    def test_not_even_a_generous_one(self, monkeypatch):
        monkeypatch.setenv("CO_PAYMENT", "10")

        assert evaluate_request(_shipped_careful(), STRANGER, {"payment": 10**9}) != "allow"

    def test_the_stranger_is_still_asked_about(self, monkeypatch):
        """`careful` says ask — the door is ONBOARD_SUBMIT, which verifies."""
        monkeypatch.setenv("CO_PAYMENT", "10")

        assert evaluate_request(_shipped_careful(), STRANGER, {"payment": 10}) is ASKED_ABOUT


class TestTheInviteCodePathIsUnaffected:
    """It checks a secret the operator set, not a number the client chose."""

    def test_the_right_code_still_admits(self, monkeypatch):
        monkeypatch.setenv("CO_INVITE_CODE", "letmein")

        assert evaluate_request(_shipped_careful(), STRANGER,
                                {"invite_code": "letmein"}) == "allow"

    def test_the_wrong_code_does_not(self, monkeypatch):
        monkeypatch.setenv("CO_INVITE_CODE", "letmein")

        assert evaluate_request(_shipped_careful(), STRANGER,
                                {"invite_code": "nope"}) is ASKED_ABOUT
