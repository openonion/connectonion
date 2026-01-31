"""Tests for network/trust/prompts.py - Trust level prompts."""

import pytest

from connectonion.network.trust.prompts import (
    TRUST_PROMPTS,
    get_trust_prompt,
    get_open_trust_prompt,
    get_careful_trust_prompt,
    get_strict_trust_prompt,
)


class TestTrustPrompts:
    """Test TRUST_PROMPTS dictionary."""

    def test_has_three_levels(self):
        """TRUST_PROMPTS has exactly three levels."""
        assert len(TRUST_PROMPTS) == 3
        assert set(TRUST_PROMPTS.keys()) == {"open", "careful", "strict"}

    def test_open_prompt_exists(self):
        """Open trust prompt exists and is non-empty."""
        assert "open" in TRUST_PROMPTS
        assert len(TRUST_PROMPTS["open"]) > 0

    def test_careful_prompt_exists(self):
        """Careful trust prompt exists and is non-empty."""
        assert "careful" in TRUST_PROMPTS
        assert len(TRUST_PROMPTS["careful"]) > 0

    def test_strict_prompt_exists(self):
        """Strict trust prompt exists and is non-empty."""
        assert "strict" in TRUST_PROMPTS
        assert len(TRUST_PROMPTS["strict"]) > 0

    def test_prompts_are_strings(self):
        """All prompts are strings."""
        for level, prompt in TRUST_PROMPTS.items():
            assert isinstance(prompt, str), f"Prompt for {level} is not a string"

    def test_open_prompt_mentions_development(self):
        """Open prompt mentions development context."""
        prompt = TRUST_PROMPTS["open"]
        assert "development" in prompt.lower()

    def test_careful_prompt_mentions_verification(self):
        """Careful prompt mentions verification."""
        prompt = TRUST_PROMPTS["careful"]
        assert "verify" in prompt.lower() or "verification" in prompt.lower()

    def test_strict_prompt_mentions_security(self):
        """Strict prompt mentions security."""
        prompt = TRUST_PROMPTS["strict"]
        assert "security" in prompt.lower()


class TestGetTrustPrompt:
    """Test get_trust_prompt function."""

    def test_get_open(self):
        """Get open trust prompt."""
        result = get_trust_prompt("open")
        assert result == TRUST_PROMPTS["open"]

    def test_get_careful(self):
        """Get careful trust prompt."""
        result = get_trust_prompt("careful")
        assert result == TRUST_PROMPTS["careful"]

    def test_get_strict(self):
        """Get strict trust prompt."""
        result = get_trust_prompt("strict")
        assert result == TRUST_PROMPTS["strict"]

    def test_case_insensitive(self):
        """Level lookup is case insensitive."""
        assert get_trust_prompt("OPEN") == TRUST_PROMPTS["open"]
        assert get_trust_prompt("Careful") == TRUST_PROMPTS["careful"]
        assert get_trust_prompt("STRICT") == TRUST_PROMPTS["strict"]

    def test_invalid_level_raises(self):
        """Invalid level raises ValueError."""
        with pytest.raises(ValueError, match="Invalid trust level"):
            get_trust_prompt("invalid")

    def test_invalid_level_message_lists_valid_options(self):
        """Error message lists valid options."""
        with pytest.raises(ValueError) as exc_info:
            get_trust_prompt("wrong")

        error_msg = str(exc_info.value)
        assert "open" in error_msg
        assert "careful" in error_msg
        assert "strict" in error_msg


class TestConvenienceFunctions:
    """Test convenience functions for each level."""

    def test_get_open_trust_prompt(self):
        """get_open_trust_prompt returns open prompt."""
        result = get_open_trust_prompt()
        assert result == TRUST_PROMPTS["open"]

    def test_get_careful_trust_prompt(self):
        """get_careful_trust_prompt returns careful prompt."""
        result = get_careful_trust_prompt()
        assert result == TRUST_PROMPTS["careful"]

    def test_get_strict_trust_prompt(self):
        """get_strict_trust_prompt returns strict prompt."""
        result = get_strict_trust_prompt()
        assert result == TRUST_PROMPTS["strict"]

    def test_convenience_functions_match_get_trust_prompt(self):
        """Convenience functions return same as get_trust_prompt."""
        assert get_open_trust_prompt() == get_trust_prompt("open")
        assert get_careful_trust_prompt() == get_trust_prompt("careful")
        assert get_strict_trust_prompt() == get_trust_prompt("strict")
