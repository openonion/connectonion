"""#2819: CLI trust edits and the Host must refer to the intended agent."""

from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.network.host import server
from connectonion.network.host.session import SessionStorage
from connectonion.network.trust.tools import list_file

CALLER = "0x" + "b1" * 32


def running_host_trust(monkeypatch, storage=None):
    captured = {}
    real_routes = server._create_route_handlers

    def routes(*args, **kwargs):
        result = real_routes(*args, **kwargs)
        captured["trust"] = result["trust_agent"]
        return result

    def create_agent():
        agent = MagicMock()
        agent.name = "trust-path-test"
        agent.tools.names.return_value = []
        return agent

    monkeypatch.setattr(server, "_create_route_handlers", routes)
    server.create_app(create_agent, storage=storage, trust="careful")
    return captured["trust"]


@pytest.mark.parametrize("subdirectory", [False, True])
def test_cli_edits_the_same_lists_as_the_default_host(tmp_path, monkeypatch, subdirectory):
    co_dir = tmp_path / ".co"
    co_dir.mkdir()
    cwd = tmp_path / "subdir" if subdirectory else tmp_path
    cwd.mkdir(exist_ok=True)
    monkeypatch.chdir(cwd)
    trust = running_host_trust(monkeypatch)
    runner = CliRunner()

    assert runner.invoke(app, ["trust", "add", CALLER]).exit_code == 0
    assert list_file("contacts") == trust._co_dir / "contacts.txt" == co_dir / "contacts.txt"
    assert "contact" in runner.invoke(app, ["trust", "level", CALLER]).output
    assert trust.get_level(CALLER) == "contact"
    assert trust.should_allow(CALLER).allow
    assert runner.invoke(app, ["trust", "block", CALLER]).exit_code == 0
    assert trust.get_level(CALLER) == "blocked"
    assert not trust.should_allow(CALLER).allow


def test_custom_host_storage_and_a_different_cli_project_read_different_lists(tmp_path, monkeypatch):
    hosted = tmp_path / "hosted" / ".co"
    launcher = tmp_path / "launcher"
    hosted.mkdir(parents=True)
    (launcher / ".co").mkdir(parents=True)
    (hosted / "contacts.txt").write_text(CALLER + "\n")
    monkeypatch.chdir(launcher)
    trust = running_host_trust(monkeypatch, SessionStorage(hosted / "sessions.jsonl"))
    runner = CliRunner()

    assert trust.get_level(CALLER) == "contact"
    assert trust.should_allow(CALLER).allow
    assert "stranger" in runner.invoke(app, ["trust", "level", CALLER]).output
    assert list_file("contacts") == launcher / ".co" / "contacts.txt"
    assert trust._co_dir / "contacts.txt" == hosted / "contacts.txt"
    # Selecting the hosted project makes the CLI and Host agree again.
    monkeypatch.chdir(hosted.parent)
    assert "contact" in runner.invoke(app, ["trust", "level", CALLER]).output
    assert runner.invoke(app, ["trust", "remove", CALLER]).exit_code == 0
    assert trust.get_level(CALLER) == "stranger"
    assert not trust.should_allow(CALLER).allow


def test_co_ai_host_uses_global_identity_lists_while_co_trust_uses_the_project(tmp_path, monkeypatch):
    from connectonion.cli.co_ai import main as co_ai_main
    from connectonion.cli.commands import project_cmd_lib

    global_co = tmp_path / "global" / ".co"
    project = tmp_path / "project"
    global_co.mkdir(parents=True)
    (project / ".co").mkdir(parents=True)
    (global_co / "contacts.txt").write_text(CALLER + "\n")
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(global_co))
    monkeypatch.chdir(project)
    monkeypatch.setattr(project_cmd_lib, "ensure_global_config", lambda: None)
    hosted = {}
    monkeypatch.setattr(co_ai_main, "host", lambda agent, **kw: hosted.update(kw))
    co_ai_main.start_server(object(), invite_code="test-invite", launch=False)
    trust = hosted["trust"]
    runner = CliRunner()

    assert hosted["co_dir"] == global_co
    assert trust.get_level(CALLER) == "contact"
    assert trust.should_allow(CALLER).allow
    assert "stranger" in runner.invoke(app, ["trust", "level", CALLER]).output
    assert runner.invoke(app, ["trust", "block", CALLER]).exit_code == 0
    assert (project / ".co" / "blocklist.txt").exists()
    assert not (global_co / "blocklist.txt").exists()
    assert trust.get_level(CALLER) == "contact"
    assert CALLER in runner.invoke(app, ["trust", "list", "--global"]).output
