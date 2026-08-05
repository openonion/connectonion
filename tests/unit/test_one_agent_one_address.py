"""Two agents answer to one address and nobody is told.

#642, measured on this laptop: `0x10e68f6dff39ab…` was announced by two
different agents at once —

    this laptop, localhost:8000   name `oo`          bash, write, edit, … (24 tools)
    the deployed box              name `naturewill`  the contract-ledger tools

— because both loaded the same keypair. Every 1.5.x project's `co init` wrote
`AGENT_CONFIG_PATH=~/.co`, and a project with no key of its own falls back to
the global one on purpose (that fallback fixed a worse bug: the host used to
mint a third address and serve under it while `co status` reported the
configured one).

After #643 a client resolves an endpoint directly and picks by network
proximity, so a call meant for the deployed agent lands on the local coding
agent instead — one holding `bash` and `write` on the caller's machine. `/info`
verification cannot catch it: the address genuinely matches. That is the point.

The rule is one agent, one address. This is the part that can be proven without
asking anything of the network: the identity directory records which project
and name is serving under it, and a second, different agent starting on the
same keypair is told it is a collision rather than silently joining it.

What it deliberately does not do is refuse to start. The agent whose address
this is may be the one restarting, and an operator who cannot start their agent
because of a stale claim is worse off than one who is told the truth. `co
deploy` is where refusing belongs — a deploy is the moment a second permanent
copy is created.
"""

import json
from pathlib import Path

import pytest

from connectonion import address
from connectonion.network.host.server import claim_identity, resolve_agent_identity


@pytest.fixture
def shared(tmp_path):
    """Two projects that really do share one keypair.

    They used to share it by *both having none* and inheriting the global
    ~/.co. Since #689 that no longer collides — a project with no key of its
    own derives `agent://<name>`, so two of them are two agents, which is the
    whole point of that change.

    The collision this file is about still exists: it needs the same key file
    in both places, which is what AGENT_CONFIG_PATH pointing two projects at
    one directory produces, and what copying a `.co/keys/` produces. So the
    fixture plants the same key in both rather than relying on inheritance.
    """
    home_co = tmp_path / "home" / ".co"
    home_co.mkdir(parents=True)
    identity = address.generate()
    address.save(identity, home_co)

    first = tmp_path / "oo" / ".co"
    second = tmp_path / "naturewill" / ".co"
    for co in (first, second):
        co.mkdir(parents=True)
        address.save(identity, co)
    return home_co, first, second


class TestTheSecondAgentIsTold:

    def test_a_different_name_on_the_same_key_is_a_collision(self, shared, monkeypatch):
        home_co, first, second = shared
        monkeypatch.setattr(Path, "home", lambda: home_co.parent)

        assert claim_identity(first, resolve_agent_identity(first), "oo") is None

        warning = claim_identity(second, resolve_agent_identity(second), "naturewill")

        assert warning, "the second agent joined the first one's address silently"
        assert "oo" in warning, warning

    def test_the_warning_names_the_other_project(self, shared, monkeypatch):
        home_co, first, second = shared
        monkeypatch.setattr(Path, "home", lambda: home_co.parent)

        claim_identity(first, resolve_agent_identity(first), "oo")
        warning = claim_identity(second, resolve_agent_identity(second), "naturewill")

        assert str(first.parent) in warning, warning

    def test_the_same_agent_restarting_is_not_a_collision(self, shared, monkeypatch):
        """The common case. An operator who cannot restart is worse off."""
        home_co, first, _ = shared
        monkeypatch.setattr(Path, "home", lambda: home_co.parent)

        claim_identity(first, resolve_agent_identity(first), "oo")

        assert claim_identity(first, resolve_agent_identity(first), "oo") is None

    def test_a_rename_in_place_is_not_a_collision(self, shared, monkeypatch):
        """One project, one key — renaming the agent is allowed, and the claim
        follows it rather than warning forever."""
        home_co, first, _ = shared
        monkeypatch.setattr(Path, "home", lambda: home_co.parent)

        claim_identity(first, resolve_agent_identity(first), "oo")
        assert claim_identity(first, resolve_agent_identity(first), "oo-renamed") is None
        assert claim_identity(first, resolve_agent_identity(first), "oo-renamed") is None


