"""Tests for fast_rules.py - YAML parsing and rule execution."""

import pytest
from pathlib import Path

from connectonion.network.trust.fast_rules import parse_policy, evaluate_request
from connectonion.network.trust import tools


@pytest.fixture
def temp_co_dir(tmp_path, monkeypatch):
    """Create temp ~/.co/ directory for tests."""
    co_dir = tmp_path / ".co"
    co_dir.mkdir()
    monkeypatch.setattr(tools, "CO_DIR", co_dir)
    return co_dir


class TestParsePolicy:
    """Test YAML frontmatter parsing."""

    def test_parse_simple_yaml(self):
        """Parse simple YAML frontmatter."""
        policy = """---
default: allow
---

# Body
"""
        config, body = parse_policy(policy)
        assert config["default"] == "allow"
        assert "Body" in body

    def test_parse_complex_yaml(self):
        """Parse complex YAML with nested config."""
        policy = """---
allow:
  - whitelisted
  - contact
onboard:
  invite_code: [CODE1, CODE2]
  payment: 10
default: ask
---

# Trust Agent
"""
        config, body = parse_policy(policy)
        assert config["allow"] == ["whitelisted", "contact"]
        assert config["onboard"]["invite_code"] == ["CODE1", "CODE2"]
        assert config["onboard"]["payment"] == 10
        assert config["default"] == "ask"

    def test_parse_no_yaml(self):
        """Handle markdown without YAML frontmatter."""
        policy = "# Just markdown\n\nNo YAML here."
        config, body = parse_policy(policy)
        assert config == {}
        assert "Just markdown" in body

    def test_parse_empty_yaml(self):
        """Handle empty YAML frontmatter."""
        policy = """---
---

# Body
"""
        config, body = parse_policy(policy)
        assert config == {}
        assert "Body" in body


class TestEvaluateRequestOpenMode:
    """Test evaluate_request with default: allow config."""

    def test_default_allow_allows_everyone(self, temp_co_dir):
        """default: allow allows any request."""
        config = {"default": "allow"}
        result = evaluate_request(config, "any-client", {})
        assert result == "allow"


class TestEvaluateRequestBlocklist:
    """Test blocklist checking."""

    def test_blocked_client_denied(self, temp_co_dir):
        """Blocked client is denied."""
        (temp_co_dir / "blocklist.txt").write_text("bad-client\n")

        config = {"deny": ["blocked"]}
        result = evaluate_request(config, "bad-client", {})
        assert result == "deny"

    def test_unblocked_client_not_denied(self, temp_co_dir):
        """Non-blocked client is not denied by blocklist."""
        (temp_co_dir / "blocklist.txt").write_text("other-client\n")

        config = {"deny": ["blocked"], "default": "allow"}
        result = evaluate_request(config, "good-client", {})
        assert result == "allow"


class TestEvaluateRequestWhitelist:
    """Test whitelist checking."""

    def test_whitelisted_client_allowed(self, temp_co_dir):
        """Whitelisted client is allowed."""
        (temp_co_dir / "whitelist.txt").write_text("trusted-client\n")

        config = {"allow": ["whitelisted"]}
        result = evaluate_request(config, "trusted-client", {})
        assert result == "allow"

    def test_whitelist_wildcard(self, temp_co_dir):
        """Whitelist wildcard pattern works."""
        (temp_co_dir / "whitelist.txt").write_text("payment-*\n")

        config = {"allow": ["whitelisted"]}
        result = evaluate_request(config, "payment-gateway-1", {})
        assert result == "allow"


class TestEvaluateRequestStrictMode:
    """Test strict mode (whitelist only)."""

    def test_strict_allows_whitelisted(self, temp_co_dir):
        """Strict mode allows whitelisted clients."""
        (temp_co_dir / "whitelist.txt").write_text("trusted\n")

        config = {"allow": ["whitelisted"], "default": "deny"}
        result = evaluate_request(config, "trusted", {})
        assert result == "allow"

    def test_strict_denies_others(self, temp_co_dir):
        """Strict mode denies non-whitelisted clients."""
        config = {"allow": ["whitelisted"], "default": "deny"}
        result = evaluate_request(config, "unknown-client", {})
        assert result == "deny"


