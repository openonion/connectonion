"""Global init installs Codex and leaves sign-in to the owner."""
import importlib
import subprocess
import time
import webbrowser
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from connectonion import codex_cli
from connectonion.cli import codex_setup
from connectonion.cli.commands import init as init_commands, rem_commands
from connectonion.cli.main import app
from connectonion.rem import config, schedule, service
from connectonion.rem.files import read_json, state_path


@pytest.fixture(autouse=True)
def isolated_codex(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("CODEX_CMD", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(codex_cli, "BUNDLED_CODEX", (tmp_path / "ChatGPT.app/codex", tmp_path / "Codex.app/codex"))
    monkeypatch.setattr("shutil.which", lambda name: None)


def executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return str(path)


def test_codex_resolution_order(tmp_path, monkeypatch):
    chatgpt, desktop = codex_cli.BUNDLED_CODEX
    executable(chatgpt)
    executable(desktop)
    local = executable(tmp_path / ".local/bin/codex")
    monkeypatch.setattr("shutil.which", lambda name: "/path/bin/codex")
    assert codex_cli.resolve_codex() == "/path/bin/codex"
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert codex_cli.resolve_codex() == str(chatgpt)
    chatgpt.chmod(0o644)
    assert codex_cli.resolve_codex() == str(desktop)
    desktop.unlink()
    assert codex_cli.resolve_codex() == local


def test_exec_and_tool_share_desktop_resolution(tmp_path):
    from connectonion.rem.codex_exec import exec_command
    tool = importlib.import_module("connectonion.useful_tools.codex")
    bundled = executable(codex_cli.BUNDLED_CODEX[0])
    assert tool._base_command() == [bundled, "app-server"]
    assert exec_command(tmp_path, config.default_config(), last_message=tmp_path / "last")[0] == bundled


def test_standalone_installer_downloads_official_script_once(tmp_path, monkeypatch):
    response = Mock(content=b"# official installer fixture\n")
    download = Mock(return_value=response)
    monkeypatch.setattr(codex_setup.httpx, "get", download)
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if command[0] == "sh":
            assert Path(command[1]).read_bytes() == response.content
            assert kwargs["env"]["CODEX_NON_INTERACTIVE"] == "true"
            assert kwargs["env"]["CODEX_INSTALL_DIR"] == str(tmp_path / ".local/bin")
            executable(tmp_path / ".local/bin/codex")
        return subprocess.CompletedProcess(command, 0, "codex-cli 1.2.3\n", "")

    monkeypatch.setattr(codex_setup.subprocess, "run", run)
    path, version, undo = codex_setup.install_codex()
    download.assert_called_once_with("https://chatgpt.com/codex/install.sh", follow_redirects=True, timeout=30)
    response.raise_for_status.assert_called_once()
    assert path == str(tmp_path / ".local/bin/codex")
    assert version == "1.2.3"
    assert "packages/standalone" in undo
    assert len([cmd for cmd in commands if cmd[0] == "sh"]) == 1


def test_offline_installer_reports_no_network_without_trying_package_managers(monkeypatch):
    """#2874 follow-up: through a dead proxy npm retried for 80 s and `co init --yes` blew its 60 s budget."""
    monkeypatch.setattr(codex_setup.httpx, "get", Mock(side_effect=codex_setup.httpx.ConnectError("connection refused")))
    monkeypatch.setattr("shutil.which", lambda name: {"npm": "/bin/npm", "brew": "/bin/brew"}.get(name))
    run = Mock()
    monkeypatch.setattr(codex_setup.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="no network for the installer"):
        codex_setup.install_codex()
    run.assert_not_called()


def test_installer_failure_falls_back_only_to_available_npm(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_setup, "_install_standalone", Mock(side_effect=RuntimeError("installer did not create an executable")))
    monkeypatch.setattr("shutil.which", lambda name: {"npm": "/bin/npm", "codex": "/npm/bin/codex"}.get(name))
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "codex-cli 1.2.3", ""))
    monkeypatch.setattr(codex_setup.subprocess, "run", run)
    assert codex_setup.install_codex() == ("/npm/bin/codex", "1.2.3", "npm uninstall -g @openai/codex")
    assert run.call_args_list[0].args[0] == ["/bin/npm", "install", "-g", "@openai/codex"]


