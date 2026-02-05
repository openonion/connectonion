"""Unit tests for trust system in host.

Trust has moved from Agent to host() function.
This file tests trust levels, policies, and custom agents.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, Mock

from connectonion.network.host import (
    extract_and_authenticate,
    is_custom_trust,
    get_default_trust,
)
from connectonion.network.trust import TrustAgent, validate_trust_level, TRUST_LEVELS


@pytest.fixture
def mock_llm():
    """Mock LLM to avoid real API client initialization."""
    from connectonion.core.llm import LLMResponse
    from connectonion.core.usage import TokenUsage

    mock = Mock()
    mock.model = "mock-model"
    mock.complete.return_value = LLMResponse(
        content="Mock response",
        tool_calls=[],
        raw_response=None,
        usage=TokenUsage(),
    )
    return mock


@pytest.fixture(autouse=True)
def patch_create_llm(mock_llm):
    """Auto-patch create_llm to avoid real OpenAI client initialization."""
    # Need to patch where it's imported (in Agent module), not where it's defined
    with patch('connectonion.core.agent.create_llm', return_value=mock_llm):
        yield


class TestTrustLevels:
    """Test trust level functionality."""

    def test_trust_levels_defined(self):
        """Test that three trust levels are defined."""
        assert TRUST_LEVELS == ["open", "careful", "strict"]

    def test_validate_trust_level(self):
        """Test trust level validation."""
        assert validate_trust_level("open") is True
        assert validate_trust_level("careful") is True
        assert validate_trust_level("strict") is True
        assert validate_trust_level("invalid") is False
        assert validate_trust_level("tested") is False

    def test_validate_trust_level_case_insensitive(self):
        """Test that trust level validation is case insensitive."""
        assert validate_trust_level("Open") is True
        assert validate_trust_level("CAREFUL") is True
        assert validate_trust_level("Strict") is True

    def test_get_default_trust_development(self):
        """Test default trust in development environment."""
        with patch.dict(os.environ, {"CONNECTONION_ENV": "development"}):
            assert get_default_trust() == "open"

    def test_get_default_trust_production(self):
        """Test default trust in production environment."""
        with patch.dict(os.environ, {"CONNECTONION_ENV": "production"}):
            assert get_default_trust() == "strict"

    def test_get_default_trust_staging(self):
        """Test default trust in staging environment."""
        with patch.dict(os.environ, {"CONNECTONION_ENV": "staging"}):
            assert get_default_trust() == "careful"

    def test_get_default_trust_test(self):
        """Test default trust in test environment."""
        with patch.dict(os.environ, {"CONNECTONION_ENV": "test"}):
            assert get_default_trust() == "careful"

    def test_get_default_trust_unset(self):
        """Test default trust when environment is unset."""
        with patch.dict(os.environ, {"CONNECTONION_ENV": ""}):
            assert get_default_trust() == "careful"


class TestIsCustomTrust:
    """Test is_custom_trust function."""

    def test_level_is_not_custom(self):
        """Test that trust levels are not custom."""
        assert is_custom_trust("open") is False
        assert is_custom_trust("careful") is False
        assert is_custom_trust("strict") is False

    def test_policy_is_custom(self):
        """Test that policy strings are custom."""
        assert is_custom_trust("I trust agents that pass tests") is True
        assert is_custom_trust("./trust_policy.md") is True

    def test_agent_is_custom(self):
        """Test that Agent instances are custom."""
        from connectonion import Agent
        agent = Agent(name="guardian", tools=[], model="gpt-4o-mini")
        assert is_custom_trust(agent) is True


class TestTrustAgentCreation:
    """Test TrustAgent creation."""

    def test_create_from_level_open(self):
        """Test creating TrustAgent from open level."""
        trust = TrustAgent("open")
        assert trust is not None
        assert trust.trust == "open"

    def test_create_from_level_careful(self):
        """Test creating TrustAgent from careful level."""
        trust = TrustAgent("careful")
        assert trust is not None
        assert trust.trust == "careful"

    def test_create_from_level_strict(self):
        """Test creating TrustAgent from strict level."""
        trust = TrustAgent("strict")
        assert trust is not None
        assert trust.trust == "strict"

    def test_create_from_policy_file(self, tmp_path):
        """Test creating TrustAgent from policy file."""
        policy_file = tmp_path / "trust_policy.md"
        policy_file.write_text("---\nallow: [whitelisted]\ndefault: deny\n---\n# Trust Policy\nI trust verified agents")

        trust = TrustAgent(str(policy_file))
        assert trust is not None
        assert "allow" in trust.config

    def test_create_from_pathlib_path(self, tmp_path):
        """Test creating TrustAgent from Path object."""
        policy_file = tmp_path / "policy.md"
        policy_file.write_text("---\ndefault: allow\n---\nTrust all verified agents")

        trust = TrustAgent(str(policy_file))
        assert trust is not None
        assert trust.config.get("default") == "allow"

    def test_has_trust_methods(self):
        """Test that TrustAgent has all expected methods."""
        trust = TrustAgent("open")
        # Trust level methods
        assert hasattr(trust, "should_allow")
        assert hasattr(trust, "get_level")
        assert hasattr(trust, "promote_to_contact")
        assert hasattr(trust, "promote_to_whitelist")
        assert hasattr(trust, "demote_to_contact")
        assert hasattr(trust, "demote_to_stranger")
        assert hasattr(trust, "block")
        assert hasattr(trust, "unblock")
        # Admin methods
        assert hasattr(trust, "is_admin")
        assert hasattr(trust, "is_super_admin")
        assert hasattr(trust, "add_admin")
        assert hasattr(trust, "remove_admin")

    def test_invalid_level_creates_empty_config(self):
        """Test that invalid trust level creates TrustAgent with empty config.

        Unknown strings that aren't trust levels or file paths result in empty config.
        """
        trust = TrustAgent("invalid_level")
        assert trust is not None
        assert trust.config == {}

    def test_nonexistent_file_creates_empty_config(self):
        """Test that missing file path creates TrustAgent with empty config."""
        trust = TrustAgent("/nonexistent/file.md")
        assert trust is not None
        assert trust.config == {}


class TestExtractAndAuthenticate:
    """Test extract_and_authenticate with trust.

    Protocol requirement: ALL requests must be signed.
    Trust levels only apply AFTER signature verification.
    """

    def test_unsigned_request_rejected(self):
        """Test that unsigned requests are always rejected (protocol requirement)."""
        data = {"prompt": "Hello"}
        prompt, identity, sig_valid, error = extract_and_authenticate(data, "open")
        assert error == "unauthorized: signed request required"

    def test_unsigned_request_rejected_even_with_from(self):
        """Test that requests without signature are rejected even with 'from' field."""
        data = {"prompt": "Hello", "from": "0xabc"}
        prompt, identity, sig_valid, error = extract_and_authenticate(data, "careful")
        assert error == "unauthorized: signed request required"

    def test_unsigned_request_rejected_for_all_trust_levels(self):
        """Test that all trust levels require signed requests."""
        data = {"prompt": "Hello", "from": "0xabc"}
        for trust in ["open", "careful", "strict"]:
            prompt, identity, sig_valid, error = extract_and_authenticate(data, trust)
            assert error == "unauthorized: signed request required", f"Trust={trust} should reject unsigned"

    def test_blacklist_checked_on_signed_request(self):
        """Test that blacklist is checked on signed requests."""
        import time
        data = {
            "payload": {"prompt": "Hello", "timestamp": time.time()},
            "from": "0xbad",
            "signature": "0x1234"
        }
        prompt, identity, sig_valid, error = extract_and_authenticate(
            data, "open", blacklist=["0xbad"]
        )
        assert error == "forbidden: blacklisted"

    def test_whitelist_requires_valid_signature(self):
        """Test that whitelisted callers still need valid signatures.

        Whitelist bypasses trust POLICY, not signature VERIFICATION.
        Even whitelisted identities must prove their identity with a valid signature.
        """
        import time
        data = {
            "payload": {"prompt": "Hello", "timestamp": time.time()},
            "from": "0xgood",
            "signature": "invalid_sig"  # Invalid signature should fail
        }
        prompt, identity, sig_valid, error = extract_and_authenticate(
            data, "strict", whitelist=["0xgood"]
        )
        # Should fail because signature is invalid (whitelist doesn't bypass signature!)
        assert error == "unauthorized: invalid signature"
        assert sig_valid is False
