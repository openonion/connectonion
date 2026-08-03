"""The person who made the agent can talk to it.

`co deploy` writes the deployer's address into the agent's `.co/admins.txt`,
and says why:

    admins.txt is who may command the agent. Without this nobody can —
    ADMIN_ADD is gated on super-admin, super-admin is the agent's OWN address,
    and that private key exists only on the server. The one account that could
    grant admin is the one nobody can sign as.

`co create` and `co init` never learned it, so an agent run from the machine
that made it treats its own author as a stranger:

    $ co create calltest --template co-ai
    $ python agent.py &
    $ co call 0x900d7723… "co status"
    agent requires onboarding — run input() once to onboard, then call() works

Confirmed both directions on a live agent. With `.co/admins.txt` absent the
CONNECT is refused; with the caller's address in it the same command connects
and runs — the 127 below is the remote shell's own answer, so the trust gate
and the exec path both worked:

    $ co call 0x900d7723… "co status"
    STDERR:
    /bin/bash: co status: command not found
    Exit code: 127

The advice in that error is not something a CLI user can act on either —
`input()` is the Python API and `co call` has no way to submit an invite code —
but that is #614's second half and a separate decision. This is the half with a
precedent to follow: write it the way deploy already does.

Appended rather than written, and only when absent: the file may already name
other admins, and re-running init must not mint a second copy of the same line.
"""

from pathlib import Path

import pytest


def _seed_global_keys() -> str:
    """conftest's autouse fixture already points HOME at a tmp dir."""
    from connectonion import address

    home = Path.home()
    (home / ".co").mkdir(parents=True, exist_ok=True)
    data = address.generate()
    address.save(data, home / ".co")
    (home / ".co" / "keys.env").write_text(
        f"OPENONION_API_KEY=token\nAGENT_ADDRESS={data['address']}\n"
    )
    return data["address"]


def _admins(project: Path) -> list:
    path = project / ".co" / "admins.txt"
    if not path.exists():
        return []
    return [l.strip() for l in path.read_text().splitlines() if l.strip()]


class TestCoCreate:

    def _create(self, tmp_path, monkeypatch, name="mine") -> Path:
        creator = _seed_global_keys()
        monkeypatch.chdir(tmp_path)

        from connectonion.cli.commands.create import handle_create

        handle_create(name=name, ai=False, key=None, template="co-ai",
                      description=None, yes=True, parent_dir=tmp_path)
        self.creator = creator
        return tmp_path / name

    def test_the_creator_is_an_admin(self, tmp_path, monkeypatch):
        project = self._create(tmp_path, monkeypatch)

        assert self.creator in _admins(project), _admins(project)

    def test_the_address_is_the_one_that_signs(self, tmp_path, monkeypatch):
        """Not the one in keys.env — an agent has to trust the key that will
        actually be presented to it."""
        from connectonion import address

        project = self._create(tmp_path, monkeypatch)
        signing = address.load(Path.home() / ".co")["address"]

        assert _admins(project) == [signing]


class TestCoInit:

    def _init(self, tmp_path, monkeypatch) -> Path:
        creator = _seed_global_keys()
        project = tmp_path / "here"
        project.mkdir()
        monkeypatch.chdir(project)

        from connectonion.cli.commands.init import handle_init

        handle_init(ai=False, key=None, template="none", description=None,
                    yes=True, force=True)
        self.creator = creator
        return project

    def test_the_creator_is_an_admin(self, tmp_path, monkeypatch):
        project = self._init(tmp_path, monkeypatch)

        assert self.creator in _admins(project), _admins(project)

    def test_running_it_twice_does_not_duplicate_the_line(self, tmp_path, monkeypatch):
        """A duplicate in the file that says who may command the agent is how
        people stop trusting the file."""
        project = self._init(tmp_path, monkeypatch)

        from connectonion.cli.commands.init import handle_init

        handle_init(ai=False, key=None, template="none", description=None,
                    yes=True, force=True)

        assert _admins(project).count(self.creator) == 1

    def test_an_existing_admin_is_kept(self, tmp_path, monkeypatch):
        """The file may already name someone else."""
        creator = _seed_global_keys()
        project = tmp_path / "shared"
        (project / ".co").mkdir(parents=True)
        someone_else = "0x" + "b" * 64
        (project / ".co" / "admins.txt").write_text(someone_else + "\n")
        monkeypatch.chdir(project)

        from connectonion.cli.commands.init import handle_init

        handle_init(ai=False, key=None, template="none", description=None,
                    yes=True, force=True)

        assert someone_else in _admins(project)
        assert creator in _admins(project)
