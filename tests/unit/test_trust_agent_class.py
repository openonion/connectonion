"""Unit tests for TrustAgent class.

Tests the clear, method-based interface for trust management.
"""

import pytest
from pathlib import Path

from connectonion.network.trust import TrustAgent, Decision


@pytest.fixture
def co_dir(tmp_path, monkeypatch):
    """Set up temp ~/.co directory."""
    co_path = tmp_path / ".co"
    co_path.mkdir()
    monkeypatch.setattr("connectonion.network.trust.tools.CO_DIR", co_path)
    return co_path


class TestTrustAgentCreation:
    """Test TrustAgent initialization."""

    def test_create_with_trust_level(self):
        """Create TrustAgent with trust level string."""
        trust = TrustAgent("careful")
        assert trust.trust == "careful"
        assert trust.config is not None

    def test_create_with_open(self):
        """Create TrustAgent with open trust."""
        trust = TrustAgent("open")
        assert trust.config.get("default") == "allow"

    def test_create_with_strict(self):
        """Create TrustAgent with strict trust."""
        trust = TrustAgent("strict")
        assert trust.config.get("default") == "deny"

    def test_create_with_policy_file(self, tmp_path):
        """Create TrustAgent with custom policy file."""
        policy_file = tmp_path / "custom.md"
        policy_file.write_text("""---
allow:
  - whitelisted
default: deny
---
# Custom Policy
""")
        trust = TrustAgent(str(policy_file))
        assert trust.config.get("default") == "deny"
        assert "whitelisted" in trust.config.get("allow", [])

    def test_create_with_inline_policy(self):
        """Create TrustAgent with inline YAML."""
        trust = TrustAgent("""---
default: allow
---
Inline policy""")
        assert trust.config.get("default") == "allow"


class TestShouldAllow:
    """Test should_allow() method."""

    def test_open_allows_everyone(self, co_dir):
        """Open trust allows all requests."""
        trust = TrustAgent("open")
        decision = trust.should_allow("stranger-123")
        assert decision.allow is True
        assert decision.used_llm is False

    def test_strict_denies_strangers(self, co_dir):
        """Strict trust denies non-whitelisted."""
        trust = TrustAgent("strict")
        decision = trust.should_allow("stranger-123")
        assert decision.allow is False
        assert decision.used_llm is False

    def test_strict_allows_whitelisted(self, co_dir):
        """Strict trust allows whitelisted clients."""
        # Add to whitelist
        whitelist_file = co_dir / "whitelist.txt"
        whitelist_file.write_text("trusted-client\n")

        trust = TrustAgent("strict")
        decision = trust.should_allow("trusted-client")
        assert decision.allow is True

    def test_returns_decision_object(self, co_dir):
        """should_allow returns Decision dataclass."""
        trust = TrustAgent("open")
        decision = trust.should_allow("anyone")

        assert isinstance(decision, Decision)
        assert hasattr(decision, "allow")
        assert hasattr(decision, "reason")
        assert hasattr(decision, "used_llm")


class TestVerification:
    """Test verification methods."""

    def test_verify_invite_valid_code(self, co_dir):
        """Valid invite code promotes to contact."""
        trust = TrustAgent("careful")  # careful.md has invite_code: [OpenOnion]

        result = trust.verify_invite("new-user", "OpenOnion")

        assert result is True
        assert trust.get_level("new-user") == "contact"

    def test_verify_invite_invalid_code(self, co_dir):
        """Invalid invite code does not promote."""
        trust = TrustAgent("careful")

        result = trust.verify_invite("new-user", "WRONG_CODE")

        assert result is False
        assert trust.get_level("new-user") == "stranger"

    def test_verify_payment_sufficient(self, co_dir, monkeypatch):
        """Sufficient payment promotes to contact."""
        trust = TrustAgent("careful")  # careful.md has payment: 10

        # Mock the API verification to return True
        monkeypatch.setattr(trust, "_verify_transfer_via_api", lambda *args: True)
        # Mock get_self_address to return a valid address
        monkeypatch.setattr(trust, "get_self_address", lambda: "0x1234")

        result = trust.verify_payment("paying-user", 10)

        assert result is True
        assert trust.get_level("paying-user") == "contact"

    def test_verify_payment_insufficient(self, co_dir, monkeypatch):
        """Insufficient payment does not promote."""
        trust = TrustAgent("careful")

        # Mock the API verification to return False (payment not found)
        monkeypatch.setattr(trust, "_verify_transfer_via_api", lambda *args: False)
        monkeypatch.setattr(trust, "get_self_address", lambda: "0x1234")

        result = trust.verify_payment("cheap-user", 5)

        assert result is False
        assert trust.get_level("cheap-user") == "stranger"


