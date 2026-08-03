"""What a trust list that cannot be read should mean.

`_check_list` wrapped its read in `except Exception: return False`. For the
whitelist that is the safe direction — an unreadable grant grants nothing. For
the **blocklist it is fail-open**: `is_blocked()` answers False, and everyone on
the list is admitted.

The way to get there is ordinary. An operator opens `blocklist.txt` in a Windows
editor and saves it as GBK; the next read raises UnicodeDecodeError. Or the file
ends up owned by root after a deploy and the agent cannot read it. Either way
the deny list silently stops denying, and nothing anywhere says so.

Same swallow, safe in one direction and dangerous in the other, which is why it
survived: the direction that matters is the one nobody tests.

An unreadable file is not an empty file. It is a question this agent cannot
answer, and the honest response is to say so rather than to guess "no".
"""

import importlib

import pytest

tools = importlib.import_module('connectonion.network.trust.tools')

BLOCKED = '0x' + 'b' * 64


@pytest.fixture
def agent_dir(tmp_path, monkeypatch):
    (tmp_path / '.co').mkdir()
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.chdir(tmp_path)
    return tmp_path / '.co'


class TestABrokenBlocklistDoesNotUnblock:

    def test_undecodable_bytes_do_not_read_as_not_blocked(self, agent_dir):
        # What a Windows editor saving as GBK leaves behind.
        (agent_dir / 'blocklist.txt').write_bytes(
            BLOCKED.encode() + b'\n\xd6\xd0\xce\xc4\n')

        with pytest.raises(Exception) as exc:
            tools.is_blocked(BLOCKED)

        assert 'blocklist' in str(exc.value), (
            "the failure must name the file the operator has to fix"
        )

    def test_an_unreadable_file_does_not_read_as_not_blocked(self, agent_dir):
        path = agent_dir / 'blocklist.txt'
        path.write_text(BLOCKED + '\n')
        path.chmod(0o000)
        try:
            with pytest.raises(Exception):
                tools.is_blocked(BLOCKED)
        finally:
            path.chmod(0o644)


class TestTheOtherListsSayItToo:
    """A whitelist that cannot be read already failed closed. It failed closed
    *silently*, which is how an operator spends an afternoon on 'why is my
    colleague being asked to onboard again'."""

    def test_a_broken_whitelist_is_loud(self, agent_dir):
        (agent_dir / 'whitelist.txt').write_bytes(b'\xd6\xd0\xce\xc4\n')

        with pytest.raises(Exception) as exc:
            tools.is_whitelisted('0x' + 'a' * 64)

        assert 'whitelist' in str(exc.value)


class TestNothingElseChanges:

    def test_a_missing_file_is_still_simply_absent(self, agent_dir):
        """Absent is an answer. Unreadable is not."""
        assert tools.is_blocked(BLOCKED) is False
        assert tools.is_whitelisted('0x' + 'a' * 64) is False

    def test_a_readable_list_still_works(self, agent_dir):
        (agent_dir / 'blocklist.txt').write_text(BLOCKED + '\n')

        assert tools.is_blocked(BLOCKED) is True
        assert tools.is_blocked('0x' + 'c' * 64) is False


class TestAnUnreadableAdminsFileDoesNotDemoteTheOwner:
    """`load_admins` swallowed the same way, and the cost went up in #579.

    Since the approval dialog belongs to admins only, an admins.txt that cannot
    be read no longer just loses a permission — it makes every approval the
    owner attempts come back "you are stranger". They would be reading a
    refusal that names the wrong reason, about a file nothing mentions.
    """

    def test_undecodable_admins_txt_is_loud(self, agent_dir):
        (agent_dir / 'admins.txt').write_bytes(b'\xd6\xd0\xce\xc4\n')

        with pytest.raises(Exception) as exc:
            tools.load_admins(agent_dir)

        assert 'admins' in str(exc.value)

    def test_a_missing_admins_txt_is_still_fine(self, agent_dir):
        """A fresh project has no admins.txt and must still start."""
        assert isinstance(tools.load_admins(agent_dir), set)

    def test_a_readable_admins_txt_still_works(self, agent_dir):
        owner = '0x' + '1' * 64
        (agent_dir / 'admins.txt').write_text(owner + '\n')

        assert owner in tools.load_admins(agent_dir)
