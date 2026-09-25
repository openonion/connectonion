"""Tests for CLI trust command - manages trust lists (contacts, whitelist, blocklist, admins).

Addresses are shown in full (not truncated) so users can easily copy them.
"""

"""
LLM-Note: Tests for CLI trust command (co trust)

What it tests:
- TestTrustCommand: Trust list management
  - test_trust_help: Verify help text display
  - test_trust_no_args_shows_list: Verify default list display
  - test_trust_list: Verify full trust lists display
  - Management of contacts, whitelist, blocklist, and admins

Components under test:
- connectonion.cli.commands.trust_command (trust command)
- Trust list display with full addresses for copying
"""

import pytest

from .argparse_runner import ArgparseCliRunner


def _flat(output):
    """One line, no colour: Rich wraps at 80 columns, and a full address is 66."""
    import re
    return " ".join(re.sub(r"\x1b\[[0-9;]*m", "", output).split())


class TestTrustCommand:
    """Test the trust command for managing trust lists."""

    @pytest.fixture(autouse=True)
    def _agent_project(self, tmp_path, monkeypatch):
        """Every trust command runs inside an explicit agent project.

        These tests used to inherit whichever temporary ``.co`` another CLI
        test happened to leave behind. Once Google auth stopped leaking its
        deleted cwd, they correctly saw that the repository itself is not an
        agent and failed for an unrelated reason.
        """
        (tmp_path / ".co").mkdir()
        monkeypatch.chdir(tmp_path)

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
        assert "Usage:" in _flat(result.output)
        assert "trust" in _flat(result.output)

    def test_trust_no_args_shows_list(self):
        """Test 'co trust' with no args shows the list."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['trust'])

        assert result.exit_code == 0
        assert "Admins" in _flat(result.output)
        assert "Whitelist" in _flat(result.output)
        assert "Contacts" in _flat(result.output)
        assert "Blocklist" in _flat(result.output)

    def test_trust_list(self):
        """Test 'co trust list' shows all trust lists."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['trust', 'list'])

        assert result.exit_code == 0
        assert "Admins" in _flat(result.output)
        assert "Whitelist" in _flat(result.output)
        assert "Contacts" in _flat(result.output)
        assert "Blocklist" in _flat(result.output)
        assert "Lists stored in:" in _flat(result.output)

    def test_trust_list_shows_sections(self):
        """Test list shows all section headers."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['trust', 'list'])

        assert result.exit_code == 0
        # Should always show section headers
        assert "Admins" in _flat(result.output)
        assert "Whitelist" in _flat(result.output)
        assert "Contacts" in _flat(result.output)
        assert "Blocklist" in _flat(result.output)

    def test_trust_add_contact(self):
        """Test 'co trust add <address>' adds to contacts."""
        from connectonion.cli.main import cli
        test_addr = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1"

        result = self.runner.invoke(cli, ['trust', 'add', test_addr])

        assert result.exit_code == 0
        assert "promoted to contact" in _flat(result.output)

    def test_trust_add_whitelist(self):
        """Test 'co trust add <address> -w' adds to whitelist."""
        from connectonion.cli.main import cli
        test_addr = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa2"

        result = self.runner.invoke(cli, ['trust', 'add', test_addr, '-w'])

        assert result.exit_code == 0
        assert "promoted to whitelist" in _flat(result.output)

    def test_trust_level_stranger(self):
        """Test 'co trust level <address>' for unknown address."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['trust', 'level', "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa3"])

        assert result.exit_code == 0
        assert "stranger" in _flat(result.output)
        assert "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa3" in result.output  # Full address shown

    def test_trust_level_contact(self):
        """Test 'co trust level <address>' for contact."""
        from connectonion.cli.main import cli
        test_addr = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa4"

        # Add as contact first
        self.runner.invoke(cli, ['trust', 'add', test_addr])

        # Check level
        result = self.runner.invoke(cli, ['trust', 'level', test_addr])

        assert result.exit_code == 0
        assert "contact" in _flat(result.output)
        assert test_addr in result.output  # Full address shown

    def test_trust_remove(self):
        """Test 'co trust remove <address>' removes from all lists."""
        from connectonion.cli.main import cli
        test_addr = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa5"

        # Add first
        self.runner.invoke(cli, ['trust', 'add', test_addr])

        # Remove
        result = self.runner.invoke(cli, ['trust', 'remove', test_addr])

        assert result.exit_code == 0
        assert "demoted to stranger" in _flat(result.output)

        # Verify removed
        level_result = self.runner.invoke(cli, ['trust', 'level', test_addr])
        assert "stranger" in _flat(level_result.output)

    def test_trust_block(self):
        """Test 'co trust block <address>' blocks an address."""
        from connectonion.cli.main import cli
        test_addr = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa6"

        result = self.runner.invoke(cli, ['trust', 'block', test_addr])

        assert result.exit_code == 0
        assert "blocked" in _flat(result.output)

    def test_trust_block_with_reason(self):
        """Test 'co trust block <address> -r <reason>' includes reason."""
        from connectonion.cli.main import cli

        result = self.runner.invoke(cli, ['trust', 'block', "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa7", '-r', 'spam'])

        assert result.exit_code == 0
        assert "blocked" in _flat(result.output)
        assert "spam" in _flat(result.output)

    def test_trust_unblock(self):
        """Test 'co trust unblock <address>' removes from blocklist."""
        from connectonion.cli.main import cli
        test_addr = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa8"

        # Block first
        self.runner.invoke(cli, ['trust', 'block', test_addr])

        # Unblock
        result = self.runner.invoke(cli, ['trust', 'unblock', test_addr])

        assert result.exit_code == 0
        assert "unblocked" in _flat(result.output)

    def test_trust_shows_full_addresses(self):
        """Test that addresses are shown in full, not truncated."""
        from connectonion.cli.main import cli
        # Long address that would be truncated
        long_addr = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa9"

        # Add to contacts
        self.runner.invoke(cli, ['trust', 'add', long_addr])

        # List should show full address
        result = self.runner.invoke(cli, ['trust', 'list'])

        assert result.exit_code == 0
        assert long_addr in _flat(result.output)


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
        assert "add" in _flat(result.output)
        assert "remove" in _flat(result.output)

    def test_trust_admin_add(self):
        """Test 'co trust admin add <address>' adds an admin."""
        from connectonion.cli.main import cli
        import uuid
        # Use unique address to avoid state pollution
        test_addr = "0x" + uuid.uuid4().hex * 2

        result = self.runner.invoke(cli, ['trust', 'admin', 'add', test_addr])

        assert result.exit_code == 0
        # Either adds successfully or already exists (from previous runs)
        assert "admin" in _flat(result.output)

    def test_trust_admin_remove(self):
        """Test 'co trust admin remove <address>' removes an admin."""
        from connectonion.cli.main import cli
        test_addr = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

        # Add first
        self.runner.invoke(cli, ['trust', 'admin', 'add', test_addr])

        # Remove
        result = self.runner.invoke(cli, ['trust', 'admin', 'remove', test_addr])

        assert result.exit_code == 0
        assert "removed from admins" in _flat(result.output)

    def test_trust_admin_add_duplicate(self):
        """Test adding same admin twice shows appropriate message."""
        from connectonion.cli.main import cli
        test_addr = "0xdddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"

        # Add twice
        self.runner.invoke(cli, ['trust', 'admin', 'add', test_addr])
        result = self.runner.invoke(cli, ['trust', 'admin', 'add', test_addr])

        assert result.exit_code == 0
        assert "already an admin" in _flat(result.output)


