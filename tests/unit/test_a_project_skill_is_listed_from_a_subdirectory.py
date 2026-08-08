"""A project skill is loadable by name and never listed, one directory down.

#663 gave `_get_skill_paths` the walk-up that #660/#661 established, and left
`_skill_search_paths` — the other half of the same module — resolving against
the bare cwd:

    base = project_dir or (co_dir.parent if co_dir else Path.cwd())
    co_base = co_dir or (base / '.co')

So the two disagree. Measured on a project holding `.co/skills/secret-handshake`,
from a subdirectory of it:

    _discover_all_skills() sees it : False
    _load_skill() finds it         : True
    project path searched          : <project>/sub/.co/skills

The loader walks up and the discoverer does not. A skill that exists and can be
loaded by name is never *listed*, so the model is never told it is there — and a
skill the model does not know about is a skill that does not work.

Visible on the real command. `co ai "handshake"` in a project whose skill answers
with a passphrase:

    from the project root   ZEBRA-9317
    from a subdirectory     "Handshake acknowledged. How can I help you today?"

This is the same half-fix shape the loop keeps turning up, and this time it is
mine: #663 changed the function I was looking at rather than the concept.
"""

from pathlib import Path

import pytest


@pytest.fixture
def project(tmp_path):
    skill = tmp_path / "project" / ".co" / "skills" / "secret-handshake"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: secret-handshake\ndescription: says a passphrase\n---\n\nZEBRA-9317\n"
    )
    (tmp_path / "project" / ".claude" / "skills" / "claude-one").mkdir(parents=True)
    (tmp_path / "project" / ".claude" / "skills" / "claude-one" / "SKILL.md").write_text(
        "---\nname: claude-one\ndescription: d\n---\n\nGo.\n"
    )
    (tmp_path / "project" / "sub" / "deeper").mkdir(parents=True)
    return tmp_path / "project"


def _names(**kw):
    from connectonion.useful_plugins.skills import _discover_all_skills

    return [s.name for s in _discover_all_skills(**kw)]


class TestFromASubdirectory:

    @pytest.mark.parametrize("depth", ["sub", "sub/deeper"])
    def test_the_project_skill_is_listed(self, project, monkeypatch, depth):
        monkeypatch.chdir(project / depth)

        assert "secret-handshake" in _names()

    def test_the_claude_project_skill_is_listed_too(self, project, monkeypatch):
        """`.claude/skills` is found the same way — by the project, not the cwd."""
        monkeypatch.chdir(project / "sub")

        assert "claude-one" in _names()

    def test_the_two_halves_agree(self, project, monkeypatch):
        """The property that was violated: loadable and listed are the same set."""
        from connectonion.useful_plugins.skills import _load_skill

        monkeypatch.chdir(project / "sub")

        assert ("secret-handshake" in _names()) == (_load_skill("secret-handshake") is not None)


class TestFromTheProjectRoot:
    """Unchanged — this already worked."""

    def test_it_is_listed(self, project, monkeypatch):
        monkeypatch.chdir(project)

        assert "secret-handshake" in _names()


class TestWhatMustNotChange:

    def test_an_explicit_co_dir_still_wins(self, project, tmp_path, monkeypatch):
        other = tmp_path / "other" / ".co" / "skills" / "elsewhere"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("---\nname: elsewhere\ndescription: d\n---\n\nGo.\n")
        monkeypatch.chdir(project)

        assert "elsewhere" in _names(co_dir=tmp_path / "other" / ".co")

    def test_an_explicit_project_dir_still_wins(self, project, tmp_path, monkeypatch):
        other = tmp_path / "other2" / ".co" / "skills" / "elsewhere2"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("---\nname: elsewhere2\ndescription: d\n---\n\nGo.\n")
        monkeypatch.chdir(project)

        assert "elsewhere2" in _names(project_dir=tmp_path / "other2")

    def test_the_customer_builtins_are_still_there(self, project, monkeypatch):
        monkeypatch.chdir(project / "sub")

        names = _names()
        assert "co-browser" in names
        assert "co-mail-and-drive" in names
        assert "commit" not in names

    def test_outside_any_project_it_uses_the_cwd(self, tmp_path, monkeypatch):
        loose = tmp_path / ".co" / "skills" / "loose"
        loose.mkdir(parents=True)
        (loose / "SKILL.md").write_text("---\nname: loose\ndescription: d\n---\n\nGo.\n")
        monkeypatch.chdir(tmp_path)

        assert "loose" in _names()