class TestAProjectWithItsOwnKey:
    """What `co create` produces now, and what the fix for this is: no sharing,
    so nothing to warn about."""

    def test_two_projects_with_their_own_keys_never_collide(self, tmp_path, monkeypatch):
        home_co = tmp_path / "home" / ".co"
        home_co.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: home_co.parent)

        first, second = tmp_path / "a" / ".co", tmp_path / "b" / ".co"
        for co in (first, second):
            co.mkdir(parents=True)
            address.save(address.generate(), co)

        assert claim_identity(first, resolve_agent_identity(first), "a") is None
        assert claim_identity(second, resolve_agent_identity(second), "b") is None

    def test_the_claim_is_keyed_on_the_address(self, tmp_path, monkeypatch):
        """Not in the project, and not beside the key either.

        Beside the key only catches projects sharing one `.co`. A copied
        `.co/keys/`, or AGENT_CONFIG_PATH pointing two projects at one
        directory, is the same collision on the network and was invisible to
        that. The address is what actually collides, so it is what the record
        is filed under — in ~/.co, because "who on this machine serves this
        address" is not any one project's question, and because a record there
        never travels in a deploy.
        """
        home_co = tmp_path / "home" / ".co"
        home_co.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: home_co.parent)
        project = tmp_path / "p" / ".co"
        project.mkdir(parents=True)
        address.save(address.generate(), project)

        claim_identity(project, resolve_agent_identity(project), "p")

        identity = resolve_agent_identity(project)
        assert (home_co / "served_by" / f"{identity['address']}.json").exists()
        assert not (project / "served_by.json").exists()


class TestWhereTheIdentityCameFrom:
    """claim_identity has to record against the key's own directory, so the
    loaded identity has to say which one that was."""

    def test_a_loaded_identity_says_which_directory_it_came_from(self, shared, monkeypatch):
        """It used to be the global one for a keyless project. Since #689 a
        keyless project derives instead, so what this checks is the surviving
        case: a key on disk reports its own directory."""
        home_co, first, _ = shared
        monkeypatch.setattr(Path, "home", lambda: home_co.parent)

        assert resolve_agent_identity(first)["source"] == str(first)

    def test_a_local_identity_says_the_project(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "nowhere")
        co = tmp_path / "p" / ".co"
        co.mkdir(parents=True)
        address.save(address.generate(), co)

        assert resolve_agent_identity(co)["source"] == str(co)


class TestTheRecordItself:

    def test_it_is_readable_json(self, shared, monkeypatch):
        home_co, first, _ = shared
        monkeypatch.setattr(Path, "home", lambda: home_co.parent)

        identity = resolve_agent_identity(first)
        claim_identity(first, identity, "oo")
        record = json.loads(
            (home_co / "served_by" / f"{identity['address']}.json").read_text())

        assert record["name"] == "oo"
        assert record["project"] == str(first.parent)

    def test_a_corrupt_record_does_not_stop_the_agent(self, shared, monkeypatch):
        """It is a warning aid, not a gate. Losing it costs a warning."""
        home_co, first, _ = shared
        monkeypatch.setattr(Path, "home", lambda: home_co.parent)
        (home_co / "served_by.json").write_text("{not json")

        assert claim_identity(first, resolve_agent_identity(first), "oo") is None


class TestTheClaimStaysOnThisMachine:
    """It names a directory on the operator's laptop.

    Shipped, it would put that path on the server and make the deployed agent
    read the laptop's claim as a collision every time it starts — the warning
    firing on the one agent that is not the problem.

    Driven through real rsync rather than asserting against the exclude list.
    #686 found `.env.example` silently not travelling that way: what the list
    says and what rsync does are two different questions.
    """

    def test_it_does_not_travel(self, tmp_path):
        import shutil
        import subprocess

        if not shutil.which("rsync"):
            pytest.skip("no rsync here")

        from connectonion.cli.commands.deploy_to_server import RSYNC_FILTERS

        project = tmp_path / "project"
        (project / ".co").mkdir(parents=True)
        (project / "agent.py").write_text("# the agent")
        (project / ".co" / "served_by.json").write_text('{"name": "oo"}')
        (project / ".co" / "host.yaml").write_text("workers: 1\n")

        out = subprocess.run(
            ["rsync", "-an", "--out-format=%n", *RSYNC_FILTERS,
             f"{project}/", str(tmp_path / "server")],
            capture_output=True, text=True, timeout=300,
        )
        assert out.returncode == 0, out.stderr[-300:]
        sent = out.stdout.split()

        assert ".co/served_by.json" not in sent, sent
        assert "agent.py" in sent, f"the exclude took the project with it: {sent}"
        assert ".co/host.yaml" in sent, f"the rest of .co stopped travelling: {sent}"


class TestItNeverStopsTheAgentStarting:

    def test_a_missing_directory_costs_a_warning_not_a_start(self, tmp_path):
        """Recording who serves an identity is a hint. Nine host tests died on
        the first draft of this, which wrote the record without asking whether
        the directory was there."""
        identity = {"address": "0x" + "b" * 64, "source": str(tmp_path / "gone")}

        assert claim_identity(tmp_path / "p" / ".co", identity, "p") is None