class TestTrustLevelNamesTheNextStep:
    """`co trust level` on a contact used to say "Make it a contact: co trust
    add <address>" -- the step already taken. The next step depends on the level."""

    @pytest.fixture(autouse=True)
    def _agent_project(self, tmp_path, monkeypatch):
        (tmp_path / ".co").mkdir()
        monkeypatch.chdir(tmp_path)
        self.runner = ArgparseCliRunner()

    def level(self, addr):
        from connectonion.cli.main import cli
        return _flat(self.runner.invoke(cli, ['trust', 'level', addr]).output)

    def test_a_stranger_is_told_how_to_make_it_a_contact(self):
        assert "co trust add 0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee" in self.level("0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee")

    def test_a_contact_is_not_told_to_become_one(self):
        from connectonion.cli.main import cli
        self.runner.invoke(cli, ['trust', 'add', '0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'])

        out = self.level("0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff")

        assert "Make it a contact" not in out
        assert "co trust add -w 0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff" in out

    def test_a_blocked_address_is_told_how_to_unblock(self):
        from connectonion.cli.main import cli
        self.runner.invoke(cli, ['trust', 'block', '0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'])

        assert "co trust unblock 0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" in self.level("0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")


class TestOnlyAnAddressIsTrusted:
    """Re-test of 1.8.8b9: `co trust add not-an-address` printed
    "✓ not-an-address promoted to contact" and stored it, and `co trust level`
    reported the agent's own admin address as a stranger to be made a contact."""

    @pytest.fixture(autouse=True)
    def _agent_project(self, tmp_path, monkeypatch):
        (tmp_path / ".co").mkdir()
        monkeypatch.chdir(tmp_path)
        self.project = tmp_path
        self.runner = ArgparseCliRunner()

    def run(self, *args):
        from connectonion.cli.main import cli
        result = self.runner.invoke(cli, ['trust', *args])
        return result.exit_code, _flat(result.output)

    @pytest.mark.parametrize("command", [
        ["add", "not-an-address"],
        ["add", "-w", "0x1234"],
        ["level", "not-an-address"],
        ["block", "0x" + "g" * 64],
        ["admin", "add", "alice"],
    ])
    def test_something_else_is_a_usage_error(self, command):
        code, out = self.run(*command)

        assert code == 2, out
        assert "not an agent address" in out
        assert "promoted" not in out

    def test_nothing_is_stored(self):
        self.run("add", "not-an-address")

        assert not (self.project / ".co" / "contacts.txt").exists() or \
            "not-an-address" not in (self.project / ".co" / "contacts.txt").read_text()

    def test_an_entry_an_older_version_stored_can_still_be_removed(self):
        (self.project / ".co" / "contacts.txt").write_text("not-an-address\n")

        code, out = self.run("remove", "not-an-address")

        assert code == 0, out

    def test_the_agents_own_address_is_an_admin_not_a_stranger(self):
        from connectonion import address
        own = address.generate()
        address.save(own, self.project / ".co")

        code, out = self.run("level", own["address"])

        assert code == 0, out
        assert "admin" in out and "own address" in out
        assert "stranger" not in out and "co trust add" not in out