def test_missing_codex_installs_once_and_checks_login(tmp_path, monkeypatch):
    path = str(tmp_path / ".local/bin/codex")
    install = Mock(return_value=(path, "1.2.3", f"rm -f {path}"))
    monkeypatch.setattr(codex_setup, "install_codex", install)
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(codex_setup.subprocess, "run", run)
    result = codex_setup.setup_codex()
    install.assert_called_once_with()
    assert result["summary"] == f"Codex CLI: installed 1.2.3 at {path}"
    assert result["ready"]
    assert run.call_args.args[0] == [path, "login", "status"]


def test_failed_install_reports_recovery_without_login(monkeypatch):
    monkeypatch.setattr(codex_setup, "install_codex", Mock(side_effect=RuntimeError("network unavailable")))
    run = Mock()
    monkeypatch.setattr(codex_setup.subprocess, "run", run)
    result = codex_setup.setup_codex()
    assert "not installed: network unavailable; run " in result["summary"]
    assert "https://chatgpt.com/codex/install.sh" in result["summary"]
    assert not result["ready"]
    run.assert_not_called()


@pytest.mark.parametrize("logged_in", [False, True])
def test_setup_only_checks_login_status(tmp_path, monkeypatch, logged_in):
    path = executable(codex_cli.BUNDLED_CODEX[0])
    run = Mock(return_value=subprocess.CompletedProcess([], 0 if logged_in else 1))
    monkeypatch.setattr(codex_setup.subprocess, "run", run)
    result = codex_setup.setup_codex()
    assert [call.args[0] for call in run.call_args_list] == [[path, "login", "status"]]
    assert result["ready"] == logged_in
    assert result["login_command"] == f"{path} login"
    assert result["summary"] == f"Codex CLI: found at {path}"


def test_global_init_finishes_with_login_pending(tmp_path, monkeypatch):
    path = executable(tmp_path / "bundled CLI/codex")
    monkeypatch.setattr(codex_cli, "BUNDLED_CODEX", (Path(path),))
    monkeypatch.setattr(codex_cli, "signed_in", lambda command: False)
    monkeypatch.setattr(codex_setup, "claude_ready", lambda: False)
    run = Mock()
    monkeypatch.setattr(codex_setup.subprocess, "run", run)
    spawn = Mock()
    monkeypatch.setattr(codex_setup.subprocess, "Popen", spawn)
    browser = Mock()
    for method in ("open", "open_new", "open_new_tab"):
        monkeypatch.setattr(webbrowser, method, browser)
    monkeypatch.setattr(init_commands, "handle_global_init", lambda **kwargs: None)
    monkeypatch.setattr(service, "mail_available", lambda kind: False)
    monkeypatch.setattr(config, "first_runner", lambda value: value)
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda cfg: ("Codex is not signed in", "codex login"))
    installer = Mock()
    monkeypatch.setattr(schedule, "default_scheduler", lambda *a, **kw: installer)
    build = Mock(return_value={})
    monkeypatch.setattr(rem_commands, "init_rem_flow", build)
    started = time.monotonic()
    result = CliRunner().invoke(app, ["init", "--yes"])
    elapsed = time.monotonic() - started
    assert result.exit_code == 0, result.output
    assert elapsed < 1
    run.assert_not_called()
    spawn.assert_not_called()
    browser.assert_not_called()
    assert result.output.splitlines().count(f"Codex login pending. Run: '{path}' login; then co rem start") == 1
    assert "REM starts after that" not in result.output
    assert "Opening Codex login" not in result.output
    assert f"Codex CLI: found at {path}" in result.output
    assert f"'{path}' login" in result.output
    assert "waiting for Codex login" in result.output
    assert "co rem start" in result.output
    installer.install.assert_not_called()
    build.assert_called_once()
    waiting = read_json(state_path(tmp_path / ".co/rem", "worker.json"), {})
    assert not waiting["enabled"]
    assert "login" in waiting["waiting_for"]


