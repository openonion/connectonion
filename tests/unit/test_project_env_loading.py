"""Startup and CLI loaders must use the same project boundary as identity."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.fixture
def env_project(tmp_path):
    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    (home / ".co" / "keys.env").write_text(
        "CO_TEST_KEY=global\nCO_TEST_GLOBAL=fallback\n", encoding="utf-8"
    )
    project = home / "project"
    (project / ".co").mkdir(parents=True)
    (project / ".env").write_text("CO_TEST_KEY=project\n", encoding="utf-8")
    nested = project / "src"
    nested.mkdir()
    (nested / ".env").write_text(
        "CO_TEST_KEY=nested\nCO_TEST_NESTED=unexpected\n", encoding="utf-8"
    )
    return home, project, nested


def _probe(home, cwd, entry, extra=None):
    env = {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
    }
    env.update(extra or {})
    code = (
        f"import {entry}\n"
        "import json, os\n"
        "print(json.dumps({k: os.getenv(k) for k in "
        "['CO_TEST_KEY', 'CO_TEST_GLOBAL', 'CO_TEST_NESTED']}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=cwd, env=env,
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("entry", ["connectonion", "connectonion.cli.main"])
def test_nested_startup_uses_project_env_not_nested_env(env_project, entry):
    home, project, nested = env_project
    expected = {"CO_TEST_KEY": "project", "CO_TEST_GLOBAL": "fallback", "CO_TEST_NESTED": None}
    assert _probe(home, project, entry) == expected
    assert _probe(home, nested, entry) == expected


@pytest.mark.parametrize("entry", ["connectonion", "connectonion.cli.main"])
def test_explicit_process_env_wins(env_project, entry):
    home, _, nested = env_project
    assert _probe(home, nested, entry, {"CO_TEST_KEY": "shell"}) == {
        "CO_TEST_KEY": "shell", "CO_TEST_GLOBAL": "fallback", "CO_TEST_NESTED": None,
    }


def test_missing_project_env_does_not_load_nested_env(env_project):
    home, project, nested = env_project
    (project / ".env").unlink()
    assert _probe(home, nested, "connectonion.cli.main") == {
        "CO_TEST_KEY": "global", "CO_TEST_GLOBAL": "fallback", "CO_TEST_NESTED": None,
    }


def test_home_dotenv_is_not_a_parent_project(env_project):
    home, _, _ = env_project
    (home / ".env").write_text("CO_TEST_KEY=home\n", encoding="utf-8")
    unrelated = home / "unrelated"
    unrelated.mkdir()
    assert _probe(home, unrelated, "connectonion.cli.main")["CO_TEST_KEY"] == "global"


def test_nearest_nested_project_owns_its_environment(env_project):
    home, _, nested = env_project
    (nested / ".co").mkdir()
    assert _probe(home, nested, "connectonion.cli.main")["CO_TEST_KEY"] == "nested"


@pytest.mark.parametrize("marker", ["directory", "worktree-file"])
def test_dotenv_does_not_cross_another_repository(env_project, marker):
    home, _, nested = env_project
    if marker == "directory":
        (nested / ".git").mkdir()
    else:
        (nested / ".git").write_text("gitdir: unused\n", encoding="utf-8")
    assert _probe(home, nested, "connectonion") == {
        "CO_TEST_KEY": "nested", "CO_TEST_GLOBAL": "fallback", "CO_TEST_NESTED": "unexpected",
    }


@pytest.mark.parametrize("module,loader", [
    ("gmail_commands", "_gmail"),
    ("outlook_commands", "_outlook"),
    ("gdrive_commands", "_gdrive"),
    ("synology_commands", "_syno"),
])
def test_integration_reload_uses_project_root(env_project, monkeypatch, module, loader):
    from importlib import import_module
    import dotenv

    home, project, nested = env_project
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(nested)
    command = import_module(f"connectonion.cli.commands.{module}")
    loaded = []

    class StopAfterEnv(Exception):
        pass

    def record(path, *args, **kwargs):
        loaded.append(Path(path).resolve())
        if len(loaded) == 2:
            raise StopAfterEnv

    monkeypatch.setattr(dotenv, "load_dotenv", record)
    with pytest.raises(StopAfterEnv):
        getattr(command, loader)()
    assert loaded == [project / ".env", home / ".co" / "keys.env"]
