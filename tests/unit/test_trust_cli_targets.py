"""Trust commands must target the lists the running Host actually reads."""
import shlex

import click
import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.network.trust import TrustAgent

CALLER = "0x" + "b1" * 32


@pytest.mark.parametrize("explicit", [False, True])
def test_trust_level_block_remove_name_and_use_the_selected_files(tmp_path, monkeypatch, explicit):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    local = project / ".co"
    selected = tmp_path / "global identity" / ".co" if explicit else local
    local.mkdir()
    selected.mkdir(parents=True, exist_ok=True)
    (selected / "contacts.txt").write_text(CALLER + "\n")
    (selected / "whitelist.txt").write_text(CALLER + "\n")
    trust = TrustAgent("careful", co_dir=selected)
    args = ["--co-dir", str(selected)] if explicit else []
    runner = CliRunner()

    level = runner.invoke(app, ["trust", "level", CALLER, *args])
    assert level.exit_code == 0, level.output
    assert "whitelist" in level.output
    for name in ("blocklist", "whitelist", "contacts", "handoffs", "admins"):
        assert str(selected / f"{name}.txt") in level.output

    removed = runner.invoke(app, ["trust", "remove", CALLER, *args])
    assert removed.exit_code == 0, removed.output
    for name in ("contacts", "whitelist"):
        assert str(selected / f"{name}.txt") in removed.output
    assert trust.get_level(CALLER) == "stranger"

    blocked = runner.invoke(app, ["trust", "block", CALLER, *args])
    assert blocked.exit_code == 0, blocked.output
    assert str(selected / "blocklist.txt") in blocked.output
    assert trust.get_level(CALLER) == "blocked"
    if explicit:
        assert not (local / "blocklist.txt").exists()


def test_trust_level_admin_also_names_its_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    co_dir = tmp_path / ".co"
    co_dir.mkdir()
    (co_dir / "admins.txt").write_text(CALLER + "\n")
    result = CliRunner().invoke(app, ["trust", "level", CALLER])
    assert result.exit_code == 0
    assert "admin" in result.output
    assert str(co_dir / "admins.txt") in result.output


def test_host_auto_hint_blocks_the_hosts_lists_even_when_logs_and_cwd_differ(tmp_path, monkeypatch, capsys):
    from connectonion import Agent
    from connectonion.core.host_context import begin_auto_run, finish_auto_run
    from connectonion.network.host import server
    from connectonion.network.host.session import SessionStorage
    from tests.utils.mock_helpers import MockLLM

    project = tmp_path / "launcher"
    project.mkdir()
    monkeypatch.chdir(project)
    trust_dir = tmp_path / "global identity" / ".co"
    trust_dir.mkdir(parents=True)
    (trust_dir / "contacts.txt").write_text(CALLER + "\n")
    trust = TrustAgent("careful", co_dir=trust_dir)
    agent = Agent("host", llm=MockLLM(), co_dir=tmp_path / "logs", quiet=True)

    def run(prompt, *, session, **kwargs):
        agent.current_session = session
        context = begin_auto_run(agent, "write", prompt)
        finish_auto_run(agent, context, "completed")
        return "done"

    monkeypatch.setattr(agent, "input", run)
    routes = server._create_route_handlers(lambda: agent, {"name": "host"}, 3600, trust, {})
    storage = SessionStorage(tmp_path / "sessions.jsonl")
    routes["ws_input"](storage, "write a note", None, session={"session_id": "one"}, requester_address=CALLER)
    output = capsys.readouterr().out
    assert "before its next tool or model step, connected or not" in output
    command = output.split("Revoke access on this Host: ", 1)[1].split(". Revocation", 1)[0]
    args = shlex.split(command)
    assert args[:4] == ["co", "trust", "block", CALLER]
    assert args[4:] == ["--co-dir", str(trust_dir.resolve())]
    result = CliRunner().invoke(app, args[1:])
    assert result.exit_code == 0, result.output
    assert trust.get_level(CALLER) == "blocked"
    assert not (project / ".co" / "blocklist.txt").exists()