def test_rem_doctor_uses_the_same_bundled_path(tmp_path, monkeypatch):
    path = executable(codex_cli.BUNDLED_CODEX[1])
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda cfg: ("", ""))
    result = CliRunner().invoke(app, ["rem", "--json", "doctor"])
    assert result.exit_code == 0, result.output
    assert f"Codex CLI: found at {path}" in result.output


def test_global_init_installs_only_once_and_no_rem_still_sets_up_codex(tmp_path, monkeypatch):
    path = str(tmp_path / ".local/bin/codex")
    install = Mock(side_effect=lambda: (executable(Path(path)), "1.2.3", f"rm -f {path}"))
    monkeypatch.setattr(codex_setup, "install_codex", install)
    monkeypatch.setattr(codex_setup.subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0)))
    monkeypatch.setattr(init_commands, "handle_global_init", lambda **kw: None)
    rem = Mock()
    monkeypatch.setattr(rem_commands, "init_global_rem", rem)
    first = CliRunner().invoke(app, ["init", "--no-rem"])
    second = CliRunner().invoke(app, ["init", "--no-rem"])
    assert first.exit_code == second.exit_code == 0
    assert f"Codex CLI: installed 1.2.3 at {path}" in first.output
    assert f"Codex CLI: found at {path}" in second.output
    assert f"Undo Codex CLI: rm -f {path}" in first.output
    install.assert_called_once_with()
    rem.assert_not_called()


def test_project_init_does_not_install_codex(tmp_path, monkeypatch):
    install = Mock()
    monkeypatch.setattr(codex_setup, "install_codex", install)
    monkeypatch.setattr(init_commands, "handle_init", lambda **kw: None)
    result = CliRunner().invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0, result.output
    install.assert_not_called()


def test_codex_override_preserves_arguments_for_login(tmp_path, monkeypatch):
    path = executable(tmp_path / "custom CLI/codex")
    monkeypatch.setenv("CODEX_CMD", path)
    run = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(codex_setup.subprocess, "run", run)
    result = codex_setup.setup_codex()
    assert result["ready"]
    assert result["login_command"] == f"'{path}' login"
    assert run.call_args.args[0] == [path, "login", "status"]


def test_brew_fallback_uses_official_cask(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_setup.sys, "platform", "darwin")
    monkeypatch.setattr(codex_setup, "_install_standalone", Mock(side_effect=OSError("offline")))
    monkeypatch.setattr("shutil.which", lambda name: {"brew": "/bin/brew", "codex": "/brew/bin/codex"}.get(name))
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "codex-cli 1.2.3", ""))
    monkeypatch.setattr(codex_setup.subprocess, "run", run)
    assert codex_setup.install_codex() == ("/brew/bin/codex", "1.2.3", "brew uninstall --cask codex")
    assert run.call_args_list[0].args[0] == ["/bin/brew", "install", "--cask", "codex"]


def test_codex_ready_rejects_stale_auth_and_accepts_keychain_login(tmp_path, monkeypatch):
    from connectonion.rem.runner import ready
    path = executable(codex_cli.BUNDLED_CODEX[0])
    auth = tmp_path / ".codex/auth.json"
    auth.parent.mkdir()
    auth.write_text("{}")
    run = Mock(return_value=subprocess.CompletedProcess([], 1))
    monkeypatch.setattr(codex_cli.subprocess, "run", run)
    assert ready({"runner": "codex"}) == ("Codex is not signed in", f"{path} login")
    auth.unlink()
    run.return_value = subprocess.CompletedProcess([], 0)
    assert ready({"runner": "codex"}) == ("", "")


