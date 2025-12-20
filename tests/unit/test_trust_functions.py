#!/usr/bin/env python3
"""
Unit tests for trust_functions.py - trust verification tools.

Tests cover:
- Whitelist checking with real file I/O
- Exact agent ID matching
- Wildcard pattern matching (* support)
- Comment and empty line handling
- Missing whitelist file
- File read errors
- test_capability() string formatting
- verify_agent() string formatting
- get_trust_verification_tools() returns correct functions

Critical paths from coverage analysis:
- check_whitelist() file reading (line 26-45)
- Wildcard matching logic (line 38-41)
- Error handling (line 43-44)
- Missing file case (line 45)
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open

# Import with aliases to avoid pytest collecting test_capability as a test
from connectonion.network.trust_functions import (
    check_whitelist,
    test_capability as capability_test_func,
    verify_agent,
    get_trust_verification_tools
)


class TestCheckWhitelist:
    """Test whitelist checking with various scenarios."""

    def test_exact_match_on_whitelist(self, tmp_path):
        """Test that exact agent ID match is found on whitelist."""
        # Create temporary whitelist file
        whitelist_file = tmp_path / "trusted.txt"
        whitelist_file.write_text("agent-123\nagent-456\n")

        with patch('connectonion.network.trust_functions.Path.home', return_value=tmp_path.parent):
            # Mock .connectonion directory structure
            connectonion_dir = tmp_path.parent / ".connectonion"
            connectonion_dir.mkdir(exist_ok=True)
            (connectonion_dir / "trusted.txt").write_text("agent-123\nagent-456\n")

            result = check_whitelist("agent-123")
            assert "is on the whitelist" in result
            assert "agent-123" in result

    def test_not_on_whitelist(self, tmp_path):
        """Test that agent not on whitelist is detected."""
        connectonion_dir = tmp_path / ".connectonion"
        connectonion_dir.mkdir()
        whitelist_file = connectonion_dir / "trusted.txt"
        whitelist_file.write_text("agent-123\nagent-456\n")

        with patch('connectonion.network.trust_functions.Path.home', return_value=tmp_path):
            result = check_whitelist("agent-999")
            assert "NOT on the whitelist" in result
            assert "agent-999" in result

    def test_wildcard_pattern_match(self, tmp_path):
        """Test that wildcard patterns match correctly."""
        connectonion_dir = tmp_path / ".connectonion"
        connectonion_dir.mkdir()
        whitelist_file = connectonion_dir / "trusted.txt"
        whitelist_file.write_text("trusted-*\n*.openonion.ai\n")

        with patch('connectonion.network.trust_functions.Path.home', return_value=tmp_path):
            # Test prefix wildcard
            result = check_whitelist("trusted-agent-123")
            assert "matches whitelist pattern" in result
            assert "trusted-*" in result

            # Test suffix wildcard
            result = check_whitelist("agent.openonion.ai")
            assert "matches whitelist pattern" in result
            assert "*.openonion.ai" in result

    def test_wildcard_substring_matching(self, tmp_path):
        """Test that wildcard uses simple substring matching (not glob)."""
        connectonion_dir = tmp_path / ".connectonion"
        connectonion_dir.mkdir()
        whitelist_file = connectonion_dir / "trusted.txt"
        # Wildcard implementation: line.replace('*', '') checks if pattern is substring
        whitelist_file.write_text("agent*123\n")

        with patch('connectonion.network.trust_functions.Path.home', return_value=tmp_path):
            # "agent*123" becomes "agent123" - should match agent_id containing "agent123" as substring
            result = check_whitelist("prefixagent123suffix")
            assert "matches whitelist pattern" in result

            # Should NOT match if the substring isn't present
            result = check_whitelist("agent-456-123")  # "agent123" not in "agent-456-123"
            assert "NOT on the whitelist" in result

    def test_comments_ignored(self, tmp_path):
        """Test that comment lines are ignored."""
        connectonion_dir = tmp_path / ".connectonion"
        connectonion_dir.mkdir()
        whitelist_file = connectonion_dir / "trusted.txt"
        whitelist_file.write_text("# This is a comment\nagent-123\n# Another comment\n")

        with patch('connectonion.network.trust_functions.Path.home', return_value=tmp_path):
            result = check_whitelist("agent-123")
            assert "is on the whitelist" in result

            # Comment itself should not match
            result = check_whitelist("# This is a comment")
            assert "NOT on the whitelist" in result

    def test_empty_lines_ignored(self, tmp_path):
        """Test that empty lines are ignored."""
        connectonion_dir = tmp_path / ".connectonion"
        connectonion_dir.mkdir()
        whitelist_file = connectonion_dir / "trusted.txt"
        whitelist_file.write_text("\n\nagent-123\n\n\nagent-456\n\n")

        with patch('connectonion.network.trust_functions.Path.home', return_value=tmp_path):
            result = check_whitelist("agent-123")
            assert "is on the whitelist" in result

            result = check_whitelist("agent-456")
            assert "is on the whitelist" in result

    def test_whitespace_trimmed(self, tmp_path):
        """Test that whitespace is properly trimmed."""
        connectonion_dir = tmp_path / ".connectonion"
        connectonion_dir.mkdir()
        whitelist_file = connectonion_dir / "trusted.txt"
        whitelist_file.write_text("  agent-123  \n\t agent-456 \t\n")

        with patch('connectonion.network.trust_functions.Path.home', return_value=tmp_path):
            result = check_whitelist("agent-123")
            assert "is on the whitelist" in result

            result = check_whitelist("agent-456")
            assert "is on the whitelist" in result

    def test_no_whitelist_file(self, tmp_path):
        """Test behavior when whitelist file doesn't exist."""
        # Point to directory without trusted.txt
        with patch('connectonion.network.trust_functions.Path.home', return_value=tmp_path):
            result = check_whitelist("any-agent")
            assert "No whitelist file found" in result
            assert "~/.connectonion/trusted.txt" in result

    def test_whitelist_read_error(self, tmp_path):
        """Test error handling when file read fails."""
        connectonion_dir = tmp_path / ".connectonion"
        connectonion_dir.mkdir()
        whitelist_file = connectonion_dir / "trusted.txt"

        # Create file but make it unreadable
        whitelist_file.write_text("agent-123\n")

        with patch('connectonion.network.trust_functions.Path.home', return_value=tmp_path):
            # Mock read_text to raise an exception
            with patch.object(Path, 'read_text', side_effect=PermissionError("Access denied")):
                result = check_whitelist("agent-123")
                assert "Error reading whitelist" in result
                assert "Access denied" in result or "PermissionError" in result

    def test_empty_whitelist_file(self, tmp_path):
        """Test behavior with empty whitelist file."""
        connectonion_dir = tmp_path / ".connectonion"
        connectonion_dir.mkdir()
        whitelist_file = connectonion_dir / "trusted.txt"
        whitelist_file.write_text("")

        with patch('connectonion.network.trust_functions.Path.home', return_value=tmp_path):
            result = check_whitelist("any-agent")
            assert "NOT on the whitelist" in result

    def test_only_comments_and_whitespace(self, tmp_path):
        """Test whitelist file with only comments and whitespace."""
        connectonion_dir = tmp_path / ".connectonion"
        connectonion_dir.mkdir()
        whitelist_file = connectonion_dir / "trusted.txt"
        whitelist_file.write_text("# Comment 1\n\n# Comment 2\n\n")

        with patch('connectonion.network.trust_functions.Path.home', return_value=tmp_path):
            result = check_whitelist("any-agent")
            assert "NOT on the whitelist" in result

    def test_case_sensitive_matching(self, tmp_path):
        """Test that matching is case-sensitive."""
        connectonion_dir = tmp_path / ".connectonion"
        connectonion_dir.mkdir()
        whitelist_file = connectonion_dir / "trusted.txt"
        whitelist_file.write_text("Agent-123\n")

        with patch('connectonion.network.trust_functions.Path.home', return_value=tmp_path):
            # Exact case should match
            result = check_whitelist("Agent-123")
            assert "is on the whitelist" in result

            # Different case should NOT match
            result = check_whitelist("agent-123")
            assert "NOT on the whitelist" in result

    def test_multiple_wildcards(self, tmp_path):
        """Test multiple wildcard patterns in whitelist."""
        connectonion_dir = tmp_path / ".connectonion"
        connectonion_dir.mkdir()
        whitelist_file = connectonion_dir / "trusted.txt"
        whitelist_file.write_text("trusted-*\nverified-*\n*.safe.com\n")

        with patch('connectonion.network.trust_functions.Path.home', return_value=tmp_path):
            result = check_whitelist("trusted-agent-999")
            assert "matches whitelist pattern" in result
            assert "trusted-*" in result

            result = check_whitelist("verified-bot-42")
            assert "matches whitelist pattern" in result
            assert "verified-*" in result

            result = check_whitelist("agent.safe.com")
            assert "matches whitelist pattern" in result
            assert "*.safe.com" in result