@pytest.mark.parametrize("target", ["--co-dir", "--global", "-g"])
def test_block_then_unblock_clears_the_hosts_list(tmp_path, monkeypatch, target):
    project = tmp_path / "project"
    (project / ".co").mkdir(parents=True)
    selected = tmp_path / "host identity" / ".co"
    selected.mkdir(parents=True)
    monkeypatch.chdir(project)
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(selected))
    (selected / "contacts.txt").write_text(CALLER + "\n")
    trust = TrustAgent("careful", co_dir=selected)
    args = ["--co-dir", str(selected)] if target == "--co-dir" else [target]
    runner = CliRunner()

    blocked = runner.invoke(app, ["trust", "block", CALLER, *args])
    assert blocked.exit_code == 0, blocked.output
    assert trust.get_level(CALLER) == "blocked"
    assert not trust.should_allow(CALLER).allow
    level = runner.invoke(app, ["trust", "level", CALLER, *args])
    assert level.exit_code == 0, level.output
    tip = level.output.split("Next: ", 1)[1].strip()
    tip_args = shlex.split(tip)
    assert tip_args[:4] == ["co", "trust", "unblock", CALLER]
    unblocked = runner.invoke(app, tip_args[1:])
    assert unblocked.exit_code == 0, unblocked.output
    assert trust.get_level(CALLER) == "contact"
    assert trust.should_allow(CALLER).allow
    assert CALLER not in (selected / "blocklist.txt").read_text()
    assert not (project / ".co" / "blocklist.txt").exists()


@pytest.mark.parametrize("target", ["--co-dir", "--global", "-g"])
def test_all_trust_commands_share_one_target(tmp_path, monkeypatch, target):
    project = tmp_path / "project"
    (project / ".co").mkdir(parents=True)
    selected = tmp_path / "identity" / ".co"
    selected.mkdir(parents=True)
    monkeypatch.chdir(project)
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(selected))
    args = ["--co-dir", str(selected)] if target == "--co-dir" else [target]
    trust = TrustAgent("careful", co_dir=selected)
    runner = CliRunner()

    def invoke(*command):
        result = runner.invoke(app, ["trust", *command, *args])
        assert result.exit_code == 0, result.output
        tip = result.output.split("Next: ", 1)[1]
        assert shlex.quote(str(selected.resolve())) in tip, tip
        return result.output

    invoke("add", CALLER)
    assert trust.get_level(CALLER) == "contact"
    assert CALLER in invoke("list")
    invoke("add", CALLER, "-w")
    assert trust.get_level(CALLER) == "whitelist"
    invoke("block", CALLER)
    assert trust.get_level(CALLER) == "blocked"
    invoke("unblock", CALLER)
    assert trust.get_level(CALLER) == "whitelist"
    invoke("remove", CALLER)
    assert trust.get_level(CALLER) == "stranger"
    invoke("admin", "add", CALLER)
    assert "admin" in invoke("level", CALLER)
    assert CALLER in (selected / "admins.txt").read_text()
    invoke("admin", "remove", CALLER)
    assert CALLER not in (selected / "admins.txt").read_text()
    assert "stranger" in invoke("level", CALLER)
    assert list((project / ".co").iterdir()) == []


def test_conflicting_targets_fail_without_writing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["trust", "block", CALLER,
                                     "--co-dir", str(tmp_path / "host"), "--global"])
    assert result.exit_code == 2
    # Rich colours option names when the terminal (or CI) asks for colour, so
    # "--co-dir" arrives wrapped in escape codes: read the text, not the styling.
    assert "Use either --co-dir or --global" in click.unstyle(result.output)
    assert not (tmp_path / "host").exists()
    assert not (tmp_path / ".co").exists()


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("command,written", [
    (["add"], "contacts"), (["add", "-w"], "whitelist"), (["unblock"], "blocklist"),
    (["admin", "add"], "admins"), (["admin", "remove"], "admins"),
])
def test_every_trust_edit_names_the_file_it_wrote(tmp_path, monkeypatch, explicit, command, written):
    """#3026 / #2819: add, unblock and admin add/remove say which list they changed."""
    project = tmp_path / "project"
    (project / ".co").mkdir(parents=True)
    monkeypatch.chdir(project)
    selected = tmp_path / "host identity" / ".co" if explicit else project / ".co"
    selected.mkdir(parents=True, exist_ok=True)
    (selected / "blocklist.txt").write_text(CALLER + "\n")
    (selected / "admins.txt").write_text(CALLER + "\n")
    args = ["--co-dir", str(selected)] if explicit else []
    result = CliRunner().invoke(app, ["trust", *command, CALLER, *args])
    assert result.exit_code == 0, result.output
    assert f"Updated: {selected / f'{written}.txt'}" in result.output