def test_mac_host_persists_off_path_cli(tmp_path, monkeypatch):
    from connectonion.cli.host_service import HostService
    from connectonion.cli.mac_bootstrap import _codex_readiness
    path = executable(tmp_path / ".local/bin/codex")
    monkeypatch.setattr("shutil.which", lambda name, **kw: None)
    service = HostService(tmp_path / "project", native_codex=True)
    service._prepare_provider()
    assert service.provider_paths["CODEX_CMD"] == path
    monkeypatch.setattr(codex_setup.subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0)))
    assert _codex_readiness({"HOME": str(tmp_path), "PATH": "/bin:/usr/bin"})["codex_ready"]


def test_linux_and_mac_schedule_keep_codex_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-profile"))
    monkeypatch.setenv("CODEX_CMD", str(tmp_path / "custom/codex"))
    from plistlib import loads
    linux = schedule.Systemd()._environment(["/bin/python"])
    mac = loads(schedule.Launchd().render(tmp_path, config.default_config()).encode())["EnvironmentVariables"]
    for env in (linux, mac):
        assert env["CODEX_HOME"] == str(tmp_path / "codex-profile")
        assert env["CODEX_CMD"] == str(tmp_path / "custom/codex")


@pytest.mark.parametrize("logged_in", [False, True])
def test_claude_fallback_requires_login(tmp_path, monkeypatch, logged_in):
    tool = importlib.import_module("connectonion.useful_tools.claude_code")
    monkeypatch.setattr(tool, "_base_command", lambda: ["/bin/claude"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-for-subscription-runs")
    run = Mock(return_value=subprocess.CompletedProcess([], 0, '{"loggedIn": ' + str(logged_in).lower() + '}'))
    monkeypatch.setattr(codex_setup.subprocess, "run", run)
    assert codex_setup.claude_ready() == logged_in
    assert run.call_args.args[0] == ["/bin/claude", "auth", "status", "--json"]
    assert "ANTHROPIC_API_KEY" not in run.call_args.kwargs["env"]


def test_init_uses_signed_in_claude_when_codex_login_is_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_setup, "claude_ready", lambda: True)
    monkeypatch.setattr(config, "first_runner", lambda value: value)
    monkeypatch.setattr(service, "mail_available", lambda kind: False)
    monkeypatch.setattr(rem_commands, "init_rem_flow", Mock(return_value={}))
    install = Mock(return_value={"scheduler": "launchd"})
    monkeypatch.setattr(rem_commands, "_install_upkeep", install)
    monkeypatch.setattr(schedule, "default_scheduler", lambda *a, **kw: Mock())
    rem_commands.init_global_rem(codex={"ready": False, "next_action": "/bin/codex login"})
    assert config.read_config(tmp_path / ".co/rem")["runner"] == "claude-code"
    install.assert_called_once()


def test_waiting_schedule_is_visible_and_start_clears_it(tmp_path, monkeypatch):
    from connectonion.rem.files import write_json
    from datetime import timezone
    monkeypatch.setattr(config, "first_runner", lambda value: value)
    monkeypatch.setattr(service, "mail_available", lambda kind: False)
    config.prepare(tmp_path)
    service.grant_init_sources(tmp_path)
    write_json(state_path(tmp_path, "worker.json"), {"enabled": False, "waiting_for": "Schedule waiting for Codex login; /bin/codex login"})
    assert "waiting for Codex login" in service._state_line(tmp_path, config.read_config(tmp_path), timezone.utc)[0]
    monkeypatch.setattr("connectonion.rem.codex_history.archive_history", lambda *a, **kw: {})
    clock = Mock()
    clock.install.return_value = {"scheduler": "launchd"}
    service.start(tmp_path, confirm=lambda summary: True, scheduler=clock, run_first_batch=False)
    assert "waiting_for" not in service.worker_state(tmp_path)
    assert service.worker_state(tmp_path)["enabled"]
