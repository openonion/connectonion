"""The trust lists belong to the agent, not to the directory it was started from.

`list_file` resolved against the bare cwd:

    return Path.cwd() / ".co" / f"{list_name}.txt"

so running the agent one directory down looks for `subdir/.co/contacts.txt`,
which is not there. Measured on a project with a real contact in its list:

    from the project root        level of the listed address -> contact
    from a subdirectory of it    level of the same address   -> stranger

The directions are not symmetric. A contact or a whitelisted address demoted to
stranger is refused, which is annoying and safe. **A blocked address demoted to
stranger is no longer blocked** — `is_blocked()` reads the same list, so someone
you blocked gets back in, silently, because of where the process was started.

The project has fixed this exact shape once already, for the Home page, and the
comment left there says what the rule is:

    The directory that owns `.co/` — the project, not wherever you ran from.
    Walks up from `start`. Everything else the agent is made of is found this
    way (`.co/skills`, `.co/host.yaml`), and the Home page had no such notion:
    it resolved against the bare cwd …

The trust lists are the remaining outlier. `_admins_file` had already been given
a `co_dir` parameter for a related reason; these three never were.

Walking up also closes the other half of the same hazard, which that comment
names: a tool or a plugin calling `os.chdir` mid-run. Nothing in the codebase
does today, but a user's tool can, and every trust check after it would read
from wherever it landed.
"""

from pathlib import Path

import pytest


ADDRESS = "0x" + "b" * 64


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project with a contact, a block, and a subdirectory to run from."""
    co = tmp_path / "project" / ".co"
    co.mkdir(parents=True)
    (co / "contacts.txt").write_text(ADDRESS + "\n")
    (co / "blocklist.txt").write_text(ADDRESS + "\n")
    (tmp_path / "project" / "subdir" / "deeper").mkdir(parents=True)

    # the legacy-list notice is one-shot per process and would swallow later ones
    from connectonion.network.trust import tools
    monkeypatch.setattr(tools, "_mentioned", set(), raising=False)
    return tmp_path / "project"


def _level_from(directory, monkeypatch, address=ADDRESS):
    from connectonion.network.trust.tools import get_level

    monkeypatch.chdir(directory)
    return get_level(address)


class TestFromASubdirectory:

    def test_a_contact_is_still_a_contact(self, project, monkeypatch):
        (project / ".co" / "blocklist.txt").unlink()

        assert _level_from(project / "subdir", monkeypatch) == "contact"

    def test_two_levels_down_as_well(self, project, monkeypatch):
        (project / ".co" / "blocklist.txt").unlink()

        assert _level_from(project / "subdir" / "deeper", monkeypatch) == "contact"

    def test_a_blocked_address_is_still_blocked(self, project, monkeypatch):
        """The direction that fails open: a lost blocklist lets someone back in."""
        assert _level_from(project / "subdir", monkeypatch) == "blocked"

    def test_is_blocked_agrees(self, project, monkeypatch):
        from connectonion.network.trust.tools import is_blocked

        monkeypatch.chdir(project / "subdir")

        assert is_blocked(ADDRESS)


class TestFromTheProjectRoot:
    """Unchanged — this is what already worked."""

    def test_a_contact_reads_as_a_contact(self, project, monkeypatch):
        (project / ".co" / "blocklist.txt").unlink()

        assert _level_from(project, monkeypatch) == "contact"

    def test_a_blocked_address_reads_as_blocked(self, project, monkeypatch):
        assert _level_from(project, monkeypatch) == "blocked"


class TestOutsideAnyProject:
    """An agent hosted where there is no `.co/` above it still behaves — the list
    simply lives where it was started, which is what the Home page does too."""

    def test_an_unknown_address_is_a_stranger(self, tmp_path, monkeypatch):
        from connectonion.network.trust.tools import get_level

        monkeypatch.chdir(tmp_path)

        assert get_level(ADDRESS) == "stranger"

    def test_a_list_beside_it_is_read(self, tmp_path, monkeypatch):
        from connectonion.network.trust.tools import get_level

        (tmp_path / ".co").mkdir()
        (tmp_path / ".co" / "contacts.txt").write_text(ADDRESS + "\n")
        monkeypatch.chdir(tmp_path)

        assert get_level(ADDRESS) == "contact"


class TestTheAdminsFileToo:
    """`_admins_file` takes a co_dir, but its default is the same bare cwd."""

    def test_admins_are_found_from_a_subdirectory(self, project, monkeypatch):
        from connectonion.network.trust.tools import _admins_file

        monkeypatch.chdir(project / "subdir")

        assert _admins_file() == project / ".co" / "admins.txt"

    def test_an_explicit_co_dir_still_wins(self, project, tmp_path):
        from connectonion.network.trust.tools import _admins_file

        elsewhere = tmp_path / "elsewhere"

        assert _admins_file(elsewhere) == elsewhere / "admins.txt"
