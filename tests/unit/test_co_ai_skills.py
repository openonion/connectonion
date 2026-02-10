"""Tests for co_ai skills loader and tool."""

from pathlib import Path

from connectonion.cli.co_ai.skills.loader import (
    parse_skill_frontmatter,
    discover_skills,
    load_skills,
    get_skills_for_prompt,
    SKILLS_REGISTRY,
)
from connectonion.cli.co_ai.skills.tool import skill


def test_parse_skill_frontmatter():
    content = "---\nname: foo\ndescription: bar\n---\n# Title\nBody"
    meta = parse_skill_frontmatter(content)
    assert meta["name"] == "foo"
    assert meta["description"] == "bar"


def test_load_and_use_skills(tmp_path, monkeypatch):
    # Create a project-level skill
    skill_dir = tmp_path / ".co" / "skills" / "alpha"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: Alpha skill\n---\nAlpha body",
        encoding="utf-8",
    )

    # Clear registry and load
    SKILLS_REGISTRY.clear()
    skills = load_skills(base_path=Path(tmp_path))
    assert "alpha" in skills

    prompt = get_skills_for_prompt()
    assert "<skill name=\"alpha\"" in prompt

    # Use skill tool (ensure cwd points to tmp_path so loader finds skill)
    monkeypatch.chdir(tmp_path)
    SKILLS_REGISTRY.clear()
    content = skill("alpha")
    assert "Alpha body" in content

    missing = skill("missing")
    assert "not found" in missing


def test_discover_skills_single_file(tmp_path):
    skills_dir = tmp_path / ".co" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "beta.md").write_text("Beta skill", encoding="utf-8")

    found = discover_skills(base_path=Path(tmp_path))
    names = {s.name for s in found}
    assert "beta" in names
