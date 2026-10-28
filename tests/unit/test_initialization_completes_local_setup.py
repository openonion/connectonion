"""Every onboarding entry point leaves the same usable local integration."""

import json
import os
from pathlib import Path

import pytest
from dotenv import dotenv_values
from typer.testing import CliRunner

from connectonion.cli.commands import agent_index, auth_commands, create, init
from connectonion.cli.commands.project_cmd_lib import ensure_global_config
from connectonion.cli.main import app


@pytest.fixture
def onboarding(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    for module in (init, create, auth_commands):
        monkeypatch.setattr(module, "authenticate", lambda *a, **k: False)
    monkeypatch.setattr(init, "show_progress", lambda *a: None)
    for module in (init, create):
        monkeypatch.setattr(module, "check_environment_for_api_keys", lambda: None)
    for tool in (".codex", ".claude"):
        (Path.home() / tool).mkdir()
    return CliRunner(), work, Path.home() / ".co"


ENTRY_POINTS = [
    ["init", "--yes"],
    ["init", "./", "--yes"],
    ["create", "demo", "--yes"],
    ["setup", "--no-skills"],
]


@pytest.mark.parametrize("existing_identity", [False, True])
@pytest.mark.parametrize("command", ENTRY_POINTS)
def test_every_entry_point_completes_local_setup(onboarding, command, existing_identity):
    from connectonion import __version__
    from connectonion.cli.commands.skills_commands import BUNDLED_SKILLS

    runner, _, root = onboarding
    # An identity alone must not short-circuit the rest of onboarding.
    if existing_identity:
        ensure_global_config()

    result = runner.invoke(app, command)

    assert result.exit_code == 0, result.output
    profile = json.loads((root / "agent.json").read_text())
    assert profile["address"] == dotenv_values(root / "keys.env")["AGENT_ADDRESS"]
    for folder, instructions in ((".codex", "AGENTS.md"), (".claude", "CLAUDE.md")):
        tool = Path.home() / folder
        for bundled in BUNDLED_SKILLS.iterdir():
            if (bundled / "SKILL.md").is_file():
                assert (tool / "skills" / bundled.name / "SKILL.md").read_bytes() == (bundled / "SKILL.md").read_bytes()
        assert agent_index.stamp(tool / instructions) == __version__


def test_setup_bootstraps_in_process_and_repairs_missing_env(onboarding, monkeypatch):
    import subprocess

    runner, _, root = onboarding
    def no_child(*args, **kwargs):
        pytest.fail("setup invoked an installed CLI instead of its own initialization")
    monkeypatch.setattr(subprocess, "run", no_child)

    result = runner.invoke(app, ["setup", "--no-skills"])
    assert result.exit_code == 0, result.output
    key = (root / "keys" / "agent.key").read_bytes()
    (root / "keys.env").unlink()

    result = runner.invoke(app, ["setup", "--no-skills"])
    assert result.exit_code == 0, result.output
    assert (root / "keys" / "agent.key").read_bytes() == key
    assert dotenv_values(root / "keys.env")["AGENT_ADDRESS"]


@pytest.mark.parametrize("command", ENTRY_POINTS)
def test_profile_and_links_follow_the_current_home(onboarding, monkeypatch, command):
    runner, _, default_root = onboarding
    selected = default_root.parent / "selected-config"
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(selected))

    result = runner.invoke(app, command)

    assert result.exit_code == 0, result.output
    assert (selected / "keys" / "agent.key").is_file()
    assert (selected / "agent.json").is_file()
    assert not default_root.exists()


