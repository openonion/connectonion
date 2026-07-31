"""
LLM-Note: Tests for trust functions

What it tests:
- Trust Functions functionality

Components under test:
- Module: trust_functions
"""
#!/usr/bin/env python3
"""
Unit tests for network/trust/tools.py - trust verification tools.

Tests cover:
- check_whitelist() and check_blocklist() functions
- is_* helper functions
- get_trust_verification_tools() returns correct functions
"""

import pytest
from pathlib import Path

from connectonion.network.trust import tools
from connectonion.network.trust.tools import (
    check_whitelist,
    check_blocklist,
    get_trust_verification_tools,
    is_whitelisted,
    is_blocked,
    is_contact,
    promote_to_contact,
    block,
)


@pytest.fixture
def temp_co_dir(tmp_path, monkeypatch):
    """Create temp ~/.co/ directory for tests."""
    co_dir = tmp_path / ".co"
    co_dir.mkdir()
    monkeypatch.setattr(tools, "CO_DIR", co_dir)
    return co_dir


class TestCheckWhitelist:
    """Test check_whitelist function."""

    def test_on_whitelist(self, temp_co_dir):
        """Agent on whitelist returns positive message."""
        (temp_co_dir / "whitelist.txt").write_text("agent-123\nagent-456\n")
        result = check_whitelist("agent-123")
        assert "on the whitelist" in result.lower()

    def test_not_on_whitelist(self, temp_co_dir):
        """Agent not on whitelist returns negative message."""
        (temp_co_dir / "whitelist.txt").write_text("agent-123\n")
        result = check_whitelist("agent-999")
        assert "not" in result.lower()

    def test_wildcard_pattern(self, temp_co_dir):
        """Wildcard patterns work."""
        (temp_co_dir / "whitelist.txt").write_text("trusted-*\n")
        result = check_whitelist("trusted-agent-123")
        assert "whitelist" in result.lower()

    def test_no_whitelist_file(self, temp_co_dir):
        """Missing whitelist file handled gracefully."""
        result = check_whitelist("any-agent")
        assert "not" in result.lower()


class TestCheckBlocklist:
    """Test check_blocklist function."""

    def test_on_blocklist(self, temp_co_dir):
        """Agent on blocklist returns blocked message."""
        (temp_co_dir / "blocklist.txt").write_text("bad-agent\n")
        result = check_blocklist("bad-agent")
        assert "blocked" in result.lower()

    def test_not_on_blocklist(self, temp_co_dir):
        """Agent not on blocklist returns not blocked message."""
        (temp_co_dir / "blocklist.txt").write_text("other-agent\n")
        result = check_blocklist("good-agent")
        assert "not blocked" in result.lower()


class TestIsWhitelisted:
    """Test is_whitelisted function."""

    def test_whitelisted(self, temp_co_dir):
        """Returns True for whitelisted agent."""
        (temp_co_dir / "whitelist.txt").write_text("agent-123\n")
        assert is_whitelisted("agent-123") is True

    def test_not_whitelisted(self, temp_co_dir):
        """Returns False for non-whitelisted agent."""
        assert is_whitelisted("unknown") is False


class TestIsBlocked:
    """Test is_blocked function."""

    def test_blocked(self, temp_co_dir):
        """Returns True for blocked agent."""
        (temp_co_dir / "blocklist.txt").write_text("bad-agent\n")
        assert is_blocked("bad-agent") is True

    def test_not_blocked(self, temp_co_dir):
        """Returns False for non-blocked agent."""
        assert is_blocked("good-agent") is False


class TestIsContact:
    """Test is_contact function."""

    def test_contact(self, temp_co_dir):
        """Returns True for contact."""
        (temp_co_dir / "contacts.txt").write_text("contact-123\n")
        assert is_contact("contact-123") is True

    def test_not_contact(self, temp_co_dir):
        """Returns False for non-contact."""
        assert is_contact("stranger") is False


class TestGetTrustVerificationTools:
    """Test get_trust_verification_tools function."""

    def test_returns_list(self):
        """Returns a list of functions."""
        tools_list = get_trust_verification_tools()
        assert isinstance(tools_list, list)
        assert len(tools_list) > 0

    def test_contains_check_whitelist(self):
        """Contains check_whitelist function."""
        tools_list = get_trust_verification_tools()
        assert check_whitelist in tools_list

    def test_contains_check_blocklist(self):
        """Contains check_blocklist function."""
        tools_list = get_trust_verification_tools()
        assert check_blocklist in tools_list

    def test_contains_promote_to_contact(self):
        """Contains promote_to_contact function."""
        tools_list = get_trust_verification_tools()
        assert promote_to_contact in tools_list

    def test_contains_block(self):
        """Contains block function."""
        tools_list = get_trust_verification_tools()
        assert block in tools_list

    def test_all_tools_callable(self):
        """All tools are callable."""
        tools_list = get_trust_verification_tools()
        for tool in tools_list:
            assert callable(tool)


