"""`co auth` one directory down authenticates as the machine and writes the
token to `~/.env`.

Two bare-cwd lookups. `handle_auth` picks the identity:

    co_dir = Path(".co")                                    # auth_commands.py
    if co_dir.exists() and (co_dir / "keys" / "agent.key").exists():
        ...                                                  # not taken from a subdirectory
    else:
        co_dir = Path.home() / ".co"

and `authenticate` then re-guesses where the token goes, ignoring the `co_dir`
it was handed:

    local_env_path = Path(".co") if Path(".co").exists() else co_dir
    upsert_env(local_env_path.parent / ".env", {...})

From a subdirectory `Path(".co")` does not exist, so `local_env_path` is `~/.co`
and the write lands on **`~/.env`** — not the project's `.env`, and not
`~/.co/keys.env`, which is the documented secret location and the one
`co status` and `co doctor` report on.

The comment above that line says "Also save to current directory's `.env`",
which is the intent. A file at the home root is not that.

It has happened on this machine: `~/.env`, mode 0600, holding exactly
`OPENONION_API_KEY`, `AGENT_EMAIL` and `AGENT_ADDRESS`.

This is the last live member of #665. The other five were fixed in #673, #679,
#680 and #681, or turned out not to reproduce.

The network is not exercised here — `authenticate` is stubbed at the seam where
it is handed a directory, and the POST is patched out. What is under test is
which directory each half chooses.
"""

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def project(tmp_path, monkeypatch):
    from connectonion import address

    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    address.save(address.generate(), home / ".co")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    project = tmp_path / "project"
    (project / ".co").mkdir(parents=True)
    own = address.generate()
    address.save(own, project / ".co")
    (project / "sub").mkdir()
    return project, home, own


class TestWhichIdentityItAuthenticatesAs:

    def test_from_a_subdirectory_it_is_the_projects(self, project, monkeypatch):
        from connectonion.cli.commands import auth_commands

        proj, _, own = project
        monkeypatch.chdir(proj / "sub")
        seen = {}

        with patch.object(auth_commands, "authenticate",
                          side_effect=lambda co_dir, **kw: seen.update(co_dir=co_dir) or True):
            auth_commands.handle_auth()

        assert seen.get("co_dir") == proj / ".co"

    def test_from_the_project_root_it_is_still_the_projects(self, project, monkeypatch):
        from connectonion.cli.commands import auth_commands

        proj, _, _ = project
        monkeypatch.chdir(proj)
        seen = {}

        with patch.object(auth_commands, "authenticate",
                          side_effect=lambda co_dir, **kw: seen.update(co_dir=co_dir) or True):
            auth_commands.handle_auth()

        assert seen.get("co_dir") == proj / ".co"

    def test_a_keyless_project_still_falls_back_to_the_machine(self, tmp_path, monkeypatch):
        from connectonion import address
        from connectonion.cli.commands import auth_commands

        home = tmp_path / "home2"
        (home / ".co").mkdir(parents=True)
        address.save(address.generate(), home / ".co")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        keyless = tmp_path / "keyless"
        (keyless / ".co").mkdir(parents=True)
        (keyless / "sub").mkdir()
        monkeypatch.chdir(keyless / "sub")
        seen = {}

        with patch.object(auth_commands, "authenticate",
                          side_effect=lambda co_dir, **kw: seen.update(co_dir=co_dir) or True):
            auth_commands.handle_auth()

        assert seen.get("co_dir") == home / ".co"


class TestWhereTheTokenIsWritten:
    """Through `co auth` itself, not `authenticate` handed the right directory.

    Handed the project's `.co`, `authenticate` already writes the project's
    `.env` — the local branch uses the `co_dir` it was given. The token reaches
    `~/.env` only because `handle_auth` hands it the *global* directory from a
    subdirectory, so the whole command is what has to be exercised.
    """

    def _run_auth(self):
        from connectonion.cli.commands import auth_commands

        class _Resp:
            status_code = 200
            def json(self):
                return {"token": "tok", "email": "a@mail.openonion.ai",
                        "email_active": False, "balance": 0}

        with patch.object(auth_commands.requests, "post", return_value=_Resp()):
            auth_commands.handle_auth()

    def test_from_a_subdirectory_it_lands_in_the_project(self, project, monkeypatch):
        proj, _, _ = project
        monkeypatch.chdir(proj / "sub")

        self._run_auth()

        assert (proj / ".env").exists(), "the project's .env was not written"

    def test_it_does_not_write_to_the_home_root(self, project, monkeypatch):
        """`~/.env` is not the secret location; `~/.co/keys.env` is."""
        proj, home, _ = project
        monkeypatch.chdir(proj / "sub")

        self._run_auth()

        assert not (home / ".env").exists(), "a credential was written to ~/.env"

    def test_the_message_names_the_file_it_wrote(self, project, monkeypatch, capsys):
        """The success line printed Path.cwd()/.env while writing somewhere else."""
        proj, _, _ = project
        monkeypatch.chdir(proj / "sub")

        self._run_auth()
        printed = capsys.readouterr().out

        assert str(proj / "sub" / ".env") not in printed, \
            "it named a file in the subdirectory that it did not write"
