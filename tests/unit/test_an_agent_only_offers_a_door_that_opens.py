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

So with `CO_INVITE_CODE` unset the two disagree. `co init` does mint a code into
the project's `.env`, and importing connectonion loads it — so a laptop project
usually has one. Where it is missing is the deployed agent: the resolver's own
docstring notes that the env file is "the one thing `co deploy` neither rsyncs
nor overwrites", so a server whose env file was never populated runs with no
code, and so does any `host()` in a project that never ran `co init`.

Measured against a real hosted agent with no code in its environment:

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
    """A default-trust agent with no invite code, selling access for 10.

    The price is set here rather than inherited. It used to be shipped in
    careful.md, so every agent had one; #672 made it opt-in, and these tests
    are about what an agent offers *given* a door, not about which doors the
    default policy carries. That question is
    tests/unit/test_payment_is_opt_in.py, which asserts the default offers
    nothing at all.
    """
    from connectonion.network.trust.trust_agent import TrustAgent

    monkeypatch.delenv("CO_INVITE_CODE", raising=False)
    monkeypatch.setenv("CO_PAYMENT", "10")
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


class TestInfoSaysTheSameThing:
    """`/info` built its own answer and reached the opposite conclusion.

        onboard = trust_config.get("onboard", {})
        if onboard:
            result["onboard"] = {
                "invite_code": "invite_code" in onboard,
                ...

    `trust_config` is the *raw* policy, so with no code set this is the
    unexpanded placeholder and the test is still true:

        /info path  (_parse_trust_config)  {'onboard': {'invite_code': ['$CO_INVITE_CODE'], 'payment': 10}}
        CONNECT path (get_onboard_requirements)  None

    That makes four places deciding what onboarding exists — #561 fixed two,
    the advertiser above was the third, and this is the fourth. It is also the
    worst placed of them: `/info` needs no credentials, so a deployed agent
    publishes this answer to the whole internet.

    So `/info` asks the same function the CONNECT path asks, rather than
    reaching its own verdict from a different input.
    """

    @staticmethod
    def _info(trust_agent):
        from connectonion.network.host.http_router import info_handler

        return info_handler(
            {"name": "a", "address": "0x" + "1" * 64, "tools": []},
            trust_agent,
            trust_agent.config,
        )

    def test_an_unusable_invite_code_is_not_announced(self, careful, monkeypatch):
        monkeypatch.setattr(careful, "get_self_address", lambda: "0x" + "a" * 64)

        assert self._info(careful)["onboard"]["invite_code"] is False

    def test_a_usable_one_is(self, monkeypatch):
        from connectonion.network.trust.trust_agent import TrustAgent

        monkeypatch.setenv("CO_INVITE_CODE", "let-me-in")
        agent = TrustAgent("careful")
        monkeypatch.setattr(agent, "get_self_address", lambda: "0x" + "a" * 64)

        assert self._info(agent)["onboard"]["invite_code"] is True

    def test_payment_with_nowhere_to_send_it_is_not_announced(self, careful, monkeypatch):
        monkeypatch.setattr(careful, "get_self_address", lambda: None)

        assert "onboard" not in self._info(careful)

    def test_the_amount_is_still_published_when_it_can_be_paid(self, careful, monkeypatch):
        monkeypatch.setattr(careful, "get_self_address", lambda: "0x" + "a" * 64)

        assert self._info(careful)["onboard"]["payment"] == 10

    def test_the_two_paths_agree(self, careful, monkeypatch):
        """The property that makes a fifth path impossible to introduce quietly."""
        from connectonion.network.trust.ws_admin import get_onboard_requirements

        for address in [None, "0x" + "a" * 64]:
            monkeypatch.setattr(careful, "get_self_address", lambda: address)
            offered = get_onboard_requirements(careful)
            info = self._info(careful).get("onboard")

            if offered is None:
                assert info is None
            else:
                assert info["invite_code"] == ("invite_code" in offered["methods"])
