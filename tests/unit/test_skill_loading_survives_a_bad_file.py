"""One unreadable skill must not take the whole CLI down with it.

`load_skills()` runs inside `create_agent()`, before the CLI is usable — so an
exception escaping discovery is not "that skill failed", it is "co ai does not
start", with nothing said about which file caused it.
"""

import sys

import pytest

import connectonion.cli.co_ai.skills.loader as loader

skills_plugin = sys.modules["connectonion.useful_plugins.skills"]


def _write_skill(root, name, body="---\nname: %s\ndescription: works\n---\ndo it\n"):
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(body % name if "%s" in body else body, encoding="utf-8")
    return d


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project holding one good skill, with $HOME redirected away from the
    developer's own ~/.co and ~/.claude so the test sees only what it created."""
    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: home))

    project = tmp_path / "project"
    _write_skill(project / ".co" / "skills", "good")
    return project


class TestCoAiLoader:
    def test_a_non_utf8_skill_is_skipped_and_the_others_still_load(self, project, capsys):
        """A compiled asset copied in by accident, or smart quotes saved as
        Windows-1252, is enough to produce this."""
        broken = project / ".co" / "skills" / "broken"
        broken.mkdir()
        (broken / "SKILL.md").write_bytes(b"---\nname: broken\ndesc: \xff\xfe binary\n---\n")

        found = loader.discover_skills(project)

        assert "good" in {s.name for s in found}, "the healthy skill must still load"
        assert "broken" not in {s.name for s in found}

    def test_it_says_which_file_was_skipped(self, project, capsys):
        """Skipping silently trades a crash for a mystery: the agent behaves
        differently and nothing points at the cause."""
        broken = project / ".co" / "skills" / "broken"
        broken.mkdir()
        (broken / "SKILL.md").write_bytes(b"\xff\xfe\x00 not text at all")

        loader.discover_skills(project)

        assert "broken" in capsys.readouterr().out

    def test_a_directory_that_cannot_be_read_does_not_abort_discovery(self, project):
        """SKILL.md present but unreadable — a permission or a race, not a
        malformed file. Same requirement: skip it, keep going."""
        weird = project / ".co" / "skills" / "weird"
        weird.mkdir()
        (weird / "SKILL.md").mkdir()          # a directory where a file is expected

        found = loader.discover_skills(project)

        assert "good" in {s.name for s in found}


class TestAgentSkillDiscovery:
    """The same loop exists a second time in useful_plugins/skills.py, and the
    issue reports both. A fix to one is not a fix."""

    def test_a_non_utf8_skill_is_skipped_and_the_others_still_load(self, project):
        broken = project / ".co" / "skills" / "broken"
        broken.mkdir()
        (broken / "SKILL.md").write_bytes(b"---\nname: broken\n\xff\xfe\n---\n")

        found = skills_plugin._discover_all_skills(project_dir=project)

        assert "good" in {s.name for s in found}
        assert "broken" not in {s.name for s in found}

    def test_a_broken_skill_does_not_shadow_a_working_one_of_the_same_name(self, tmp_path, monkeypatch):
        """Discovery takes the first of each name and skips the rest, so a broken
        file must not claim the name on its way out — otherwise a corrupted
        project skill silently disables the user-level one it was overriding,
        which is a harder failure to explain than either alone."""
        home = tmp_path / "home"
        _write_skill(home / ".co" / "skills", "notes")           # the fallback, healthy
        monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: home))

        project = tmp_path / "project"
        broken = project / ".co" / "skills" / "notes"            # higher priority, broken
        broken.mkdir(parents=True)
        (broken / "SKILL.md").write_bytes(b"\xff\xfe not text")

        found = skills_plugin._discover_all_skills(project_dir=project)

        assert "notes" in {s.name for s in found}
        assert next(s for s in found if s.name == "notes").location == "user"
