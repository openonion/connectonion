"""A fresh ``co ai`` gets product workflows, not our release toolbox."""

from pathlib import Path


EXPECTED_DEFAULTS = {
    "dashboard",
    "topup",
    "install-connectonion",
    "co-browser",
    "co-mail-and-drive",
}
CONTRIBUTOR_SKILLS = {"commit", "review-pr", "ship-feature"}


def test_both_skill_readers_expose_the_same_defaults(tmp_path, monkeypatch):
    from connectonion.cli.co_ai.skills.loader import discover_skills
    from connectonion.useful_plugins.skills import _discover_all_skills

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    project = tmp_path / "project"
    project.mkdir()

    prompt_names = {skill.name for skill in discover_skills(project)}
    slash_names = {
        skill.name
        for skill in _discover_all_skills(
            co_dir=project / ".co", project_dir=project
        )
    }

    assert prompt_names == EXPECTED_DEFAULTS
    assert slash_names == EXPECTED_DEFAULTS
    assert not prompt_names & CONTRIBUTOR_SKILLS


def test_default_library_skills_have_one_canonical_body():
    from connectonion.skills_catalog import default_skill_path

    for name in EXPECTED_DEFAULTS - {"dashboard", "topup"}:
        path = default_skill_path(name)
        assert path is not None
        assert "useful_skills" in path.parts


def test_defaults_do_not_auto_approve_tools():
    from connectonion.skills_catalog import default_skill_files
    from connectonion.useful_plugins.skills import _parse_skill_content

    for path in default_skill_files():
        frontmatter, _ = _parse_skill_content(path.read_text(encoding="utf-8"))
        assert not frontmatter.get("tools"), path


def test_release_skill_is_neither_default_nor_auto_approved():
    from connectonion.skills_catalog import default_skill_path, useful_skills_dir
    from connectonion.useful_plugins.skills import _parse_skill_content

    assert default_skill_path("ship-feature") is None
    body = (useful_skills_dir() / "ship-feature" / "SKILL.md").read_text(encoding="utf-8")
    frontmatter, _ = _parse_skill_content(body)
    assert not frontmatter.get("tools")
