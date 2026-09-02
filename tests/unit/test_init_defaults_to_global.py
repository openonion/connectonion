"""No path means machine setup; project writes require an explicit directory."""

from pathlib import Path
from unittest.mock import Mock
from hashlib import sha256
import os

import pytest
from dotenv import dotenv_values
from typer.testing import CliRunner

from connectonion.cli.commands import init as init_command
from connectonion.cli.commands.project_cmd_lib import upsert_env
from connectonion.cli.main import app


@pytest.fixture
def setup_init(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setattr(init_command, "show_progress", lambda *args: None)
    monkeypatch.setattr(init_command, "check_environment_for_api_keys", lambda: None)

    def authenticate(co_dir, save_to_project=True):
        assert co_dir == Path.home() / ".co"
        assert save_to_project is False
        upsert_env(co_dir / "keys.env", {"OPENONION_API_KEY": "fake-managed"})
        return True

    auth = Mock(side_effect=authenticate)
    monkeypatch.setattr(init_command, "authenticate", auth)
    return CliRunner(), work, Path.home() / ".co", auth


@pytest.mark.parametrize("inside_project", [False, True])
def test_no_path_only_initializes_global_config(setup_init, inside_project):
    runner, work, global_dir, auth = setup_init
    if inside_project:
        (work / ".co").mkdir()
        (work / ".co" / "host.yaml").write_text("name: keep-me\n")
        (work / ".env").write_text("OPENAI_API_KEY=sk-project-only\n")
    before = {p.relative_to(work): sha256(p.read_bytes()).hexdigest()
              for p in work.rglob("*") if p.is_file()}

    result = runner.invoke(app, ["init", "--yes"])

    assert result.exit_code == 0, result.output
    assert before == {p.relative_to(work): sha256(p.read_bytes()).hexdigest()
                      for p in work.rglob("*") if p.is_file()}
    assert not (work / "agent.py").exists()
    if not inside_project:
        assert not (work / ".co").exists()
    assert (global_dir / "keys" / "agent.key").is_file()
    keys = dotenv_values(global_dir / "keys.env")
    assert keys["OPENONION_API_KEY"] == "fake-managed"
    assert "OPENAI_API_KEY" not in keys
    auth.assert_called_once_with(global_dir, save_to_project=False)
    assert "co init ./" in result.output


def test_global_init_saves_explicit_key_and_preserves_other_keys(setup_init):
    runner, work, global_dir, _ = setup_init
    global_dir.mkdir()
    upsert_env(global_dir / "keys.env", {"ANTHROPIC_API_KEY": "sk-ant-existing"})

    for _ in range(2):
        result = runner.invoke(app, ["init", "--key", "sk-or-explicit", "--yes"])
        assert result.exit_code == 0, result.output

    keys = dotenv_values(global_dir / "keys.env")
    assert keys["OPENROUTER_API_KEY"] == "sk-or-explicit"
    assert keys["ANTHROPIC_API_KEY"] == "sk-ant-existing"
    assert "sk-or-explicit" not in result.output
    assert (global_dir / "keys.env").read_text().count("OPENROUTER_API_KEY=") == 1
    if os.name != "nt":
        assert (global_dir / "keys.env").stat().st_mode & 0o777 == 0o600
    assert list(work.iterdir()) == []


def test_global_init_does_not_persist_implicitly_loaded_keys(setup_init, monkeypatch):
    runner, _, global_dir, _ = setup_init
    monkeypatch.setenv("OPENAI_API_KEY", "sk-project-or-process")
    monkeypatch.setattr(init_command, "check_environment_for_api_keys",
                        lambda: ("openai", "sk-project-or-process"))

    result = runner.invoke(app, ["init", "--yes"])

    assert result.exit_code == 0, result.output
    assert "OPENAI_API_KEY" not in dotenv_values(global_dir / "keys.env")


def test_global_init_keeps_identity_when_offline(setup_init):
    runner, work, global_dir, auth = setup_init
    auth.side_effect = None
    auth.return_value = False

    result = runner.invoke(app, ["init", "--yes"])

    assert result.exit_code == 0, result.output
    assert (global_dir / "keys.env").is_file()
    assert (global_dir / "keys" / "agent.key").is_file()
    assert "co auth" in result.output
    assert "authenticated" not in result.output.lower()
    assert list(work.iterdir()) == []


def test_global_init_restores_missing_keys_env_without_rotating_identity(setup_init):
    runner, work, global_dir, auth = setup_init
    init_command.ensure_global_config()
    key_file = global_dir / "keys" / "agent.key"
    original = key_file.read_bytes()
    (global_dir / "keys.env").unlink()
    auth.side_effect = None
    auth.return_value = False

    result = runner.invoke(app, ["init", "--yes"])

    assert result.exit_code == 0, result.output
    assert dotenv_values(global_dir / "keys.env")["AGENT_ADDRESS"]
    assert key_file.read_bytes() == original
    if os.name != "nt":
        assert (global_dir / "keys.env").stat().st_mode & 0o777 == 0o600
    assert list(work.iterdir()) == []


@pytest.mark.parametrize("target_kind", ["dot", "relative", "absolute"])
def test_explicit_path_initializes_only_that_project(setup_init, target_kind):
    runner, work, _, _ = setup_init
    target = work if target_kind == "dot" else work / "project with spaces"
    target.mkdir(exist_ok=True)
    argument = "./" if target_kind == "dot" else str(target if target_kind == "absolute" else target.name)

    result = runner.invoke(app, ["init", argument, "--yes", "--template", "co-ai"])

    assert result.exit_code == 0, result.output
    assert (target / ".co" / "host.yaml").is_file()
    assert (target / ".env").is_file()
    assert (target / "agent.py").is_file()
    assert len(list((target / ".co" / "docs").rglob("*.md"))) > 50
    assert Path.cwd() == work
    if target != work:
        assert not (work / ".env").exists()
        assert not (work / ".co").exists()


@pytest.mark.parametrize("flags", [["--template", "co-ai"], ["--force"], ["--description", "an agent"]])
def test_project_flags_require_a_path_before_any_write(setup_init, flags):
    runner, work, global_dir, auth = setup_init

    result = runner.invoke(app, ["init", "--yes", *flags])

    assert result.exit_code == 2
    assert "co init ./" in result.output
    assert list(work.iterdir()) == []
    assert not global_dir.exists()
    auth.assert_not_called()


@pytest.mark.parametrize("kind", ["file", "missing"])
def test_invalid_path_fails_without_initialization(setup_init, kind):
    runner, work, global_dir, auth = setup_init
    target = work / kind
    if kind == "file":
        target.write_text("keep me")

    result = runner.invoke(app, ["init", str(target), "--yes"])

    assert result.exit_code == 2
    assert not global_dir.exists()
    assert not (work / ".co").exists()
    auth.assert_not_called()


def test_help_explains_global_and_project_modes(setup_init):
    runner, _, _, auth = setup_init

    result = runner.invoke(app, ["init", "--help"])

    assert result.exit_code == 0
    assert "keys.env" in result.output
    assert "co init ./" in result.output
    auth.assert_not_called()