def test_reinitialization_repairs_omissions_and_preserves_edits(onboarding):
    runner, work, root = onboarding
    first = runner.invoke(app, ["init", "./", "--yes"])
    assert first.exit_code == 0, first.output
    key = (root / "keys" / "agent.key").read_bytes()
    invite = dotenv_values(work / ".env")["CO_INVITE_CODE"]
    profile = root / "agent.json"
    profile.write_text('{"alias": "my-edited-profile", "bio": "keep this"}\n')
    codex = Path.home() / ".codex"
    instructions = codex / "AGENTS.md"
    instructions.write_text("My own instructions.\n")
    skill = codex / "skills" / "co-browser"
    if skill.is_symlink():
        skill.unlink()
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text("My own browser skill.\n")
    missing = codex / "skills" / "co-linear"
    if missing.is_symlink():
        missing.unlink()
    else:
        import shutil
        shutil.rmtree(missing)

    for _ in range(2):
        result = runner.invoke(app, ["init", "./", "--yes", "--force"])
        assert result.exit_code == 0, result.output

    assert (root / "keys" / "agent.key").read_bytes() == key
    assert dotenv_values(work / ".env")["CO_INVITE_CODE"] == invite
    assert json.loads(profile.read_text())["alias"] == "my-edited-profile"
    assert (skill / "SKILL.md").read_text() == "My own browser skill.\n"
    assert instructions.read_text().startswith("My own instructions.\n")
    assert instructions.read_text().count("<!-- co:begin ") == 1
    assert (codex / "skills" / "co-linear" / "SKILL.md").is_file()


def test_incomplete_profile_is_repaired_without_losing_custom_fields(onboarding):
    runner, _, root = onboarding
    ensure_global_config()
    profile = root / "agent.json"
    profile.write_text('{"alias":"custom","extra":"keep"}')
    result = runner.invoke(app, ["init", "--yes"])
    assert result.exit_code == 0, result.output
    saved = json.loads(profile.read_text())
    assert saved["alias"] == saved["name"] == "custom"
    assert saved["extra"] == "keep" and saved["skills"] == [] and saved["address"]


@pytest.mark.parametrize("skills", [None, "bad", ["bad"], [{}], [{"name": ""}]])
def test_malformed_skill_metadata_is_preserved_with_an_actionable_error(onboarding, skills):
    runner, _, root = onboarding
    ensure_global_config()
    profile = root / "agent.json"
    original = json.dumps({"alias": "custom", "skills": skills})
    profile.write_text(original)
    result = runner.invoke(app, ["setup", "--no-skills", "--name", "updated"])
    assert result.exit_code != 0
    assert "skills must be a list" in str(result.exception)
    assert profile.read_text() == original


@pytest.mark.parametrize("skip_import", [False, True])
def test_setup_can_customize_the_profile_created_by_init(onboarding, skip_import):
    runner, _, root = onboarding
    runner.invoke(app, ["init", "--yes"])
    path = root / "agent.json"
    profile = json.loads(path.read_text())
    profile.update(skills=[{"name": "my-skill", "publish": True}], extra="keep",
                   signature="outdated", signer="old-signer")
    path.write_text(json.dumps(profile))

    flags = ["--no-skills"] if skip_import else []
    result = runner.invoke(app, ["setup", *flags, "--name", "my-agent", "--bio", "My work"])

    assert result.exit_code == 0, result.output
    edited = json.loads(path.read_text())
    assert edited["alias"] == edited["name"] == "my-agent"
    assert edited["bio"] == "My work"
    assert profile["skills"][0] in edited["skills"] and edited["extra"] == "keep"
    assert "signature" not in edited and "signer" not in edited


def test_full_setup_imports_into_the_selected_root_and_is_loadable(onboarding, monkeypatch):
    from connectonion.cli.co_ai.skills.loader import discover_skills
    from connectonion.useful_plugins.skills import _discover_all_skills, _load_skill

    runner, _, default_root = onboarding
    root = default_root.parent / "custom-library"
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(root))
    skill = Path.home() / ".claude" / "skills" / "my-fixture"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: my-fixture\ndescription: Test fixture\n---\nBody\n")

    for _ in range(2):
        result = runner.invoke(app, ["setup"])
        assert result.exit_code == 0, result.output

    assert (root / "skills" / "my-fixture" / "SKILL.md").is_file()
    assert (root / "skills" / "index.json").is_file()
    profile = json.loads((root / "agent.json").read_text())
    assert any(s["name"] == "my-fixture" and s["publish"] is False for s in profile["skills"])
    assert any(s.name == "my-fixture" and s.location == "user" for s in _discover_all_skills())
    assert Path(_load_skill("my-fixture")["path"]) == root / "skills" / "my-fixture" / "SKILL.md"
    assert any(s.name == "my-fixture" and s.path == root / "skills" / "my-fixture" / "SKILL.md"
               for s in discover_skills())
    assert not default_root.exists()
    preview = runner.invoke(app, ["announce", "--dry-run"])
    assert preview.exit_code == 0, preview.output


