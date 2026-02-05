"""Tests for trust state management functions (promote, demote, block, etc.)."""

import pytest
from pathlib import Path

from connectonion.network.trust import tools
from connectonion.network.trust.tools import (
    promote_to_contact,
    promote_to_whitelist,
    demote_to_contact,
    demote_to_stranger,
    block,
    unblock,
    get_level,
    is_contact,
    is_stranger,
    is_whitelisted,
    is_blocked,
    verify_invite,
    verify_payment,
)


@pytest.fixture
def temp_co_dir(tmp_path, monkeypatch):
    """Create temp ~/.co/ directory for tests."""
    co_dir = tmp_path / ".co"
    co_dir.mkdir()
    monkeypatch.setattr(tools, "CO_DIR", co_dir)
    return co_dir


class TestPromoteToContact:
    """Test promote_to_contact function."""

    def test_adds_to_contacts(self, temp_co_dir):
        """promote_to_contact adds client to contacts list."""
        result = promote_to_contact("new-client")
        assert "promoted to contact" in result
        assert is_contact("new-client")

    def test_idempotent(self, temp_co_dir):
        """Promoting twice doesn't duplicate entry."""
        promote_to_contact("client")
        promote_to_contact("client")

        content = (temp_co_dir / "contacts.txt").read_text()
        assert content.count("client") == 1


class TestPromoteToWhitelist:
    """Test promote_to_whitelist function."""

    def test_adds_to_whitelist(self, temp_co_dir):
        """promote_to_whitelist adds client to whitelist."""
        result = promote_to_whitelist("trusted-client")
        assert "promoted to whitelist" in result
        assert is_whitelisted("trusted-client")


class TestDemoteToContact:
    """Test demote_to_contact function."""

    def test_removes_from_whitelist(self, temp_co_dir):
        """demote_to_contact removes from whitelist, adds to contacts."""
        promote_to_whitelist("client")
        assert is_whitelisted("client")

        result = demote_to_contact("client")
        assert "demoted to contact" in result
        assert not is_whitelisted("client")
        assert is_contact("client")


class TestDemoteToStranger:
    """Test demote_to_stranger function."""

    def test_removes_from_contacts(self, temp_co_dir):
        """demote_to_stranger removes from contacts."""
        promote_to_contact("client")
        assert is_contact("client")

        result = demote_to_stranger("client")
        assert "demoted to stranger" in result
        assert not is_contact("client")
        assert is_stranger("client")

    def test_removes_from_whitelist(self, temp_co_dir):
        """demote_to_stranger removes from whitelist too."""
        promote_to_whitelist("client")

        demote_to_stranger("client")
        assert not is_whitelisted("client")
        assert is_stranger("client")


class TestBlock:
    """Test block function."""

    def test_adds_to_blocklist(self, temp_co_dir):
        """block adds client to blocklist."""
        result = block("bad-client", "spam")
        assert "blocked" in result
        assert is_blocked("bad-client")

    def test_includes_reason(self, temp_co_dir):
        """block result includes reason."""
        result = block("client", "abuse detected")
        assert "abuse detected" in result


class TestUnblock:
    """Test unblock function."""

    def test_removes_from_blocklist(self, temp_co_dir):
        """unblock removes client from blocklist."""
        block("client", "test")
        assert is_blocked("client")

        result = unblock("client")
        assert "unblocked" in result
        assert not is_blocked("client")


class TestGetLevel:
    """Test get_level function."""

    def test_stranger(self, temp_co_dir):
        """Unknown client is stranger."""
        assert get_level("unknown") == "stranger"

    def test_contact(self, temp_co_dir):
        """Contact level is detected."""
        promote_to_contact("client")
        assert get_level("client") == "contact"

    def test_whitelist(self, temp_co_dir):
        """Whitelist level is detected."""
        promote_to_whitelist("client")
        assert get_level("client") == "whitelist"

    def test_blocked(self, temp_co_dir):
        """Blocked level takes priority."""
        promote_to_whitelist("client")
        block("client", "test")
        assert get_level("client") == "blocked"


class TestVerifyInvite:
    """Test verify_invite function."""

    def test_valid_code_promotes(self, temp_co_dir):
        """Valid invite code promotes to contact."""
        result = verify_invite("client", "CODE1", ["CODE1", "CODE2"])
        assert "valid" in result.lower()
        assert is_contact("client")

    def test_invalid_code_rejected(self, temp_co_dir):
        """Invalid invite code is rejected."""
        result = verify_invite("client", "WRONG", ["CODE1"])
        assert "invalid" in result.lower()
        assert not is_contact("client")


class TestVerifyPayment:
    """Test verify_payment function."""

    def test_sufficient_payment_promotes(self, temp_co_dir):
        """Sufficient payment promotes to contact."""
        result = verify_payment("client", 15, 10)
        assert "verified" in result.lower()
        assert is_contact("client")

    def test_exact_payment_works(self, temp_co_dir):
        """Exact payment amount is accepted."""
        result = verify_payment("client", 10, 10)
        assert "verified" in result.lower()

    def test_insufficient_payment_rejected(self, temp_co_dir):
        """Insufficient payment is rejected."""
        result = verify_payment("client", 5, 10)
        assert "insufficient" in result.lower()
        assert not is_contact("client")


class TestIsHelpers:
    """Test is_* helper functions."""

    def test_is_contact(self, temp_co_dir):
        """is_contact returns correct boolean."""
        assert not is_contact("client")
        promote_to_contact("client")
        assert is_contact("client")

    def test_is_stranger(self, temp_co_dir):
        """is_stranger returns correct boolean."""
        assert is_stranger("unknown")
        promote_to_contact("unknown")
        assert not is_stranger("unknown")

    def test_is_whitelisted(self, temp_co_dir):
        """is_whitelisted returns correct boolean."""
        assert not is_whitelisted("client")
        promote_to_whitelist("client")
        assert is_whitelisted("client")

    def test_is_blocked(self, temp_co_dir):
        """is_blocked returns correct boolean."""
        assert not is_blocked("client")
        block("client", "test")
        assert is_blocked("client")
