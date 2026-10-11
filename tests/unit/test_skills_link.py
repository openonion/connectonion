"""Unit tests for `co skills link` — publishing bundled skills to Claude and Codex.

Tests cover:
- every bundled skill is linked into every target
- idempotence (re-running reports "already linked", does not duplicate)
- a directory the user owns is never silently destroyed
- --force replaces it
- a stale symlink pointing elsewhere is repointed
- the packaged skills all carry the frontmatter the tools read
"""

import os
from pathlib import Path

import pytest

from connectonion.cli.commands import skills_commands
from connectonion.cli.commands.skills_commands import (
    BUNDLED_SKILLS,
    handle_skills_link,
    parse_frontmatter,
)


@pytest.fixture
def targets():
    """Both tools installed in the per-test HOME conftest provides."""
    roots = [root for _, root in skills_commands.link_targets()]
    for root in roots:
        root.parent.mkdir()
    return roots


def bundled_names():
    return sorted(d.name for d in BUNDLED_SKILLS.iterdir() if d.is_dir() and (d / "SKILL.md").exists())


class TestBundledSkills:
    """The skills that ship with the package."""

    def test_every_bundled_skill_has_frontmatter_name_and_description(self):
        """Both fields are what an agent matches on to decide to load the skill."""
        for name in bundled_names():
            fm = parse_frontmatter((BUNDLED_SKILLS / name / "SKILL.md").read_text(encoding="utf-8"))
            assert fm.get("name"), f"{name}: missing frontmatter name"
            assert fm.get("description"), f"{name}: missing frontmatter description"

    def test_frontmatter_name_matches_directory(self):
        for name in bundled_names():
            fm = parse_frontmatter((BUNDLED_SKILLS / name / "SKILL.md").read_text(encoding="utf-8"))
            assert fm["name"] == name

    def test_mail_and_drive_skill_ships(self):
        assert "co-mail-and-drive" in bundled_names()


class TestSkillsLink:

    def test_links_every_skill_into_every_target(self, targets):
        handle_skills_link()

        for root in targets:
            for name in bundled_names():
                linked = root / name
                assert linked.exists(), f"{name} missing from {root}"
                assert (linked / "SKILL.md").exists()

    def test_brief_is_one_line_per_coding_agent_naming_what_it_kept(self, targets, capsys):
        """co init uses brief: a row per skill pushed the useful lines off the screen."""
        (targets[1] / bundled_names()[0]).mkdir(parents=True)          # one the user owns in codex
        handle_skills_link(brief=True)
        out = " ".join(capsys.readouterr().out.split())                  # rich wraps long paths
        n = len(bundled_names())
        assert out.startswith(f"✓ claude: {n} co skills in ")
        assert f"✓ codex: {n - 1} co skills in " in out and f"1 of your own kept: {bundled_names()[0]}" in out
        assert out.count("✓") == 2 and "Linking" not in out              # no per-skill table

    def test_is_idempotent(self, targets, capsys):
        handle_skills_link()
        capsys.readouterr()
        handle_skills_link()

        assert "already linked" in capsys.readouterr().out
        for root in targets:
            assert len(list(root.iterdir())) == len(bundled_names())

    def test_never_destroys_a_directory_the_user_owns(self, targets, capsys):
        """A real directory of that name is the user's own skill, not ours."""
        mine = targets[0] / "co-browser"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("my own version")

        handle_skills_link()

        assert (mine / "SKILL.md").read_text() == "my own version"
        assert "skipped" in capsys.readouterr().out

    def test_force_replaces_a_user_directory(self, targets):
        mine = targets[0] / "co-browser"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("my own version")

        handle_skills_link(force=True)

        assert (mine / "SKILL.md").read_text() != "my own version"

    @pytest.mark.skipif(os.name == "nt", reason="symlinks need privilege on Windows")
    def test_repoints_a_symlink_aimed_somewhere_else(self, targets, tmp_path):
        """An upgrade that moves the package must not leave a dangling link."""
        stale_source = tmp_path / "old-install" / "co-browser"
        stale_source.mkdir(parents=True)
        (stale_source / "SKILL.md").write_text("stale")
        link = targets[0] / "co-browser"
        link.parent.mkdir(parents=True)
        link.symlink_to(stale_source, target_is_directory=True)

        handle_skills_link()

        assert link.resolve() == (BUNDLED_SKILLS / "co-browser").resolve()

    def test_reports_both_targets(self, targets, capsys):
        handle_skills_link()

        output = capsys.readouterr().out
        assert "claude" in output
        assert "codex" in output


class TestCoBrowserSkillMatchesBehaviour:
    """The skill is what Claude Code and Codex actually read.

    It drifted once already: it told agents "a crashed agent's claim expires on
    its own; open your own tab rather than closing theirs" — the opposite of
    what the daemon now does once a declared window elapses. A skill that
    contradicts the tool is worse than no skill.
    """

    def _skill(self):
        return (BUNDLED_SKILLS / "co-browser" / "SKILL.md").read_text(encoding="utf-8")

    def test_teaches_declaring_how_long_the_tab_is_needed(self):
        text = self._skill()
        assert "--needs" in text

    def test_does_not_still_say_never_close_another_agents_tab(self):
        """True inside the declared window, wrong once it has passed."""
        text = self._skill()
        assert "rather than closing theirs" not in text
        assert "expires on its own" not in text

    def test_points_agents_at_the_board_before_they_act(self):
        text = self._skill()
        assert "tab ls" in text


def test_a_tool_that_is_not_installed_is_never_created(capsys):
    """co init runs this; creating ~/.codex would make Codex look installed."""
    claude = Path.home() / ".claude"
    claude.mkdir()
    handle_skills_link()
    assert (claude / "skills" / "co-browser" / "SKILL.md").exists()
    assert not (Path.home() / ".codex").exists()
    assert "no .codex, skipped" in capsys.readouterr().out