def test_later_installed_coding_agent_is_connected_on_rerun(onboarding):
    runner, _, root = onboarding
    codex = Path.home() / ".codex"
    codex.rmdir()
    first = runner.invoke(app, ["init", "--yes"])
    assert first.exit_code == 0, first.output
    assert not codex.exists()
    key = (root / "keys" / "agent.key").read_bytes()
    codex.mkdir()

    result = runner.invoke(app, ["init", "--yes"])

    assert result.exit_code == 0, result.output
    assert (codex / "skills" / "co-browser" / "SKILL.md").is_file()
    assert agent_index.stamp(codex / "AGENTS.md") is not None
    assert (root / "keys" / "agent.key").read_bytes() == key


def test_setup_reports_a_saved_token_without_printing_it(onboarding, monkeypatch):
    from connectonion.cli.commands.project_cmd_lib import upsert_env

    runner, _, root = onboarding
    ensure_global_config()
    upsert_env(root / "keys.env", {"OPENONION_API_KEY": "fixture-token-do-not-print"})
    monkeypatch.delenv("OPENONION_API_KEY", raising=False)

    result = runner.invoke(app, ["setup", "--no-skills"])

    assert result.exit_code == 0, result.output
    assert "present (not verified)" in result.output
    assert "fixture-token-do-not-print" not in result.output


def test_force_recreates_only_the_profile_and_backs_it_up(onboarding):
    runner, _, root = onboarding
    runner.invoke(app, ["init", "--yes"])
    path = root / "agent.json"
    original = path.read_bytes()
    key = (root / "keys" / "agent.key").read_bytes()
    skill = Path.home() / ".codex" / "skills" / "co-browser"
    if skill.is_symlink():
        skill.unlink()
    else:
        import shutil
        shutil.rmtree(skill)
    skill.mkdir()
    (skill / "SKILL.md").write_text("keep my skill")

    result = runner.invoke(app, ["setup", "--name", "new-profile", "--force", "--no-skills"])

    assert result.exit_code == 0, result.output
    assert path.with_suffix(".json.bak").read_bytes() == original
    assert json.loads(path.read_text())["alias"] == "new-profile"
    assert (root / "keys" / "agent.key").read_bytes() == key
    assert (skill / "SKILL.md").read_text() == "keep my skill"
    assert result.output.count("Next:") == 1


@pytest.mark.parametrize("broken", ["not-json", "[]"])
def test_init_reports_a_broken_existing_profile_without_replacing_it(onboarding, broken):
    runner, _, root = onboarding
    ensure_global_config()
    path = root / "agent.json"
    path.write_text(broken)

    result = runner.invoke(app, ["init", "--yes"])

    assert result.exit_code != 0
    assert path.read_text() == broken


@pytest.mark.skipif(os.name == "nt", reason="personal symlinks require Windows privilege")
@pytest.mark.parametrize("command", ENTRY_POINTS + [["setup", "--force", "--no-skills"]])
def test_a_valid_personal_skill_link_survives_initialization(onboarding, command):
    runner, work, _ = onboarding
    personal = work / "my-browser-skill"
    personal.mkdir()
    (personal / "SKILL.md").write_text("my custom browser")
    linked = Path.home() / ".codex" / "skills" / "co-browser"
    linked.parent.mkdir()
    linked.symlink_to(personal, target_is_directory=True)

    result = runner.invoke(app, command)

    assert result.exit_code == 0, result.output
    assert linked.is_symlink() and linked.resolve() == personal
    assert (linked / "SKILL.md").read_text() == "my custom browser"