class TestPromotion:
    """Test promotion methods."""

    def test_promote_to_contact(self, co_dir):
        """Promote stranger to contact."""
        trust = TrustAgent("careful")

        trust.promote_to_contact("new-user")

        assert trust.get_level("new-user") == "contact"

    def test_promote_to_whitelist(self, co_dir):
        """Promote to whitelist."""
        trust = TrustAgent("careful")

        trust.promote_to_whitelist("trusted-user")

        assert trust.get_level("trusted-user") == "whitelist"


class TestDemotion:
    """Test demotion methods."""

    def test_demote_to_contact(self, co_dir):
        """Demote from whitelist to contact."""
        trust = TrustAgent("careful")
        trust.promote_to_whitelist("user")
        assert trust.get_level("user") == "whitelist"

        trust.demote_to_contact("user")

        assert trust.get_level("user") == "contact"

    def test_demote_to_stranger(self, co_dir):
        """Demote from contact to stranger."""
        trust = TrustAgent("careful")
        trust.promote_to_contact("user")
        assert trust.get_level("user") == "contact"

        trust.demote_to_stranger("user")

        assert trust.get_level("user") == "stranger"


class TestBlocking:
    """Test blocking methods."""

    def test_block(self, co_dir):
        """Block a client."""
        trust = TrustAgent("careful")

        trust.block("bad-actor", reason="spam")

        assert trust.get_level("bad-actor") == "blocked"
        assert trust.is_blocked("bad-actor") is True

    def test_unblock(self, co_dir):
        """Unblock a client."""
        trust = TrustAgent("careful")
        trust.block("user")
        assert trust.is_blocked("user") is True

        trust.unblock("user")

        assert trust.is_blocked("user") is False


class TestQueries:
    """Test query methods."""

    def test_get_level_stranger(self, co_dir):
        """Unknown client is stranger."""
        trust = TrustAgent("careful")
        assert trust.get_level("unknown") == "stranger"

    def test_get_level_contact(self, co_dir):
        """Contact level is correct."""
        trust = TrustAgent("careful")
        trust.promote_to_contact("user")
        assert trust.get_level("user") == "contact"

    def test_get_level_whitelist(self, co_dir):
        """Whitelist level is correct."""
        trust = TrustAgent("careful")
        trust.promote_to_whitelist("user")
        assert trust.get_level("user") == "whitelist"

    def test_get_level_blocked(self, co_dir):
        """Blocked level is correct."""
        trust = TrustAgent("careful")
        trust.block("user")
        assert trust.get_level("user") == "blocked"

    def test_is_whitelisted(self, co_dir):
        """is_whitelisted returns correct value."""
        trust = TrustAgent("careful")
        assert trust.is_whitelisted("user") is False
        trust.promote_to_whitelist("user")
        assert trust.is_whitelisted("user") is True

    def test_is_contact(self, co_dir):
        """is_contact returns correct value."""
        trust = TrustAgent("careful")
        assert trust.is_contact("user") is False
        trust.promote_to_contact("user")
        assert trust.is_contact("user") is True

    def test_is_stranger(self, co_dir):
        """is_stranger returns correct value."""
        trust = TrustAgent("careful")
        assert trust.is_stranger("unknown") is True
        trust.promote_to_contact("unknown")
        assert trust.is_stranger("unknown") is False


class TestConfigAccess:
    """Test config property access."""

    def test_config_property(self):
        """Can access parsed config."""
        trust = TrustAgent("careful")
        assert isinstance(trust.config, dict)
        assert "allow" in trust.config or "default" in trust.config

    def test_prompt_property(self):
        """Can access markdown prompt."""
        trust = TrustAgent("careful")
        assert isinstance(trust.prompt, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
