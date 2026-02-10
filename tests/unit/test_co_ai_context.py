"""Tests for project context loading."""

from pathlib import Path

from connectonion.cli.co_ai.context import load_project_context
from connectonion.cli.co_ai.skills import loader as skills_loader


def test_load_project_context_includes_files(tmp_path, monkeypatch):
    base = tmp_path

    (base / ".co").mkdir()
    (base / ".co" / "OO.md").write_text("OO instructions", encoding="utf-8")
    (base / "CLAUDE.md").write_text("Claude notes", encoding="utf-8")
    (base / "README.md").write_text("Readme text", encoding="utf-8")

    # Add a skill
    skill_dir = base / ".co" / "skills" / "skill-one"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: skill-one\ndescription: Test skill\n---\nBody", encoding="utf-8")

    # Reset registry to avoid leakage
    skills_loader.SKILLS_REGISTRY.clear()

    ctx = load_project_context(base_path=Path(base))

    assert "Project Instructions (OO.md)" in ctx
    assert "Additional Instructions (CLAUDE.md)" in ctx
    assert "Project Overview (README.md)" in ctx
    assert "Available Skills" in ctx
    assert "skill-one" in ctx
    assert "Working Directory" in ctx
