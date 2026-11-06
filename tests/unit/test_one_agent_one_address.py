"""Identity claims live beside their key and stay on the serving machine."""

import json
import os
from pathlib import Path

import httpx
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


@pytest.fixture
def previous_project(shared, monkeypatch):
    home_co, first, second = shared
    monkeypatch.setattr(Path, "home", lambda: home_co.parent)

    def no_listener(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx, "get", no_listener)
    monkeypatch.chdir(first.parent)
    claim_identity(first, resolve_agent_identity(first), "cedar")
    monkeypatch.chdir(second.parent)
    return shared


class TestTheSecondAgentIsTold:

    @pytest.mark.parametrize("name", ["cedar", "maple"])
    def test_a_different_project_is_told_without_blocking(
            self, previous_project, capsys, name):
        home_co, first, second = previous_project

        assert claim_identity(second, resolve_agent_identity(second), name) is None

        notice = capsys.readouterr().out
        assert "[host] This address was last served from" in notice
        assert str(first.parent) in notice
        assert f"serving it from {second.parent}" in notice
        assert json.loads((home_co / "served_by.json").read_text())["project"] == str(second.parent)

    @pytest.mark.parametrize("name", ["cedar", "renamed"])
    def test_a_restart_or_rename_in_the_same_folder_is_quiet(
            self, previous_project, monkeypatch, capsys, name):
        _, first, _ = previous_project
        monkeypatch.chdir(first.parent)

        assert claim_identity(first, resolve_agent_identity(first), name) is None
        assert capsys.readouterr().out == ""


class TestTheWarningTellsTheTruth:

    def test_it_reports_an_unverified_host_without_identity_replacement_advice(
            self, previous_project, capsys):
        home_co, _, second = previous_project
        key = home_co / "keys" / "agent.key"
        original_key = key.read_bytes()

        assert claim_identity(second, resolve_agent_identity(second), "maple") is None

        notice = capsys.readouterr().out
        assert "no matching Host verified now" in notice
        assert "not running" not in notice
        assert "address.save" not in notice
        assert "address.generate" not in notice
        assert "co create" not in notice
        assert key.read_bytes() == original_key

    @pytest.mark.parametrize("change", ["another-address", "missing-project"])
    def test_it_only_reports_a_known_project_for_this_address(
            self, previous_project, capsys, change):
        home_co, _, second = previous_project
        record = home_co / "served_by.json"
        existing = json.loads(record.read_text())
        if change == "another-address":
            existing["address"] = address.generate()["address"]
        else:
            del existing["project"]
        record.write_text(json.dumps(existing))

        assert claim_identity(second, resolve_agent_identity(second), "maple") is None
        assert capsys.readouterr().out == ""


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
