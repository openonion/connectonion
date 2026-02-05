"""Tests for trust policy files and fast rules."""

import pytest
from pathlib import Path

from connectonion.network.trust import parse_policy, TRUST_LEVELS
from connectonion.network.trust.factory import PROMPTS_DIR


class TestTrustPolicyFiles:
    """Test trust policy markdown files exist and are valid."""

    def test_prompts_dir_exists(self):
        """Prompts directory exists."""
        assert PROMPTS_DIR.exists(), f"Directory not found: {PROMPTS_DIR}"

    def test_open_policy_exists(self):
        """open.md exists."""
        path = PROMPTS_DIR / "open.md"
        assert path.exists(), f"File not found: {path}"

    def test_careful_policy_exists(self):
        """careful.md exists."""
        path = PROMPTS_DIR / "careful.md"
        assert path.exists(), f"File not found: {path}"

    def test_strict_policy_exists(self):
        """strict.md exists."""
        path = PROMPTS_DIR / "strict.md"
        assert path.exists(), f"File not found: {path}"

    def test_all_levels_have_files(self):
        """All trust levels have corresponding .md files."""
        for level in TRUST_LEVELS:
            path = PROMPTS_DIR / f"{level}.md"
            assert path.exists(), f"Missing policy file for level: {level}"


class TestParsePolicyFiles:
    """Test parsing YAML frontmatter from policy files."""

    def test_parse_open_policy(self):
        """Parse open.md YAML config."""
        path = PROMPTS_DIR / "open.md"
        content = path.read_text(encoding='utf-8')
        config, body = parse_policy(content)

        assert config.get('default') == 'allow'
        assert len(body) > 0

    def test_parse_careful_policy(self):
        """Parse careful.md YAML config."""
        path = PROMPTS_DIR / "careful.md"
        content = path.read_text(encoding='utf-8')
        config, body = parse_policy(content)

        assert 'allow' in config
        assert 'onboard' in config
        assert config.get('default') == 'ask'
        assert len(body) > 0

    def test_parse_strict_policy(self):
        """Parse strict.md YAML config."""
        path = PROMPTS_DIR / "strict.md"
        content = path.read_text(encoding='utf-8')
        config, body = parse_policy(content)

        assert 'whitelisted' in config.get('allow', [])
        assert config.get('default') == 'deny'
        assert len(body) > 0

    def test_open_mentions_development(self):
        """Open policy mentions development."""
        path = PROMPTS_DIR / "open.md"
        content = path.read_text(encoding='utf-8')
        assert "development" in content.lower()

    def test_careful_has_onboard(self):
        """Careful policy has onboard config."""
        path = PROMPTS_DIR / "careful.md"
        content = path.read_text(encoding='utf-8')
        config, _ = parse_policy(content)

        onboard = config.get('onboard', {})
        assert 'invite_code' in onboard
        assert isinstance(onboard['invite_code'], list)

    def test_strict_mentions_whitelist(self):
        """Strict policy mentions whitelist."""
        path = PROMPTS_DIR / "strict.md"
        content = path.read_text(encoding='utf-8')
        assert "whitelist" in content.lower()
