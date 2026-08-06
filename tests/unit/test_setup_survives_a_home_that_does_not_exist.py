"""Setting up `~/.co` on a HOME that does not exist yet gives a raw traceback.

Reproduced while probing something else — `HOME` pointed at a directory I had not
created:

    global_dir.mkdir(exist_ok=True)
    FileNotFoundError: [Errno 2] No such file or directory:
      '/…/failinit/fakehome/.co'

`mkdir(exist_ok=True)` creates one level. `~/.co` is the first thing this project
puts under HOME, so if HOME itself is absent there is no parent to create it in,
and the CLI unwinds through rich's traceback renderer instead of saying anything.
This project is deliberate about not doing that elsewhere — `send()` catches every
setup RuntimeError precisely so typer's pretty exceptions never print frame locals
— and a first-run path is the worst place for it, because the reader has nothing
else to go on.

An absent HOME is not exotic: containers and sandboxes hand one over that has not
been created, and this repo ships a Dockerfile.

`parents=True` is the whole fix, and it cannot do less than the old call did.

Scope, deliberately: the two places that create `~/.co` itself. The other bare
`mkdir(exist_ok=True)` calls either sit under the cwd (a project's `.co`, whose
parent is where you are standing) or under `~/.co` after auth has already made it,
so they are ordering-guarded rather than broken.
"""

from pathlib import Path

import pytest


class TestTheGlobalDirectoryCanBeCreatedFromNothing:

    @pytest.fixture
    def absent_home(self, monkeypatch, tmp_path):
        """A HOME whose directory has not been created."""
        home = tmp_path / "never-created"
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        assert not home.exists()
        return home

    def test_setup_does_not_raise_filenotfound(self, absent_home, monkeypatch):
        from connectonion.cli.commands import project_cmd_lib as lib

        # Stop after the directories are made: what is under test is the mkdir,
        # not key generation or the network call that follows it.
        monkeypatch.setattr(lib.address, "generate",
                            lambda: (_ for _ in ()).throw(_Stop()))

        with pytest.raises(_Stop):
            lib.ensure_global_config()  # the real name, not one I assumed

        assert (absent_home / ".co").is_dir()
        assert (absent_home / ".co" / "keys").is_dir()
        assert (absent_home / ".co" / "logs").is_dir()

    def test_reset_does_not_raise_filenotfound(self, absent_home, monkeypatch):
        """The same three lines, in the same shape, in reset_commands."""
        from connectonion.cli.commands import reset_commands

        source = Path(reset_commands.__file__).read_text(encoding="utf-8")
        creating = [line.strip() for line in source.splitlines()
                    if ".mkdir(" in line and ("global_dir" in line or "keys_dir" in line)]

        assert creating, "the reset path no longer creates these; revisit this test"
        for line in creating:
            assert "parents=True" in line, line


class _Stop(Exception):
    """Sentinel: the directories are made, stop before doing any real work."""


class TestTheCallCannotDoLessThanBefore:
    """`parents=True` only adds; exist_ok must stay or a second run raises."""

    def test_it_is_idempotent(self, tmp_path):
        target = tmp_path / "a" / "b" / ".co"

        target.mkdir(parents=True, exist_ok=True)
        target.mkdir(parents=True, exist_ok=True)  # must not raise

        assert target.is_dir()
