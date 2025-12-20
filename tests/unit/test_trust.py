"""Unit tests for trust system in host.

Trust has moved from Agent to host() function.
This file tests trust levels, policies, and custom agents.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch

from connectonion.network.host import (
    extract_and_authenticate,
    is_custom_trust,
    get_default_trust,
)
from connectonion.network.trust import create_trust_agent, validate_trust_level, TRUST_LEVELS


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


class TestCreateTrustAgent:
    """Test trust agent creation."""

    def test_create_from_level_open(self):
        """Test creating trust agent from open level."""
        agent = create_trust_agent("open")
        assert agent is not None
        assert agent.name == "trust_agent_open"

    def test_create_from_level_careful(self):
        """Test creating trust agent from careful level."""
        agent = create_trust_agent("careful")
        assert agent is not None
        assert agent.name == "trust_agent_careful"

    def test_create_from_level_strict(self):
        """Test creating trust agent from strict level."""
        agent = create_trust_agent("strict")
        assert agent is not None
        assert agent.name == "trust_agent_strict"

    def test_create_from_policy_inline(self):
        """Test creating trust agent from inline policy."""
        policy = """I trust agents that:
- Are verified
- Pass my tests"""
        agent = create_trust_agent(policy)
        assert agent is not None
        assert agent.name == "trust_agent_custom"

    def test_create_from_policy_file(self, tmp_path):
        """Test creating trust agent from policy file."""
        policy_file = tmp_path / "trust_policy.md"
        policy_file.write_text("# Trust Policy\nI trust verified agents")

        agent = create_trust_agent(str(policy_file))
        assert agent is not None
        assert agent.name == "trust_agent_custom"

    def test_create_from_pathlib_path(self, tmp_path):
        """Test creating trust agent from Path object."""
        policy_file = tmp_path / "policy.md"
        policy_file.write_text("Trust all verified agents")

        agent = create_trust_agent(policy_file)
        assert agent is not None
        assert agent.name == "trust_agent_custom"

    def test_create_from_custom_agent(self):
        """Test that custom agent is returned as-is."""
        from connectonion import Agent

        def verify(agent_id: str) -> bool:
            return True

        guardian = Agent(name="my_guardian", tools=[verify], model="gpt-4o-mini")
        result = create_trust_agent(guardian)
        assert result == guardian

    def test_invalid_level_raises_error(self):
        """Test that invalid trust level raises error."""
        with pytest.raises(ValueError, match="Invalid trust level"):
            create_trust_agent("invalid_level")

    def test_file_not_found_raises_error(self):
        """Test that missing file raises error."""
        with pytest.raises(FileNotFoundError):
            create_trust_agent("/nonexistent/file.md")

    def test_custom_agent_without_tools_raises_error(self):
        """Test that custom agent without tools raises error."""
        from connectonion import Agent
        empty_agent = Agent(name="empty", tools=[], model="gpt-4o-mini")

        with pytest.raises(ValueError, match="must have verification tools"):
            create_trust_agent(empty_agent)

    def test_invalid_type_raises_error(self):
        """Test that invalid types raise error."""
        with pytest.raises(TypeError, match="Trust must be"):
            create_trust_agent(123)

        with pytest.raises(TypeError, match="Trust must be"):
            create_trust_agent([])

        with pytest.raises(TypeError, match="Trust must be"):
            create_trust_agent({})


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

    def test_whitelist_bypasses_signature_verification(self):
        """Test that whitelisted callers bypass signature verification."""
        import time
        data = {
            "payload": {"prompt": "Hello", "timestamp": time.time()},
            "from": "0xgood",
            "signature": "invalid_sig"  # Would fail verification
        }
        prompt, identity, sig_valid, error = extract_and_authenticate(
            data, "strict", whitelist=["0xgood"]
        )
        assert prompt == "Hello"
        assert error is None
        assert sig_valid is True  # Whitelisted = trusted