class TestCapability:
    """Test capability testing function."""

    def test_capability_basic(self):
        """Test basic capability test string formatting."""
        result = capability_test_func("agent-123", "math", "correct answer")
        assert "Testing agent-123" in result
        assert "math" in result
        assert "correct answer" in result

    def test_capability_with_complex_test(self):
        """Test capability with complex test description."""
        result = capability_test_func(
            "agent-math-bot",
            "solve equation: 2x + 5 = 15",
            "x = 5"
        )
        assert "agent-math-bot" in result
        assert "solve equation" in result
        assert "x = 5" in result

    def test_capability_empty_strings(self):
        """Test capability with empty strings."""
        result = capability_test_func("agent", "", "")
        assert "Testing agent" in result
        assert "expecting:" in result


class TestVerifyAgent:
    """Test agent verification function."""

    def test_verify_basic(self):
        """Test basic agent verification."""
        result = verify_agent("agent-123")
        assert "Verifying agent: agent-123" in result
        assert "Info:" in result

    def test_verify_with_info(self):
        """Test verification with agent info."""
        result = verify_agent("agent-456", "Math specialist, v2.0")
        assert "agent-456" in result
        assert "Math specialist, v2.0" in result

    def test_verify_empty_info(self):
        """Test verification with explicitly empty info."""
        result = verify_agent("agent-789", "")
        assert "agent-789" in result
        assert "Info:" in result

    def test_verify_long_info(self):
        """Test verification with long agent info."""
        long_info = "This is a very long description " * 20
        result = verify_agent("agent-long", long_info)
        assert "agent-long" in result
        assert long_info in result


