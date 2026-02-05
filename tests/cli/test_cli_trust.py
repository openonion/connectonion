"""Tests for CLI trust command - manages trust lists (contacts, whitelist, blocklist, admins).

Addresses are shown in full (not truncated) so users can easily copy them.
"""

from .argparse_runner import ArgparseCliRunner


class TestTrustCommand:
    """Test the trust command for managing trust lists."""

    def setup_method(self):
        """Setup test environment."""
        self.runner = ArgparseCliRunner()

    def teardown_method(self):
        """Cleanup test environment."""
        pass

    def test_trust_help(self):
        """Test 'co trust --help' shows command-specific help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['trust', '--help'])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "trust" in result.output

    def test_trust_no_args_shows_list(self):
        """Test 'co trust' with no args shows the list."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['trust'])

        assert result.exit_code == 0
        assert "Admins" in result.output
        assert "Whitelist" in result.output
        assert "Contacts" in result.output
        assert "Blocklist" in result.output

    def test_trust_list(self):
        """Test 'co trust list' shows all trust lists."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['trust', 'list'])

        assert result.exit_code == 0
        assert "Admins" in result.output
        assert "Whitelist" in result.output
        assert "Contacts" in result.output
        assert "Blocklist" in result.output
        assert "Lists stored in:" in result.output

    def test_trust_list_shows_sections(self):
        """Test list shows all section headers."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['trust', 'list'])

        assert result.exit_code == 0
        # Should always show section headers
        assert "Admins" in result.output
        assert "Whitelist" in result.output
        assert "Contacts" in result.output
        assert "Blocklist" in result.output

    def test_trust_add_contact(self):
        """Test 'co trust add <address>' adds to contacts."""
        from connectonion.cli.main import cli
        test_addr = "0x1234567890abcdef"

        result = self.runner.invoke(cli, ['trust', 'add', test_addr])

        assert result.exit_code == 0
        assert "promoted to contact" in result.output

    def test_trust_add_whitelist(self):
        """Test 'co trust add <address> -w' adds to whitelist."""
        from connectonion.cli.main import cli
        test_addr = "0xwhitelisttest"

        result = self.runner.invoke(cli, ['trust', 'add', test_addr, '-w'])

        assert result.exit_code == 0
        assert "promoted to whitelist" in result.output

    def test_trust_level_stranger(self):
        """Test 'co trust level <address>' for unknown address."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['trust', 'level', '0xunknown'])

        assert result.exit_code == 0
        assert "stranger" in result.output
        assert "0xunknown" in result.output  # Full address shown

    def test_trust_level_contact(self):
        """Test 'co trust level <address>' for contact."""
        from connectonion.cli.main import cli
        test_addr = "0xcontacttest"

        # Add as contact first
        self.runner.invoke(cli, ['trust', 'add', test_addr])

        # Check level
        result = self.runner.invoke(cli, ['trust', 'level', test_addr])

        assert result.exit_code == 0
        assert "contact" in result.output
        assert test_addr in result.output  # Full address shown

    def test_trust_remove(self):
        """Test 'co trust remove <address>' removes from all lists."""
        from connectonion.cli.main import cli
        test_addr = "0xremovetest"

        # Add first
        self.runner.invoke(cli, ['trust', 'add', test_addr])

        # Remove
        result = self.runner.invoke(cli, ['trust', 'remove', test_addr])

        assert result.exit_code == 0
        assert "demoted to stranger" in result.output

        # Verify removed
        level_result = self.runner.invoke(cli, ['trust', 'level', test_addr])
        assert "stranger" in level_result.output

    def test_trust_block(self):
        """Test 'co trust block <address>' blocks an address."""
        from connectonion.cli.main import cli
        test_addr = "0xblocktest"

        result = self.runner.invoke(cli, ['trust', 'block', test_addr])

        assert result.exit_code == 0
        assert "blocked" in result.output

    def test_trust_block_with_reason(self):
        """Test 'co trust block <address> -r <reason>' includes reason."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['trust', 'block', '0xbadactor', '-r', 'spam'])

        assert result.exit_code == 0
        assert "blocked" in result.output
        assert "spam" in result.output

    def test_trust_unblock(self):
        """Test 'co trust unblock <address>' removes from blocklist."""
        from connectonion.cli.main import cli
        test_addr = "0xunblocktest"

        # Block first
        self.runner.invoke(cli, ['trust', 'block', test_addr])

        # Unblock
        result = self.runner.invoke(cli, ['trust', 'unblock', test_addr])

        assert result.exit_code == 0
        assert "unblocked" in result.output

    def test_trust_shows_full_addresses(self):
        """Test that addresses are shown in full, not truncated."""
        from connectonion.cli.main import cli
        # Long address that would be truncated
        long_addr = "0x1234567890abcdef1234567890abcdef12345678"

        # Add to contacts
        self.runner.invoke(cli, ['trust', 'add', long_addr])

        # List should show full address
        result = self.runner.invoke(cli, ['trust', 'list'])

        assert result.exit_code == 0
        assert long_addr in result.output


class TestTrustAdminCommand:
    """Test the trust admin subcommand."""

    def setup_method(self):
        """Setup test environment."""
        self.runner = ArgparseCliRunner()

    def teardown_method(self):
        """Cleanup test environment."""
        pass

    def test_trust_admin_help(self):
        """Test 'co trust admin --help' shows subcommand help."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['trust', 'admin', '--help'])

        assert result.exit_code == 0
        assert "add" in result.output
        assert "remove" in result.output

    def test_trust_admin_add(self):
        """Test 'co trust admin add <address>' adds an admin."""
        from connectonion.cli.main import cli
        import uuid
        # Use unique address to avoid state pollution
        test_addr = f"0xadmintest_{uuid.uuid4().hex[:8]}"

        result = self.runner.invoke(cli, ['trust', 'admin', 'add', test_addr])

        assert result.exit_code == 0
        # Either adds successfully or already exists (from previous runs)
        assert "admin" in result.output

    def test_trust_admin_remove(self):
        """Test 'co trust admin remove <address>' removes an admin."""
        from connectonion.cli.main import cli
        test_addr = "0xadminremove"

        # Add first
        self.runner.invoke(cli, ['trust', 'admin', 'add', test_addr])

        # Remove
        result = self.runner.invoke(cli, ['trust', 'admin', 'remove', test_addr])

        assert result.exit_code == 0
        assert "removed from admins" in result.output

    def test_trust_admin_add_duplicate(self):
        """Test adding same admin twice shows appropriate message."""
        from connectonion.cli.main import cli
        test_addr = "0xduplicateadmin"

        # Add twice
        self.runner.invoke(cli, ['trust', 'admin', 'add', test_addr])
        result = self.runner.invoke(cli, ['trust', 'admin', 'add', test_addr])

        assert result.exit_code == 0
        assert "already an admin" in result.output
