"""Tests for co skills command handlers."""

import json
from pathlib import Path

import pytest

from connectonion.cli.commands import skills_commands as skills


def _write_skill(root: Path, dirname: str, name: str, description: str) -> None:
    skill_dir = root / dirname
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\nBody\n",
        encoding="utf-8",
    )


@pytest.fixture
def isolated_skills_home(tmp_path, monkeypatch):
    co_home = tmp_path / ".co"
    skills_dir = co_home / "skills"
    agent_json = co_home / "agent.json"

    monkeypatch.setattr(skills, "CO_HOME", co_home)
    monkeypatch.setattr(skills, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(skills, "INDEX_FILE", skills_dir / "index.json")
    monkeypatch.setattr(skills, "AGENT_JSON", agent_json)

    skills_dir.mkdir(parents=True)
    agent_json.write_text(
        json.dumps(
            {
                "address": "0xabc",
                "alias": "tester",
                "name": "tester",
                "bio": "Test agent",
                "skills": [],
                "version": "v0.1.0",
            }
        ),
        encoding="utf-8",
    )

    return co_home


def test_manifest_defaults_to_agent_json_with_publish_false(isolated_skills_home):
    _write_skill(skills.SKILLS_DIR, "alpha", "alpha", "Alpha skill")
    _write_skill(skills.SKILLS_DIR, "beta", "beta", "Beta skill")

    skills.handle_skills_manifest()

    profile = json.loads(skills.AGENT_JSON.read_text(encoding="utf-8"))
    assert profile["skills"] == [
        {"name": "alpha", "description": "Alpha skill", "publish": False},
        {"name": "beta", "description": "Beta skill", "publish": False},
    ]


def test_manifest_preserves_existing_publish_flags(isolated_skills_home):
    _write_skill(skills.SKILLS_DIR, "alpha", "alpha", "Alpha skill")
    _write_skill(skills.SKILLS_DIR, "beta", "beta", "Beta skill")
    profile = json.loads(skills.AGENT_JSON.read_text(encoding="utf-8"))
    profile["skills"] = [
        {"name": "alpha", "description": "Old alpha", "publish": True},
    ]
    profile["signature"] = "stale-signature"
    profile["signer"] = "stale-signer"
    skills.AGENT_JSON.write_text(json.dumps(profile), encoding="utf-8")

    skills.handle_skills_manifest()

    updated = json.loads(skills.AGENT_JSON.read_text(encoding="utf-8"))
    assert updated["skills"] == [
        {"name": "alpha", "description": "Alpha skill", "publish": True},
        {"name": "beta", "description": "Beta skill", "publish": False},
    ]
    assert "signature" not in updated
    assert "signer" not in updated


def test_manifest_custom_out_writes_standalone_json(isolated_skills_home, tmp_path):
    _write_skill(skills.SKILLS_DIR, "alpha", "alpha", "Alpha skill")
    out = tmp_path / "skills.json"

    skills.handle_skills_manifest(out=str(out))

    assert json.loads(out.read_text(encoding="utf-8")) == [
        {"name": "alpha", "description": "Alpha skill", "publish": False},
    ]
    profile = json.loads(skills.AGENT_JSON.read_text(encoding="utf-8"))
    assert profile["skills"] == []


def test_manifest_requires_agent_json_by_default(isolated_skills_home):
    skills.AGENT_JSON.unlink()

    with pytest.raises(SystemExit):
        skills.handle_skills_manifest()
