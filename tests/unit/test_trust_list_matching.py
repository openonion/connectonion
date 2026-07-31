"""What a line in whitelist.txt or blocklist.txt actually matches.

Both defects here fail *open* on the whitelist, which is the direction that
matters: `_check_list` is what `is_whitelisted()` and `is_blocked()` are built
on, so a line that matches more than its author meant is a grant nobody
intended.
"""

import pytest

from connectonion.network.trust import tools


@pytest.fixture
def listfile(tmp_path, monkeypatch):
    """Point the module at a temp .co and write one of its list files."""
    monkeypatch.setattr(tools, "CO_DIR", tmp_path)

    def write(name, *lines):
        (tmp_path / f"{name}.txt").write_text("\n".join(lines) + "\n")
    return write


class TestWildcardIsAnchored:
    """`trusted-*` means "starts with trusted-", not "contains it somewhere"."""

    def test_a_prefix_pattern_does_not_match_in_the_middle(self, listfile):
        listfile("whitelist", "trusted-*")
        assert tools._check_list("whitelist", "trusted-alice")
        assert not tools._check_list("whitelist", "un-trusted-hacker")

    def test_a_prefix_pattern_does_not_match_at_the_end(self, listfile):
        listfile("blocklist", "spam*")
        assert tools._check_list("blocklist", "spam-bot")
        assert not tools._check_list("blocklist", "no-spam-here-either")

    def test_a_suffix_pattern_anchors_to_the_end(self, listfile):
        listfile("whitelist", "*.example.com")
        assert tools._check_list("whitelist", "agent.example.com")
        assert not tools._check_list("whitelist", "example.com.evil.net")

    def test_a_bare_star_still_matches_everything(self, listfile):
        """The one pattern whose meaning is unambiguous, and people rely on it."""
        listfile("whitelist", "*")
        assert tools._check_list("whitelist", "anyone-at-all")


class TestAddressCaseIsIgnored:
    """Addresses are generated lowercase, but a human pastes what they are shown.

    An admin who blocks `0xABCDEF…` and gets no block at all is worse off than
    one who gets an error: the command reported success.
    """

    def test_a_mixed_case_entry_blocks_the_lowercase_address(self, listfile):
        listfile("blocklist", "0xABCDEF0123456789")
        assert tools._check_list("blocklist", "0xabcdef0123456789")

    def test_a_lowercase_entry_blocks_a_mixed_case_query(self, listfile):
        listfile("blocklist", "0xabcdef0123456789")
        assert tools._check_list("blocklist", "0xABCDEF0123456789")

    def test_case_folding_applies_to_wildcards_too(self, listfile):
        listfile("whitelist", "TRUSTED-*")
        assert tools._check_list("whitelist", "trusted-alice")


class TestUnchanged:
    """Behaviour the fix must not disturb."""

    def test_a_missing_file_denies(self, listfile, tmp_path, monkeypatch):
        monkeypatch.setattr(tools, "CO_DIR", tmp_path)
        assert not tools._check_list("whitelist", "anyone")

    def test_comments_and_blank_lines_are_skipped(self, listfile):
        listfile("whitelist", "# a comment", "", "  ", "alice")
        assert tools._check_list("whitelist", "alice")
        assert not tools._check_list("whitelist", "# a comment")

    def test_an_exact_entry_still_matches(self, listfile):
        listfile("whitelist", "alice")
        assert tools._check_list("whitelist", "alice")
        assert not tools._check_list("whitelist", "alice-2")
