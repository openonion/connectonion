"""Auth and diagnostic readers honor exactly the same explicit identity choice."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from connectonion import address, environment
from connectonion.cli.commands import auth_commands, keys_commands, status_commands
from connectonion.cli.main import app
from connectonion.project import project_identity


@pytest.fixture
def identities(tmp_path, monkeypatch):
    global_dir = tmp_path / "global"
    project = tmp_path / "project"
    nested = project / "src"
    nested.mkdir(parents=True)
    global_id, project_id = address.generate(), address.generate()
    address.save(global_id, global_dir)
    address.save(project_id, project / ".co")
    (project / ".env").write_text("PROJECT_ONLY=yes\n")
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(global_dir))
    monkeypatch.chdir(nested)
    return global_dir, project, global_id, project_id


@pytest.mark.parametrize("explicit", [False, True])
def test_auth_signs_and_writes_exactly_selected_source(identities, monkeypatch, explicit):
    global_dir, project, global_id, project_id = identities
    response = Mock(status_code=200)
    response.json.return_value = {"token": "synthetic-broker-key", "user": {"balance_usd": 1}}
    post = Mock(return_value=response)
    monkeypatch.setattr(auth_commands.requests, "post", post)
    args = ["--env-file", str(project / ".env")] if explicit else []
    result = CliRunner().invoke(app, args + ["auth"])
    assert result.exit_code == 0, result.output
    assert post.call_args.kwargs["json"]["public_key"] == (project_id if explicit else global_id)["address"]
    chosen = project / ".env" if explicit else global_dir / "keys.env"
    assert "OPENONION_API_KEY=synthetic-broker-key" in chosen.read_text()
    if explicit:
        assert not (global_dir / "keys.env").exists()
    else:
        assert (project / ".env").read_text() == "PROJECT_ONLY=yes\n"


@pytest.mark.parametrize("explicit", [False, True])
def test_identity_readers_agree_across_directories(identities, monkeypatch, explicit):
    global_dir, project, global_id, project_id = identities
    environment.select_env_file(project / ".env" if explicit else None)
    for cwd in (project, project / "src", global_dir.parent):
        monkeypatch.chdir(cwd)
        assert project_identity()["address"] == (project_id if explicit else global_id)["address"]
        assert keys_commands._find_co_dir() == (project / ".co" if explicit else global_dir)


def test_diagnostics_never_borrow_file_metadata_for_a_process_account(identities, monkeypatch):
    global_dir, project, *_ = identities
    (global_dir / "keys.env").write_text("GOOGLE_EMAIL=global@example.test\nGOOGLE_SCOPES=gmail.readonly\nGOOGLE_ACCESS_TOKEN=global-access\n")
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "process-access")
    environment.select_env_file(None)
    rows = keys_commands._load_env_vars()
    assert rows["GOOGLE_ACCESS_TOKEN"] == "process-access"
    assert rows["GOOGLE_EMAIL"] is None
    google = next(row for row in status_commands._oauth_rows() if row["provider"] == "Google OAuth")
    assert google["status"] == "incomplete (scopes missing)"
    assert google["source"] == "process environment"


def test_bare_init_rejects_a_project_env_selector(identities, monkeypatch):
    _, project, *_ = identities
    monkeypatch.setattr(auth_commands.requests, "post", lambda *a, **k: pytest.fail("No auth before selector validation"))
    result = CliRunner().invoke(app, ["--env-file", str(project / ".env"), "init"])
    assert result.exit_code == 2
    assert "co init" in result.output
    assert (project / ".env").read_text() == "PROJECT_ONLY=yes\n"
