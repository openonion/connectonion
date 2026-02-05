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
