"""`co call` says which address it signed with, and can be told which (#3298, #3182).

Inside a checkout with its own .co/keys, `co call` signed as that project, not
as the user's ~/.co. A host that trusts the global address then answered
"agent requires onboarding (invite_code)", and nothing in the output said which
address had called, so it looked like the remote's trust had changed.
"""
from pathlib import Path

import pytest

from connectonion import ExecResult, address
from connectonion.cli.commands.call_commands import handle_call

AGENT = "0x" + "a" * 64


@pytest.fixture
def two_identities(tmp_path, monkeypatch):
    """A global ~/.co key and a project with a different key of its own; cwd is the project."""
    monkeypatch.delenv("AGENT_CONFIG_PATH", raising=False)
    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    mine = address.generate()
    address.save(mine, home / ".co")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    project = tmp_path / "repo"
    (project / ".git").mkdir(parents=True)
    (project / ".co").mkdir()
    projects = address.generate()
    address.save(projects, project / ".co")
    monkeypatch.chdir(project)
    return mine, projects


def remote_answering(monkeypatch, result):
    """connect() returns a remote with a canned answer; records the keys it was given."""
    used = []

    class Remote:
        def call(self, tool, command=None, timeout=60.0, **kw):
            return result

    def connect(target, keys=None, **kw):
        used.append(keys)
        return Remote()
    monkeypatch.setattr("connectonion.connect", connect, raising=False)
    return used


def test_a_refusal_names_the_project_address_and_where_its_key_came_from(two_identities, monkeypatch, capsys):
    _, projects = two_identities
    remote_answering(monkeypatch, ExecResult(text="", status="error",
                                             error="agent requires onboarding (invite_code)"))
    assert handle_call([AGENT, "co", "status"]) == 1
    err = capsys.readouterr().err
    assert "agent requires onboarding" in err
    assert f"signed as {projects['address']}" in err
    assert str(Path.cwd() / ".co") in err and "--global" in err
    assert err.count("signed as") == 1


def test_a_refusal_with_the_global_key_names_it_too(two_identities, tmp_path, monkeypatch, capsys):
    mine, _ = two_identities
    monkeypatch.chdir(tmp_path)
    remote_answering(monkeypatch, ExecResult(text="", status="error", error="not trusted"))
    assert handle_call([AGENT, "co", "status"]) == 1
    err = capsys.readouterr().err
    assert err.splitlines()[0] == "not trusted"
    assert f"signed as {mine['address']} from {Path.home() / '.co'}/keys" in err


def test_signing_as_a_project_is_said_even_when_it_works(two_identities, monkeypatch, capsys):
    _, projects = two_identities
    remote_answering(monkeypatch, ExecResult(text="ok", status="success"))
    assert handle_call([AGENT, "co", "status"]) == 0
    out = capsys.readouterr()
    assert out.out.strip() == "ok"
    assert f"signed as {projects['address']}" in out.err


def test_global_signs_as_the_users_own_identity(two_identities, monkeypatch, capsys):
    mine, _ = two_identities
    used = remote_answering(monkeypatch, ExecResult(text="ok", status="success"))
    assert handle_call(["--global", AGENT, "co", "status"]) == 0
    assert used[0]["address"] == mine["address"]
    assert capsys.readouterr().err == ""


def test_co_dir_signs_with_that_folders_key(two_identities, tmp_path, monkeypatch):
    other = address.generate()
    address.save(other, tmp_path / "other" / ".co")
    used = remote_answering(monkeypatch, ExecResult(text="ok", status="success"))
    assert handle_call(["--co-dir", str(tmp_path / "other" / ".co"), AGENT, "co", "status"]) == 0
    assert used[0]["address"] == other["address"]


def test_co_dir_without_a_key_is_a_usage_error(two_identities, tmp_path, monkeypatch, capsys):
    used = remote_answering(monkeypatch, ExecResult(text="ok", status="success"))
    assert handle_call(["--co-dir", str(tmp_path / "nowhere"), AGENT, "co", "status"]) == 2
    assert used == [] and "keys/agent.key" in capsys.readouterr().err
