"""A default agent tells every stranger to onboard, through no door at all.

`should_allow` decides what happens once the fast rules have deferred:

    onboard = self._config.get('onboard', {})
    if onboard and (onboard.get('invite_code') or onboard.get('payment')):
        return Decision(allow=False, reason="Onboard required")

    return self._llm_decide(client_id, request)

Both values in the shipped policy are unexpanded placeholders --
`[$CO_INVITE_CODE]` and `$CO_PAYMENT` -- so both are truthy on an agent with
neither set, and every stranger is sent to onboard.

This is the shape #671 exists to prevent. `doors_that_open` is the single rule:
an invite code counts only if `_resolve_codes` yields one, a payment only if it
resolves to an amount and there is an address to send it to. #561 fixed two
places that decided it separately; #671 found the advertiser and `/info` as the
third and fourth. This is the fifth, and it was still asking the raw config.

Measured against a real host on default trust, no CO_INVITE_CODE, no
CO_PAYMENT, from a client that had never connected:

    GET /info                 "onboard": null
    CONNECT (stranger)   ->   {"type": "ERROR", "message": "forbidden: Onboard required"}

    host log:  [FAST_RULES] Returning None (needs LLM)
               ✗ CONNECT auth error: forbidden: Onboard required

Two things are wrong at once.

The stranger is told to onboard while `/info` -- correctly, since #671 --
publishes no way to. Whatever they do next, nothing admits them.

And `_llm_decide` never runs. `careful` is the default trust level and its
whole documented behaviour for strangers is `default: ask`, evaluated by the
LLM policy. On a default agent that evaluation is unreachable: the branch above
it always wins.
"""

import pytest

from connectonion.network.trust.trust_agent import TrustAgent


STRANGER = "0x" + "f" * 64


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv("CO_INVITE_CODE", raising=False)
    monkeypatch.delenv("CO_PAYMENT", raising=False)

    # Promotions are durable and land in one directory shared by the session
    # (#694), so a test that promotes changes later tests' answers.
    from connectonion.network.trust import tools

    co = tmp_path / ".co"
    co.mkdir()
    monkeypatch.setattr(tools, "_project_co_dir", lambda: co)


@pytest.fixture
def careful(monkeypatch):
    """A default agent, and a record of whether the LLM was consulted."""
    agent = TrustAgent("careful")
    asked = []
    monkeypatch.setattr(
        TrustAgent, "_llm_decide",
        lambda self, client_id, request: asked.append(client_id) or _ALLOW)
    monkeypatch.setattr(TrustAgent, "get_self_address", lambda self: "0x" + "a" * 64)
    return agent, asked


class _Decision:
    def __init__(self, allow, reason):
        self.allow, self.reason = allow, reason


_ALLOW = _Decision(True, "the LLM said so")


class TestWithNoDoorConfigured:

    def test_the_stranger_is_not_told_to_onboard(self, careful):
        agent, _ = careful

        decision = agent.should_allow(STRANGER, {})

        assert "onboard" not in decision.reason.lower(), decision.reason

    def test_the_llm_policy_actually_runs(self, careful):
        """`careful` is the default level and `default: ask` is its documented
        behaviour. It was unreachable."""
        agent, asked = careful

        agent.should_allow(STRANGER, {})

        assert asked == [STRANGER], "default: ask never reached the LLM"


class TestWithADoorThatOpens:
    """Unchanged: an operator who configured one still gets onboarding."""

    def test_an_invite_code_sends_them_to_onboard(self, careful, monkeypatch):
        monkeypatch.setenv("CO_INVITE_CODE", "letmein")
        agent, asked = careful

        decision = agent.should_allow(STRANGER, {})

        assert decision.allow is False
        assert "onboard" in decision.reason.lower()
        assert asked == [], "the LLM was consulted even though a door was open"

    def test_a_price_sends_them_to_onboard(self, careful, monkeypatch):
        monkeypatch.setenv("CO_PAYMENT", "25")
        agent, asked = careful

        decision = agent.should_allow(STRANGER, {})

        assert "onboard" in decision.reason.lower()
        assert asked == []

    def test_a_price_with_nowhere_to_pay_is_not_a_door(self, careful, monkeypatch):
        """Same rule doors_that_open applies: verify_payment refuses without an
        address, so telling a stranger to pay would be telling them nothing."""
        monkeypatch.setenv("CO_PAYMENT", "25")
        agent, asked = careful
        monkeypatch.setattr(TrustAgent, "get_self_address", lambda self: None)

        agent.should_allow(STRANGER, {})

        assert asked == [STRANGER]


class TestTheTwoHalvesAgree:
    """What /info publishes and what CONNECT demands come from one rule."""

    @pytest.mark.parametrize("env", [
        {},
        {"CO_INVITE_CODE": "letmein"},
        {"CO_PAYMENT": "25"},
        {"CO_INVITE_CODE": "letmein", "CO_PAYMENT": "25"},
    ])
    def test_onboard_is_demanded_exactly_when_a_door_opens(self, careful, monkeypatch, env):
        from connectonion.network.trust.ws_admin import doors_that_open

        for key, value in env.items():
            monkeypatch.setenv(key, value)
        agent, _ = careful

        offered = doors_that_open(agent._config.get("onboard", {}),
                                  agent.get_self_address())
        demanded = "onboard" in agent.should_allow(STRANGER, {}).reason.lower()

        assert demanded == (offered is not None), (
            f"{env}: /info offers {offered}, CONNECT demands onboard={demanded}"
        )
