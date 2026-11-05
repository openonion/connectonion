"""Identity claims live beside their key and stay on the serving machine."""

import json
import os
from pathlib import Path

import pytest

from connectonion import address
from connectonion.network.host.server import claim_identity, resolve_agent_identity


@pytest.fixture
def shared(tmp_path):
    """One global ~/.co holding the only keypair, and two projects with none."""
    home_co = tmp_path / "home" / ".co"
    home_co.mkdir(parents=True)
    address.save(address.generate(), home_co)

    first = tmp_path / "cedar" / ".co"
    second = tmp_path / "maple" / ".co"
    for co in (first, second):
        co.mkdir(parents=True)
    return home_co, first, second


class TestAProjectWithItsOwnKey:
    """Separate identities can be served independently."""

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

    def test_the_claim_lands_beside_the_key_it_is_about(self, tmp_path, monkeypatch):
        """Not in the project — the whole point is that several projects share
        one identity directory, so the record has to live with the key."""
        home_co = tmp_path / "home" / ".co"
        home_co.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: home_co.parent)
        project = tmp_path / "p" / ".co"
        project.mkdir(parents=True)
        address.save(address.generate(), project)

        claim_identity(project, resolve_agent_identity(project), "p")

        assert (project / "served_by.json").exists()
        assert not (home_co / "served_by.json").exists()


class TestWhereTheIdentityCameFrom:
    """claim_identity has to record against the key's own directory, so the
    loaded identity has to say which one that was."""

    def test_an_inherited_identity_says_it_is_the_global_one(self, shared, monkeypatch):
        home_co, first, _ = shared
        monkeypatch.setattr(Path, "home", lambda: home_co.parent)

        assert resolve_agent_identity(first)["source"] == str(home_co)

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

        monkeypatch.chdir(first.parent)
        claim_identity(first, resolve_agent_identity(first), "cedar")
        record = json.loads((home_co / "served_by.json").read_text())

        assert record["name"] == "cedar"
        assert record["project"] == str(first.parent)
        assert record["pid"] == os.getpid()
        assert record["port"] == 8000

    def test_a_corrupt_record_does_not_stop_the_agent(self, shared, monkeypatch):
        """Corrupt JSON does not establish a live owner."""
        home_co, first, _ = shared
        monkeypatch.setattr(Path, "home", lambda: home_co.parent)
        (home_co / "served_by.json").write_text("{not json")

        assert claim_identity(first, resolve_agent_identity(first), "cedar") is None


class TestTheClaimStaysOnThisMachine:
    """It names a directory on the operator's laptop.

    Shipped, it would put that path on the server and make the deployed agent
    read a laptop PID as if it belonged to a process on the server.

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
        (project / ".co" / "served_by.json").write_text('{"name": "cedar"}')
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


class TestAMissingIdentityDirectory:

    def test_a_missing_directory_is_not_recorded(self, tmp_path):
        identity = {"address": "0x" + "b" * 64, "source": str(tmp_path / "gone")}

        assert claim_identity(tmp_path / "p" / ".co", identity, "p") is None
