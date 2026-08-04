"""`co status` and `host()` must name the same agent.

A project with no key of its own gets two different answers.

`co status` falls back to the machine's identity:

    co_dir = Path(".co")
    if not (co_dir.exists() and (co_dir / "keys" / "agent.key").exists()):
        co_dir = Path.home() / ".co"

`host()` does not fall back. It looks in `cwd/.co`, finds nothing, and mints:

    if co_dir is None:
        co_dir = Path.cwd() / '.co'
    addr_data = address.load(co_dir)
    if addr_data is None:
        addr_data = address.generate()
        address.save(addr_data, co_dir)

Measured in a project created by 1.5.x — the `co init` that pointed at the
global `~/.co` and wrote no local key:

    co status says:   0x10e68f6dff39ab1c50cc48ea…
    host serves as:   0x3910103910d99954443e42a3…

So the operator reads one address, hands it out, and nothing reaches the agent —
it is answering as somebody else. The project's identity is also changed on the
way past, silently: an agent whitelisted or announced under the address that was
configured is now a different agent.

Projects made by today's `co create` and `co init` write their own key, so this
is invisible there and the whole thing only bites the projects that predate that
— the ones most likely to be running unattended somewhere.

Generating stays, for a machine with no identity at all: an agent has to have an
address. What goes is inventing one while a configured identity sits unused.
"""

from pathlib import Path

import pytest

from connectonion import address
from connectonion.network.host.server import resolve_agent_identity


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A home with an identity, and an empty project beside it."""
    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    machine_keys = address.generate()
    address.save(machine_keys, home / ".co")

    project = tmp_path / "project"
    (project / ".co").mkdir(parents=True)

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return machine_keys, project


class TestAProjectWithNoKeyOfItsOwn:

    def test_it_uses_the_machine_identity(self, machine):
        machine_keys, project = machine

        resolved = resolve_agent_identity(project / ".co")

        assert resolved["address"] == machine_keys["address"]

    def test_it_does_not_invent_one(self, machine):
        machine_keys, project = machine

        resolved = resolve_agent_identity(project / ".co")

        assert resolved["address"] != address.generate()["address"]  # sanity
        assert resolved["address"] == machine_keys["address"]

    def test_it_writes_no_key_into_the_project(self, machine):
        _, project = machine

        resolve_agent_identity(project / ".co")

        assert not (project / ".co" / "keys" / "agent.key").exists()

    def test_it_agrees_with_what_co_status_would_report(self, machine):
        """The same resolution `co status` does, spelled out here so the two
        cannot drift apart again."""
        machine_keys, project = machine

        co_dir = project / ".co"
        status_dir = co_dir if (co_dir / "keys" / "agent.key").exists() else Path.home() / ".co"
        status_says = address.load(status_dir)["address"]

        assert resolve_agent_identity(co_dir)["address"] == status_says


class TestAProjectWithItsOwnKey:
    """Everything `co create` makes today. Must be untouched."""

    def test_its_own_key_wins(self, machine):
        machine_keys, project = machine
        own = address.generate()
        address.save(own, project / ".co")

        assert resolve_agent_identity(project / ".co")["address"] == own["address"]

    def test_the_machine_identity_is_not_consulted(self, machine):
        machine_keys, project = machine
        own = address.generate()
        address.save(own, project / ".co")

        assert resolve_agent_identity(project / ".co")["address"] != machine_keys["address"]


class TestWithNoIdentityAnywhere:
    """An agent has to have an address; this is the case generating is for."""

    def test_one_is_generated(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / ".co").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        project = tmp_path / "project"
        (project / ".co").mkdir(parents=True)

        resolved = resolve_agent_identity(project / ".co")

        assert resolved and resolved["address"].startswith("0x")

    def test_it_is_saved_in_the_project(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / ".co").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        project = tmp_path / "project"
        (project / ".co").mkdir(parents=True)

        resolved = resolve_agent_identity(project / ".co")

        assert address.load(project / ".co")["address"] == resolved["address"]


class TestHostActuallyUsesIt:
    """A helper nothing calls is the bug, not the fix."""

    def test_the_served_address_comes_from_the_resolver(self, machine, monkeypatch):
        from connectonion import Agent
        from connectonion.network.host import server as server_module

        machine_keys, project = machine
        monkeypatch.chdir(project)

        seen = {}
        monkeypatch.setattr(server_module.uvicorn, "run", lambda app, **kw: None)
        monkeypatch.setattr(server_module, "_print_host_banner",
                            lambda **kw: seen.update(kw))

        server_module.host(Agent("t", tools=[], model="co/gemini-2.5-flash"),
                           relay_url=None)

        assert seen.get("address") == machine_keys["address"], (
            "host() served an address the operator was never told"
        )
