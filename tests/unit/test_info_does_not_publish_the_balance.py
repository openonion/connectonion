"""The unauthenticated `/info` does not say how much money the operator has.

`/info` needs no credentials. Its own comment in http_router.py says what that
means and draws the line carefully for skills:

    /info is unauthenticated: anyone who can reach the agent can read it, and on
    a deployed agent that is the whole internet. … The operator's own toolboxes
    … must not be advertised by it; a full list here leaks which tools, SaaS
    accounts and internal workflows the operator has on their machine.

Twenty lines below, the same response carries `balance_usd`. Measured against a
live agent on this machine:

    $ curl -s http://127.0.0.1:8477/info
    "balance_usd": 1207.1999

That is the operator's real account balance, published to anyone who can reach
the agent. It is commercially revealing on its own, and it is a targeting
signal: credits are money, and an agent with a large balance is worth more
effort than one with none.

The client library already documents the intended boundary — `connectonion-react`
says of the authenticated profile:

    The agent's full self-description — name, model, tools, every skill, balance
    — pushed by the Host once the connection is authenticated. … the public
    `/info` answer is deliberately narrower.

So the contract was already written down; `/info` did not keep it. The balance
still goes to authenticated clients in AGENT_PROFILE and in the CONNECTED
frame, which is where the chat UI reads it from.
"""

import pytest

from connectonion.network.host import http_router
from connectonion.network.trust.trust_agent import TrustAgent


def _info(**metadata) -> dict:
    base = {
        "name": "billing",
        "address": "0x" + "a" * 64,
        "tools": ["read"],
        "model": "co/gemini-3.7-flash",
        "version": "1.6.0",
    }
    base.update(metadata)
    # The real TrustAgent, not a string: info_handler reads .trust off it, and
    # a stand-in that answers differently is how a test agrees with itself.
    return http_router.info_handler(base, trust=TrustAgent("careful"), trust_config={})


class TestTheBalanceStaysPrivate:

    def test_it_is_absent_when_the_agent_has_one(self):
        result = _info(balance_usd=1207.1999)

        assert "balance_usd" not in result, result

    def test_no_field_carries_the_number_under_another_name(self):
        """A rename would be the same leak with a different label."""
        result = _info(balance_usd=1207.1999)

        assert 1207.1999 not in result.values()


class TestWhatInfoStillAnswers:
    """It is the pre-connection answer: enough to decide whether to connect."""

    def test_the_name_and_address(self):
        result = _info(balance_usd=1207.1999)

        assert result["name"] == "billing"
        assert result["address"] == "0x" + "a" * 64

    def test_the_model_and_tools(self):
        result = _info()

        assert result["model"] == "co/gemini-3.7-flash"
        assert result["tools"] == ["read"]

    def test_an_agent_without_a_balance_is_unchanged(self):
        result = _info()

        assert "balance_usd" not in result