class TestGetTrustVerificationTools:
    """Test trust verification tools list."""

    def test_returns_list_of_functions(self):
        """Test that function returns list of callables."""
        tools = get_trust_verification_tools()
        assert isinstance(tools, list)
        assert len(tools) == 3

    def test_contains_check_whitelist(self):
        """Test that check_whitelist is in tools list."""
        tools = get_trust_verification_tools()
        assert check_whitelist in tools

    def test_contains_test_capability(self):
        """Test that test_capability is in tools list."""
        tools = get_trust_verification_tools()
        # Check using the actual function from the module
        from connectonion.network.trust_functions import test_capability
        assert test_capability in tools

    def test_contains_verify_agent(self):
        """Test that verify_agent is in tools list."""
        tools = get_trust_verification_tools()
        assert verify_agent in tools

    def test_all_tools_callable(self):
        """Test that all returned tools are callable."""
        tools = get_trust_verification_tools()
        for tool in tools:
            assert callable(tool)

    def test_tools_order(self):
        """Test that tools are in expected order."""
        from connectonion.network.trust_functions import test_capability
        tools = get_trust_verification_tools()
        assert tools[0] == check_whitelist
        assert tools[1] == test_capability
        assert tools[2] == verify_agent


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_whitelist_check_in_tools_list(self, tmp_path):
        """Test that whitelist checking works when retrieved from tools list."""
        # Setup whitelist
        connectonion_dir = tmp_path / ".connectonion"
        connectonion_dir.mkdir()
        whitelist_file = connectonion_dir / "trusted.txt"
        whitelist_file.write_text("agent-123\n")

        # Get tools
        tools = get_trust_verification_tools()
        whitelist_tool = tools[0]

        with patch('connectonion.network.trust_functions.Path.home', return_value=tmp_path):
            result = whitelist_tool("agent-123")
            assert "is on the whitelist" in result

    def test_all_tools_executable(self):
        """Test that all tools can be executed without errors."""
        tools = get_trust_verification_tools()

        # Execute check_whitelist (will return "No whitelist file" but shouldn't error)
        result = tools[0]("test-agent")
        assert isinstance(result, str)

        # Execute test_capability
        result = tools[1]("agent", "test", "expected")
        assert isinstance(result, str)

        # Execute verify_agent
        result = tools[2]("agent", "info")
        assert isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
