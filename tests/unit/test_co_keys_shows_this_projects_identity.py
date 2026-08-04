"""`co keys` shows a different identity depending on where you stand.

`_find_co_dir` looks in the bare cwd, then falls back to the machine's:

    local = Path(".co")
    if local.exists() and (local / "keys" / "agent.key").exists():
        return local
    global_dir = Path.home() / ".co"
    ...

so one directory down the project's own key is invisible and the global one
answers instead. Measured on a project with its own keypair:

    from the project root   Address 0xd72fbbd5…   Source .co (project)
    from a subdirectory     Address 0x10e68f6d…   Source ~/.co (global)

Two different addresses for the same agent, and the panel states the wrong one
as confidently as the right one.

This is the shape I got wrong when filing #665. I wrote there that these
commands "fail in the visible direction — the command says it found nothing,
rather than silently acting on the wrong thing". That is true of `co status` and
`co doctor`; it is not true here, because the `~/.co` fallback always finds
*something*. An operator reads an address off this panel and hands it out, and
from a subdirectory it is the machine's rather than the agent's.

The fallback itself is right and stays: a project with no key of its own is a
real configuration — `co init` produces one — and `resolve_agent_identity` on
the host side does exactly this, own key then `~/.co`. What changes is that
"own key" is found by walking up, the way everything else since #660 is.
"""

from pathlib import Path

import pytest


@pytest.fixture
def project_with_its_own_key(tmp_path, monkeypatch):
    from connectonion import address

    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    machine = address.generate()
    address.save(machine, home / ".co")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    project = tmp_path / "project"
    (project / ".co").mkdir(parents=True)
    own = address.generate()
    address.save(own, project / ".co")
    (project / "sub" / "deeper").mkdir(parents=True)
    return project, own, machine


class TestFromASubdirectory:

    @pytest.mark.parametrize("depth", ["sub", "sub/deeper"])
    def test_it_finds_the_projects_co(self, project_with_its_own_key, monkeypatch, depth):
        from connectonion.cli.commands.keys_commands import _find_co_dir

        project, _, _ = project_with_its_own_key
        monkeypatch.chdir(project / depth)

        assert _find_co_dir() == project / ".co"

    def test_the_address_is_the_projects(self, project_with_its_own_key, monkeypatch):
        from connectonion import address
        from connectonion.cli.commands.keys_commands import _find_co_dir

        project, own, machine = project_with_its_own_key
        monkeypatch.chdir(project / "sub")
        loaded = address.load(_find_co_dir())

        assert loaded["address"] == own["address"]
        assert loaded["address"] != machine["address"]


class TestFromTheProjectRoot:
    """Unchanged."""

    def test_it_still_finds_the_project(self, project_with_its_own_key, monkeypatch):
        from connectonion.cli.commands.keys_commands import _find_co_dir

        project, _, _ = project_with_its_own_key
        monkeypatch.chdir(project)

        assert _find_co_dir() == project / ".co"


class TestTheGlobalFallbackStays:
    """A project with no key of its own is what `co init` usually produces."""

    def test_a_keyless_project_uses_the_machine_identity(self, tmp_path, monkeypatch):
        from connectonion import address
        from connectonion.cli.commands.keys_commands import _find_co_dir

        home = tmp_path / "home2"
        (home / ".co").mkdir(parents=True)
        address.save(address.generate(), home / ".co")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        keyless = tmp_path / "keyless"
        (keyless / ".co").mkdir(parents=True)
        (keyless / "sub").mkdir()
        monkeypatch.chdir(keyless / "sub")

        assert _find_co_dir() == home / ".co"

    def test_no_identity_anywhere_is_still_None(self, tmp_path, monkeypatch):
        from connectonion.cli.commands.keys_commands import _find_co_dir

        home = tmp_path / "empty"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        monkeypatch.chdir(tmp_path)

        assert _find_co_dir() is None