class TestEvaluateRequestContact:
    """Test contact access."""

    def test_contact_allowed(self, temp_co_dir):
        """Contact is allowed when in allow list."""
        (temp_co_dir / "contacts.txt").write_text("existing-contact\n")

        config = {"allow": ["whitelisted", "contact"]}
        result = evaluate_request(config, "existing-contact", {})
        assert result == "allow"

    def test_contact_not_allowed_if_not_in_list(self, temp_co_dir):
        """Contact not allowed if 'contact' not in allow list."""
        (temp_co_dir / "contacts.txt").write_text("existing-contact\n")

        config = {"allow": ["whitelisted"], "default": "deny"}
        result = evaluate_request(config, "existing-contact", {})
        assert result == "deny"


class TestEvaluateRequestOnboard:
    """Test onboarding (stranger → contact)."""

    def test_valid_invite_code_onboards(self, temp_co_dir):
        """Valid invite code promotes to contact and allows."""
        config = {
            "allow": ["contact"],
            "onboard": {"invite_code": ["BETA2024", "FRIEND123"]}
        }
        request = {"invite_code": "BETA2024"}
        result = evaluate_request(config, "new-client", request)
        assert result == "allow"
        assert tools.is_contact("new-client")

    def test_invalid_invite_code_rejected(self, temp_co_dir):
        """Invalid invite code doesn't onboard."""
        config = {
            "onboard": {"invite_code": ["BETA2024"]},
            "default": "deny"
        }
        request = {"invite_code": "WRONG"}
        result = evaluate_request(config, "client", request)
        assert result == "deny"
        assert not tools.is_contact("client")

    def test_payment_onboards(self, temp_co_dir):
        """Sufficient payment promotes to contact and allows."""
        config = {"onboard": {"payment": 10}}
        request = {"payment": 15}
        result = evaluate_request(config, "paying-client", request)
        assert result == "allow"
        assert tools.is_contact("paying-client")

    def test_exact_payment_works(self, temp_co_dir):
        """Exact payment amount is accepted."""
        config = {"onboard": {"payment": 10}}
        request = {"payment": 10}
        result = evaluate_request(config, "client", request)
        assert result == "allow"

    def test_insufficient_payment_rejected(self, temp_co_dir):
        """Insufficient payment doesn't onboard."""
        config = {"onboard": {"payment": 10}, "default": "deny"}
        request = {"payment": 5}
        result = evaluate_request(config, "client", request)
        assert result == "deny"


class TestEvaluateRequestDefault:
    """Test default action for strangers."""

    def test_default_allow(self, temp_co_dir):
        """default: allow allows strangers."""
        config = {"default": "allow"}
        result = evaluate_request(config, "stranger", {})
        assert result == "allow"

    def test_default_deny(self, temp_co_dir):
        """default: deny denies strangers."""
        config = {"default": "deny"}
        result = evaluate_request(config, "stranger", {})
        assert result == "deny"

    def test_default_ask(self, temp_co_dir):
        """default: ask returns None for LLM evaluation."""
        config = {"default": "ask"}
        result = evaluate_request(config, "stranger", {})
        assert result is None

    def test_default_is_deny(self, temp_co_dir):
        """Default fallback is deny."""
        config = {}
        result = evaluate_request(config, "stranger", {})
        assert result == "deny"


class TestEvaluateRequestPriority:
    """Test rule evaluation priority."""

    def test_deny_before_allow(self, temp_co_dir):
        """Deny is checked before allow."""
        (temp_co_dir / "blocklist.txt").write_text("client\n")
        (temp_co_dir / "whitelist.txt").write_text("client\n")

        config = {"deny": ["blocked"], "allow": ["whitelisted"]}
        result = evaluate_request(config, "client", {})
        assert result == "deny"

    def test_allow_before_onboard(self, temp_co_dir):
        """Allowed client doesn't need to onboard."""
        (temp_co_dir / "whitelist.txt").write_text("trusted\n")

        config = {
            "allow": ["whitelisted"],
            "onboard": {"invite_code": ["CODE"]}
        }
        result = evaluate_request(config, "trusted", {})
        assert result == "allow"
