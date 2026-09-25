"""A refusal on the first run exits non-zero, and a finished `co init` names a step that works.

LLM-Note: Tests for connectonion/cli/commands/create.py, deploy_commands.py (through cli/main.py) and init.py

What it tests:
- `co create NAME` when NAME already exists prints the suggestion and exits 1 (1.8.8b9 exited 0)
- `co deploy` in a project with no agent.py says "Entrypoint not found" and exits 1 (1.8.8b9 exited 0)
- `co init ./` in an empty directory does not end with "co deploy" while there is nothing to deploy

A script or a coding agent reads the exit code, not the red text: exit 0 after
"exists" reads as "created", and the next command then runs in a project that
was never made.
"""

import re

from typer.testing import CliRunner

from connectonion.cli.main import app


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_create_into_an_existing_directory_exits_1(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("connectonion.cli.commands.create.authenticate", lambda *a, **k: True)
    (tmp_path / "my-agent").mkdir()

    result = CliRunner().invoke(app, ["create", "my-agent", "--yes"])

    assert result.exit_code == 1, result.output
    assert "co create my-agent-2" in _plain(result.output)


def test_deploy_without_the_entrypoint_exits_1(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".co").mkdir()
    (tmp_path / ".co" / "host.yaml").write_text("name: my-agent\nentrypoint: agent.py\n")

    result = CliRunner().invoke(app, ["deploy"])

    assert "Entrypoint not found: agent.py" in _plain(result.output)
    assert result.exit_code == 1


def test_init_in_an_empty_directory_says_what_to_create_before_deploy(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.cli.commands.init.authenticate", lambda *a, **k: True)
    project = tmp_path / "empty"
    project.mkdir()

    result = CliRunner().invoke(app, ["init", str(project), "--yes"])
    out = _plain(result.output)

    assert result.exit_code == 0, out
    assert not (project / "agent.py").exists()
    assert "Deploy it when it works" not in out
    assert "create agent.py" in out and "co init ./ --template co-ai --yes" in out


def test_an_existing_directory_is_refused_before_any_identity_or_account(tmp_path, monkeypatch):
    # Found capturing 1.8.8b10: on a first run the "exists" refusal came after
    # a keypair was generated and an OpenOnion account signed up.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("connectonion.cli.commands.create.authenticate",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("signed up")))
    monkeypatch.setattr("connectonion.cli.commands.create.ensure_global_config",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("made an identity")))
    (tmp_path / "my-agent").mkdir()

    result = CliRunner().invoke(app, ["create", "my-agent", "--yes"])

    assert result.exit_code == 1, result.output
    assert "co create my-agent-2" in _plain(result.output)


def test_create_dot_suggests_a_real_name_not_dot_dash_2(tmp_path, monkeypatch):
    # 1.8.8b11: `co create .` in a non-empty folder said "Try: co create .-2".
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("already here")
    (tmp_path / "my-agent").mkdir()

    result = CliRunner().invoke(app, ["create", ".", "--yes"])
    out = _plain(result.output)

    assert result.exit_code == 1, out
    assert ".-2" not in out
    assert "co create my-agent-2" in out and "co init ./ --template co-ai --yes" in out
