"""A container deploy keeps the admins the project names.

`_build_tarball()` packs the project — including `.co/admins.txt` — and then
calls `_add_deployer_as_admin()`, which appends a second entry of the same name
holding only the deployer. Two members, one path; extraction takes the last.

Measured on a real tarball, with a colleague added to the project's file:

    project .co/admins.txt      0x10e6…  (the deployer)
                                0xbbbb…  (a colleague)

    entries named admins.txt    2
    winning content             ['0x10e6…']

So anyone the operator added is dropped on deploy, silently, and the loss shows
up later as a person who cannot command an agent they were given access to.

The deployer must always end up in the file — that is what
`_add_deployer_as_admin` is for, and #614 is what happens without it. But
"always present" and "the only one" are different guarantees, and the second
one was never intended: the docstring says it seeds the deployer, not that it
replaces the list.

The two are merged, and the tarball carries one entry for the path.
"""

import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from connectonion.cli.commands.deploy_commands import _build_tarball


COLLEAGUE = "0x" + "b" * 64


@pytest.fixture
def project(tmp_path):
    """A project with a .co/, as `co create` leaves one."""
    from connectonion import address

    home = Path.home()
    (home / ".co").mkdir(parents=True, exist_ok=True)
    data = address.generate()
    address.save(data, home / ".co")

    p = tmp_path / "shipme"
    (p / ".co").mkdir(parents=True)
    (p / "agent.py").write_text("from connectonion import host\n")
    (p / ".co" / "host.yaml").write_text("name: shipme\nentrypoint: agent.py\n")
    return SimpleNamespace(dir=p, deployer=data["address"])


def _admins_in(tarball: Path) -> list:
    with tarfile.open(tarball) as tar:
        members = [m for m in tar.getmembers() if m.name == ".co/admins.txt"]
        assert members, "no admins.txt in the tarball"
        # What extraction leaves behind.
        text = tar.extractfile(members[-1]).read().decode()
    return [l.strip() for l in text.splitlines() if l.strip()]


def _entry_count(tarball: Path) -> int:
    with tarfile.open(tarball) as tar:
        return len([m for m in tar.getmembers() if m.name == ".co/admins.txt"])


class TestAnAdminTheProjectNames:

    def test_survives_the_deploy(self, project):
        (project.dir / ".co" / "admins.txt").write_text(
            f"{project.deployer}\n{COLLEAGUE}\n")

        assert COLLEAGUE in _admins_in(_build_tarball(project.dir, []))

    def test_survives_even_when_the_deployer_is_not_listed(self, project):
        """The operator may have written only their colleague's address."""
        (project.dir / ".co" / "admins.txt").write_text(COLLEAGUE + "\n")

        assert COLLEAGUE in _admins_in(_build_tarball(project.dir, []))


class TestTheDeployerIsStillAlwaysThere:
    """#614: without this, nobody can command the agent."""

    def test_added_when_the_project_has_no_file(self, project):
        assert _admins_in(_build_tarball(project.dir, [])) == [project.deployer]

    def test_added_when_the_project_names_only_someone_else(self, project):
        (project.dir / ".co" / "admins.txt").write_text(COLLEAGUE + "\n")

        assert project.deployer in _admins_in(_build_tarball(project.dir, []))

    def test_not_listed_twice(self, project):
        (project.dir / ".co" / "admins.txt").write_text(project.deployer + "\n")

        admins = _admins_in(_build_tarball(project.dir, []))
        assert admins.count(project.deployer) == 1, admins


class TestTheArchiveIsTidy:

    def test_one_entry_for_the_path(self, project):
        """Two members with one name is a coin toss decided by write order."""
        (project.dir / ".co" / "admins.txt").write_text(
            f"{project.deployer}\n{COLLEAGUE}\n")

        assert _entry_count(_build_tarball(project.dir, [])) == 1
