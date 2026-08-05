"""`connect(address).input(...)` — the documented one-liner — cannot talk to a
default agent.

`connect` takes `keys=None` and passes it straight through:

    def connect(address, keys=None, relay_url=...):
        keys: Signing keys from address.load() - required for strict trust agents
        ...
        >>> agent = connect("0x3d4017c3...")
        >>> response = agent.input("Book a flight")

The example is the shape a user copies, and the parameter doc says signing is a
`strict` concern. Both are wrong about the default. Measured against a real
hosted agent on `trust: careful` — the default from `co init` — using exactly
that example:

    ConnectionError: Auth error: unauthorized: signed request required

`careful` refuses an unsigned frame just as `strict` does; what `careful` adds is
a way *in* for a signed stranger (onboarding), not permission to stay anonymous.

The CLI does not have this problem, because it loads the keys itself:

    # cli/commands/call_commands.py
    def _load_keys():
        co_dir = Path(".co")
        if not (co_dir.exists() and (co_dir / "keys" / "agent.key").exists()):
            co_dir = Path.home() / ".co"
        return address.load(co_dir)

    kwargs = {"keys": _load_keys()}

So `co call` reaches the agent and `connect()` does not — the same two-places
shape as #669 and #671, with only one of the two places doing the work.

The host side already settled what the answer is. `resolve_agent_identity` uses
the project's key when it has one and the machine's `~/.co` identity when it does
not, and #661 gave the project half of that a proper walk-up. A client is the
same question from the other end, so it gets the same answer here, and
`_load_keys` becomes one call into it rather than a second copy with a bare
`Path(".co")` that reads the wrong project from a subdirectory.

Passing `keys=` explicitly still wins, and an unsigned client is still possible
by asking for one — `connect(addr, keys=False)` — because `trust: open` accepts
anonymous callers and that is a thing people do in development.
"""

from pathlib import Path

import pytest


@pytest.fixture
def a_project_with_an_identity(tmp_path, monkeypatch):
    from connectonion import address

    co = tmp_path / "project" / ".co"
    co.mkdir(parents=True)
    keys = address.generate()
    address.save(keys, co)
    (tmp_path / "project" / "sub").mkdir()
    monkeypatch.chdir(tmp_path / "project")
    return tmp_path / "project", keys


class TestTheDocumentedOneLiner:

    def test_it_signs(self, a_project_with_an_identity):
        from connectonion.network import connect

        _, keys = a_project_with_an_identity

        assert connect("0x" + "a" * 64)._keys["address"] == keys["address"]

    def test_from_a_subdirectory_it_is_still_this_project(self, a_project_with_an_identity, monkeypatch):
        """`co call`'s copy used a bare `Path(".co")`, so a subdirectory silently
        fell through to the machine identity instead."""
        project, keys = a_project_with_an_identity
        monkeypatch.chdir(project / "sub")

        assert connect_keys("0x" + "a" * 64)["address"] == keys["address"]


def connect_keys(address_str):
    from connectonion.network import connect

    return connect(address_str)._keys


class TestTheClientIsTheSameAgentAsTheHost:
    """A client signs as whatever this project *is* — the same answer
    `resolve_agent_identity` gives the host. Signing as one identity while your
    own agent serves under another is #659 from the other side."""

    def test_a_project_without_keys_derives_its_own(self, tmp_path, monkeypatch):
        """It used to sign as the machine identity, which is what made every
        project on a laptop one agent (#642). Since #689 it derives."""
        from connectonion import address
        from connectonion.network import connect
        from connectonion.project import project_identity

        home = tmp_path / "home"
        (home / ".co").mkdir(parents=True)
        machine = address.generate()
        address.save(machine, home / ".co")
        (home / ".co" / "keys" / "recovery.txt").write_text(
            machine["seed_phrase"], encoding="utf-8")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        project = tmp_path / "keyless"
        (project / ".co").mkdir(parents=True)
        monkeypatch.chdir(project)

        signing_as = connect("0x" + "a" * 64)._keys["address"]

        assert signing_as != machine["address"]
        assert signing_as == project_identity(project / ".co")["address"]

    def test_no_identity_anywhere_is_not_an_error(self, tmp_path, monkeypatch):
        """A caller with no key at all still constructs; the agent decides."""
        from connectonion.network import connect

        home = tmp_path / "empty-home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        monkeypatch.chdir(tmp_path)

        assert connect("0x" + "a" * 64)._keys is None


class TestWhatMustNotChange:

    def test_explicit_keys_still_win(self, a_project_with_an_identity):
        from connectonion import address
        from connectonion.network import connect

        chosen = address.generate()

        assert connect("0x" + "a" * 64, keys=chosen)._keys["address"] == chosen["address"]

    def test_an_unsigned_client_can_still_be_asked_for(self, a_project_with_an_identity):
        """`trust: open` accepts anonymous callers, and that is a real workflow."""
        from connectonion.network import connect

        assert connect("0x" + "a" * 64, keys=False)._keys is None


class TestTheCliUsesTheSameOne:
    """One resolver, not two — `_load_keys` was the copy that worked."""

    def test_it_finds_the_projects_identity(self, a_project_with_an_identity):
        from connectonion.cli.commands.call_commands import _load_keys

        _, keys = a_project_with_an_identity

        assert _load_keys()["address"] == keys["address"]

    def test_from_a_subdirectory_too(self, a_project_with_an_identity, monkeypatch):
        from connectonion.cli.commands.call_commands import _load_keys

        project, keys = a_project_with_an_identity
        monkeypatch.chdir(project / "sub")

        assert _load_keys()["address"] == keys["address"]


class TestTheDocstringSaysWhatIsTrue:
    """The claim that sent a user down this path in the first place."""

    def test_it_does_not_say_signing_is_only_for_strict(self):
        import inspect

        from connectonion.network import connect

        text = (inspect.getdoc(connect) or "").lower()

        assert "required for strict trust agents" not in text
