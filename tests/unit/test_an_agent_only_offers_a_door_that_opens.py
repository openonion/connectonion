"""A stranger is offered an invite code that cannot open anything.

`get_onboard_requirements` advertises a method whenever the policy *mentions*
it:

    if "invite_code" in onboard:
        result["methods"].append("invite_code")

The shipped `careful` policy — the default for every agent — mentions it as an
environment reference:

    onboard:
      invite_code: [$CO_INVITE_CODE]
      payment: 10

`verify_invite` does not use that list directly. It resolves it, and the
resolver is explicit about what an unset variable means (#561):

    An unset variable resolves to *nothing*, never to the placeholder and never
    to a default. … A missing code is a closed door, not an open one.

So with `CO_INVITE_CODE` unset — which is every agent that has not set one —
the two disagree. Measured against a real hosted agent on default trust:

    GET /info          "onboard": {"invite_code": true, "payment": 10}
    co call <address>  agent requires onboarding (invite_code, payment)
    verify_invite('')            -> False
    verify_invite('anything')    -> False
    verify_invite('$CO_INVITE_CODE') -> False

The stranger is told to enter a code, and no code exists that works.

This is the third path of #561. That fix changed `evaluate_request` and
`verify_invite`, and the comment left on the second one says why both were
needed — "fixing only the other one would have left the real door open". The
advertiser was never compared against the resolver at all.

Payment has the same shape for a different reason: the amount is advertised
whether or not there is an address to send it to. `get_self_address()` returns
None for an agent with no key of its own, and the method is still offered, so a
client is told to pay and not told where.

What is deliberately *not* changed here: `payment: 10` sitting in the default
policy at all. Every agent from `co init` advertises "transfer 10 to my address
and become a contact" without its operator configuring anything, and the door
is wired end to end — ONBOARD_SUBMIT → verify_payment → oo-api → promote to
contact. Whether that default should exist is a product decision, filed
separately. This change only stops the agent offering doors that cannot open.
"""

import pytest


@pytest.fixture
def careful(monkeypatch):
    """A default-trust agent with no invite code set — the common case."""
    from connectonion.network.trust.trust_agent import TrustAgent

    monkeypatch.delenv("CO_INVITE_CODE", raising=False)
    return TrustAgent("careful")


class TestAnInviteCodeThatCannotWork:

    def test_it_is_not_offered(self, careful):
        from connectonion.network.trust.ws_admin import get_onboard_requirements

        offered = get_onboard_requirements(careful) or {"methods": []}

        assert "invite_code" not in offered["methods"]

    def test_the_resolver_agrees_nothing_opens_it(self, careful):
        """The measurement the advertisement should have matched."""
        for attempt in ["", "anything", "$CO_INVITE_CODE"]:
            assert careful.verify_invite("0x" + "f" * 64, attempt) is False


class TestAnInviteCodeThatDoesWork:
    """The point of the feature — it must still be offered."""

    def test_it_is_offered(self, monkeypatch):
        from connectonion.network.trust.trust_agent import TrustAgent
        from connectonion.network.trust.ws_admin import get_onboard_requirements

        monkeypatch.setenv("CO_INVITE_CODE", "let-me-in")
        offered = get_onboard_requirements(TrustAgent("careful"))

        assert "invite_code" in offered["methods"]

    def test_and_the_code_opens_it(self, monkeypatch, tmp_path):
        from connectonion.network.trust.trust_agent import TrustAgent

        monkeypatch.setenv("CO_INVITE_CODE", "let-me-in")
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".co").mkdir()

        assert TrustAgent("careful").verify_invite("0x" + "f" * 64, "let-me-in")


class TestPaymentWithNowhereToSendIt:

    def test_it_is_not_offered_without_an_address(self, careful, monkeypatch):
        from connectonion.network.trust import ws_admin

        monkeypatch.setattr(careful, "get_self_address", lambda: None)
        offered = ws_admin.get_onboard_requirements(careful) or {"methods": []}

        assert "payment" not in offered["methods"]

    def test_it_is_offered_with_one(self, careful, monkeypatch):
        from connectonion.network.trust import ws_admin

        monkeypatch.setattr(careful, "get_self_address", lambda: "0x" + "a" * 64)
        offered = ws_admin.get_onboard_requirements(careful)

        assert "payment" in offered["methods"]
        assert offered["payment_address"] == "0x" + "a" * 64
        assert offered["payment_amount"] == 10


class TestAnInviteCodeWrittenAsAScalar:
    """`invite_code: mycode` admits anyone who types one letter of it.

    The resolver iterates what it is given:

        for code in codes or []:

    The shipped policies write a list, so this never showed. A hand-written
    policy that says `invite_code: mycode` -- the natural way to write one value
    in YAML -- iterates the *string*, and every character becomes a code that
    opens the door. A stranger typing `m` is promoted to contact.

    Same family as #561, which removed a published constant from the shipped
    policy. This is the other way to end up with a code nobody chose.
    """

    def test_a_scalar_is_one_code_not_one_per_letter(self):
        from connectonion.network.trust.fast_rules import _resolve_codes

        assert _resolve_codes("mycode") == ["mycode"]

    def test_a_letter_of_it_does_not_open_the_door(self, tmp_path, monkeypatch):
        from connectonion.network.trust.trust_agent import TrustAgent

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".co").mkdir()
        agent = TrustAgent("careful")
        agent._config["onboard"] = {"invite_code": "mycode"}

        assert agent.verify_invite("0x" + "f" * 64, "m") is False

    def test_the_whole_code_still_does(self, tmp_path, monkeypatch):
        from connectonion.network.trust.trust_agent import TrustAgent

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".co").mkdir()
        agent = TrustAgent("careful")
        agent._config["onboard"] = {"invite_code": "mycode"}

        assert agent.verify_invite("0x" + "f" * 64, "mycode") is True

    def test_a_scalar_environment_reference_still_resolves(self, monkeypatch):
        from connectonion.network.trust.fast_rules import _resolve_codes

        monkeypatch.setenv("CO_INVITE_CODE", "from-the-env")

        assert _resolve_codes("$CO_INVITE_CODE") == ["from-the-env"]

    def test_a_list_is_unchanged(self, monkeypatch):
        from connectonion.network.trust.fast_rules import _resolve_codes

        monkeypatch.setenv("CO_INVITE_CODE", "from-the-env")

        assert _resolve_codes(["one", "$CO_INVITE_CODE"]) == ["one", "from-the-env"]

    def test_nothing_is_still_nothing(self):
        from connectonion.network.trust.fast_rules import _resolve_codes

        assert _resolve_codes(None) == []
        assert _resolve_codes([]) == []
        assert _resolve_codes("") == []


class TestAnAgentWithNoDoorAtAll:

    def test_nothing_is_offered(self, careful, monkeypatch):
        """Neither method usable — the client should be told there is no way in,
        not handed a menu of two that both fail."""
        from connectonion.network.trust import ws_admin

        monkeypatch.setattr(careful, "get_self_address", lambda: None)

        assert ws_admin.get_onboard_requirements(careful) is None

    def test_a_policy_without_onboarding_is_unchanged(self, monkeypatch):
        from connectonion.network.trust.trust_agent import TrustAgent
        from connectonion.network.trust.ws_admin import get_onboard_requirements

        monkeypatch.delenv("CO_INVITE_CODE", raising=False)

        assert get_onboard_requirements(TrustAgent("strict")) is None
