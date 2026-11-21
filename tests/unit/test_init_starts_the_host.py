"""`co init` leaves the always-on Host running; `co host` shows it (#3170).

One command sets everything up. After `co init` there is nothing else to start:
the Host (agent, REM, schedule, channels) runs as a user service, and a bare
`co host` reports on it instead of starting a second one. Your own agent.py is
the special case and needs `--agent`.
"""
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli import mac_bootstrap
from connectonion.cli import main as cli
from connectonion.cli.commands import init as init_commands
from connectonion.cli.host_service import HostServiceError, HostServiceUnavailable
from connectonion.cli.main import app


@pytest.fixture
def quiet_global_setup(monkeypatch):
    """Global init without the network, Codex install or REM: only the Host step is real."""
    monkeypatch.setattr(init_commands, "handle_global_init", lambda **kw: None)
    monkeypatch.setattr("connectonion.cli.codex_setup.setup_codex",
                        lambda: {"summary": "Codex: ready", "undo": "-", "ready": True, "next_action": ""})
    started = []

    def prepare():
        started.append(True)
        return {"configured": True, "running": True, "pid": 77, "model": "codex", "model_ready": True,
                "codex_ready": True, "profile": "/p", "rem_prepared": True, "watch_connector_ready": False}
    monkeypatch.setattr(mac_bootstrap, "prepare_host", prepare)
    return started


def test_global_init_starts_the_host_without_any_flag(quiet_global_setup):
    result = CliRunner().invoke(app, ["init", "--no-rem"])
    assert result.exit_code == 0, result.output
    assert quiet_global_setup == [True]
    assert "Host running in the background (model: codex, pid 77)" in result.output


def test_no_host_skips_it(quiet_global_setup):
    result = CliRunner().invoke(app, ["init", "--no-rem", "--no-host"])
    assert result.exit_code == 0, result.output
    assert quiet_global_setup == []


def test_the_old_background_flag_still_works_and_does_the_same(quiet_global_setup):
    result = CliRunner().invoke(app, ["init", "--no-rem", "--background"])
    assert result.exit_code == 0, result.output
    assert quiet_global_setup == [True]


def test_a_platform_without_a_user_service_is_skipped_not_failed(quiet_global_setup, monkeypatch):
    def unsupported():
        raise HostServiceUnavailable("A background Host needs macOS or Linux with systemd. Next: co host --serve")
    monkeypatch.setattr(mac_bootstrap, "prepare_host", unsupported)
    result = CliRunner().invoke(app, ["init", "--no-rem"])
    assert result.exit_code == 0, result.output
    assert "Background Host skipped" in result.output


def test_a_host_that_fails_to_start_fails_init(quiet_global_setup, monkeypatch):
    def broken():
        raise HostServiceError("macOS could not load the service; its files were preserved. Next: co host --status")
    monkeypatch.setattr(mac_bootstrap, "prepare_host", broken)
    result = CliRunner().invoke(app, ["init", "--no-rem"])
    assert result.exit_code == 1
    assert "did not start" in result.output


def test_a_model_that_cannot_answer_says_how_to_fix_it(quiet_global_setup, monkeypatch):
    monkeypatch.setattr(mac_bootstrap, "prepare_host", lambda: {
        "running": True, "pid": 5, "model": "claude-code", "model_ready": False,
        "model_problem": "Claude Code is not logged in", "next_action": "claude auth login"})
    result = CliRunner().invoke(app, ["init", "--no-rem"])
    assert result.exit_code == 0, result.output
    assert "claude auth login" in result.output


# ---- co host ----

class FakeService:
    def __init__(self, running=True):
        self.running = running

    def status(self):
        return {"configured": True, "running": self.running, "pid": 77 if self.running else None,
                "device_ready": False}


@pytest.fixture
def profile(tmp_path, monkeypatch):
    home = tmp_path / "home"
    runtime = home / ".co" / "runtime" / "host"
    (runtime / ".co").mkdir(parents=True)
    (runtime / ".co" / "host.yaml").write_text("name: my-host\nport: 8123\nmodel: claude-code\n")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(mac_bootstrap, "profile_dir", lambda: runtime)
    monkeypatch.setattr("connectonion.cli.host_service.host_service", lambda target, **kw: FakeService())
    monkeypatch.chdir(home)
    return runtime


def test_bare_co_host_shows_the_running_host(profile):
    result = CliRunner().invoke(app, ["host"])
    assert result.exit_code == 0, result.output
    assert "Running in the background (pid 77)" in result.output
    assert "model claude-code" in result.output and "Port: 8123" in result.output
    assert "co host --stop" in result.output


def test_bare_co_host_before_init_says_to_run_it(tmp_path, monkeypatch):
    monkeypatch.setattr(mac_bootstrap, "profile_dir", lambda: tmp_path / "nothing")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["host"])
    assert result.exit_code == 0
    assert "Next: co init" in result.output


def test_an_agent_py_in_a_terminal_is_not_served_without_agent(profile, tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "agent.py").write_text("raise SystemExit('must not run')\n")
    monkeypatch.chdir(project)
    monkeypatch.setattr(cli, "_in_terminal", lambda: True)
    import os
    monkeypatch.setattr(os, "execve", lambda *a: pytest.fail("agent.py ran without --agent"))
    result = CliRunner().invoke(app, ["host"])
    assert "co host --agent agent.py" in result.output


def test_agent_runs_your_own_agent_py(tmp_path, monkeypatch):
    import os
    (tmp_path / "agent.py").write_text("# synthetic")
    monkeypatch.chdir(tmp_path)
    ran = []
    monkeypatch.setattr(os, "execve", lambda exe, argv, env: ran.append(argv))
    CliRunner().invoke(app, ["host", "--agent", "agent.py"])
    assert ran and ran[0][-1] == "agent.py"


def test_a_service_from_before_3170_keeps_serving_its_agent_py(tmp_path, monkeypatch):
    """Its plist runs a bare `co host` in the project with no terminal."""
    import os
    (tmp_path / "agent.py").write_text("# synthetic")
    monkeypatch.chdir(tmp_path)
    ran = []
    monkeypatch.setattr(os, "execve", lambda exe, argv, env: ran.append(argv))
    CliRunner().invoke(app, ["host"])  # CliRunner's stdin is not a terminal
    assert ran and ran[0][-1] == "agent.py"


def test_serve_runs_the_built_in_agent_here(tmp_path, monkeypatch):
    served = []
    monkeypatch.setattr(mac_bootstrap, "serve_project", lambda project, port=None: served.append((project, port)))
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["host", "--serve", "--port", "9001"])
    assert result.exit_code == 0, result.output
    assert served == [(Path.cwd(), 9001)]


def test_serve_without_a_host_yaml_says_to_init(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["host", "--serve"])
    assert result.exit_code == 1
    assert "co init" in result.output