class TestIntegration:
    """Integration tests for trust tools."""

    def test_whitelist_check_via_is_whitelisted(self, temp_co_dir):
        """check_whitelist and is_whitelisted agree."""
        (temp_co_dir / "whitelist.txt").write_text("agent-123\n")

        # Both should agree
        assert is_whitelisted("agent-123") is True
        assert "whitelist" in check_whitelist("agent-123").lower()

    def test_block_and_is_blocked(self, temp_co_dir):
        """block() and is_blocked() work together."""
        assert is_blocked("new-agent") is False

        block("new-agent", "test reason")

        assert is_blocked("new-agent") is True
        assert "blocked" in check_blocklist("new-agent").lower()


class TestAdminListIsPerAgent:
    """admins.txt lives beside the agent's identity, not in $HOME.

    It used to be the single global ~/.co/admins.txt while the self address it is
    compared against came from the project's .co/ — so every agent on one machine
    shared one set of admins, and making someone admin of one deployed agent made
    them admin of all of them.
    """

    def test_add_admin_writes_beside_the_identity(self, tmp_path):
        co_dir = tmp_path / "agent-a" / ".co"
        co_dir.mkdir(parents=True)

        tools.add_admin("0xdeadbeef", co_dir)

        assert (co_dir / "admins.txt").read_text().strip() == "0xdeadbeef"
        assert tools._admins_file(co_dir) != Path.home() / ".co" / "admins.txt"

    def test_two_agents_on_one_machine_have_separate_admins(self, tmp_path):
        a = tmp_path / "agent-a" / ".co"
        b = tmp_path / "agent-b" / ".co"
        a.mkdir(parents=True)
        b.mkdir(parents=True)

        tools.add_admin("0xalice", a)

        assert tools.is_admin("0xalice", a) is True
        assert tools.is_admin("0xalice", b) is False

    def test_remove_admin_targets_the_same_file_add_wrote(self, tmp_path):
        co_dir = tmp_path / "agent" / ".co"
        co_dir.mkdir(parents=True)

        tools.add_admin("0xalice", co_dir)
        tools.remove_admin("0xalice", co_dir)

        assert tools.is_admin("0xalice", co_dir) is False

    def test_a_seeded_admins_file_is_honoured(self, tmp_path):
        """This is the file a deploy ships: the operator's address, one line."""
        co_dir = tmp_path / "agent" / ".co"
        co_dir.mkdir(parents=True)
        (co_dir / "admins.txt").write_text("0xdeployer\n")

        assert tools.is_admin("0xdeployer", co_dir) is True


class TestThePaymentAddressAPaidOnboardingShows:
    """openonion/oo-chat#28. The card says "Transfer $X to:" — and the address it
    shows is `get_self_address()`, which is also the address `verify_payment`
    checks the transfer arrived at. Both read it from the same place on purpose:
    an onboarding where the displayed address and the verified address can
    disagree sends somebody's money somewhere nobody is watching.
    """

    def _project(self, tmp_path):
        """A project as `co create` leaves it: keys under .co/keys/, and no
        .co/address.json, which is the file this used to read."""
        from connectonion import address

        co_dir = tmp_path / ".co"
        co_dir.mkdir()
        keys = address.generate()
        address.save(keys, co_dir)
        assert not (co_dir / "address.json").exists(), \
            "the fixture no longer reflects what co create writes"
        return co_dir, keys["address"]

    def test_a_project_made_by_co_create_has_a_payment_address(self, tmp_path):
        from connectonion.network.trust.tools import get_self_address

        co_dir, expected = self._project(tmp_path)

        assert get_self_address(co_dir) == expected

    def test_an_older_project_still_answers_from_address_json(self, tmp_path):
        """Nothing rewrites these on upgrade, so the old file stays readable."""
        import json

        from connectonion.network.trust.tools import get_self_address

        co_dir = tmp_path / ".co"
        co_dir.mkdir()
        (co_dir / "address.json").write_text(json.dumps({"address": "0xold"}))

        assert get_self_address(co_dir) == "0xold"

    def test_the_card_and_the_check_are_given_the_same_address(self, tmp_path):
        """ONBOARD_REQUIRED tells the payer where to send it; verify_payment
        decides whether it arrived. One value, read once."""
        from types import SimpleNamespace

        from connectonion.network.trust.tools import get_self_address
        from connectonion.network.trust.ws_admin import get_onboard_requirements

        co_dir, expected = self._project(tmp_path)
        trust_agent = SimpleNamespace(
            config={"onboard": {"payment": 5}},
            get_self_address=lambda: get_self_address(co_dir),
        )

        assert get_onboard_requirements(trust_agent)["payment_address"] == expected


class TestPaymentVerificationFailsClosed:
    def test_a_missing_dependency_does_not_admit_the_payer(self, monkeypatch):
        """It returned True — a machine without httpx let anyone in who claimed
        to have paid. This is the one direction the check must never fail in."""
        import builtins

        from connectonion.network.trust.trust_agent import TrustAgent

        real_import = builtins.__import__

        def no_httpx(name, *args, **kwargs):
            if name == "httpx":
                raise ImportError("no httpx here")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_httpx)

        agent = TrustAgent.__new__(TrustAgent)
        assert agent._verify_transfer_via_api("0xpayer", "0xagent", 5.0) is False
