"""The skill you put in your project must be the one that runs.

`loader.py`'s docstring states the contract outright — "priority: project > user
> builtin, highest > lowest" — and `co ai` builds its system prompt from this
registry, so getting it backwards means the agent silently follows different
instructions than the ones in the repo.
"""

import pytest

import connectonion.cli.co_ai.skills.loader as loader


def _skill(root, name, description):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\ndo the {description} thing\n",
        encoding="utf-8",
    )


@pytest.fixture
def tiers(tmp_path, monkeypatch):
    """A `commit` skill at all three tiers, each identifiable by its description."""
    home = tmp_path / "home"
    _skill(home / ".co" / "skills", "commit", "USER")
    monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: home))

    builtin = tmp_path / "builtin"
    _skill(builtin, "commit", "BUILTIN")
    monkeypatch.setattr(loader, "__file__", str(tmp_path / "skills" / "loader.py"))
    (tmp_path / "skills").mkdir(exist_ok=True)
    monkeypatch.setattr(
        loader.Path, "cwd", staticmethod(lambda: tmp_path / "project")
    )

    project = tmp_path / "project"
    _skill(project / ".co" / "skills", "commit", "PROJECT")
    return project, builtin


class TestPrecedence:
    def test_a_project_skill_beats_the_user_one(self, tmp_path, monkeypatch):
        """The case a team hits: someone customises a skill in the repo and the
        agent keeps serving the personal copy from their laptop."""
        home = tmp_path / "home"
        _skill(home / ".co" / "skills", "commit", "USER")
        monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: home))

        project = tmp_path / "project"
        _skill(project / ".co" / "skills", "commit", "PROJECT")

        registry = loader.load_skills(project)

        assert registry["commit"].description == "PROJECT"

    def test_a_project_skill_beats_the_bundled_one(self, tmp_path, monkeypatch):
        """The case in the issue: customise the bundled `commit` skill by adding
        .co/skills/commit/SKILL.md, and the stock one is served instead."""
        home = tmp_path / "home"
        (home / ".co").mkdir(parents=True)
        monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: home))

        builtin_dir = tmp_path / "fake_pkg" / "builtin"
        _skill(builtin_dir, "commit", "BUILTIN")
        monkeypatch.setattr(loader, "__file__", str(tmp_path / "fake_pkg" / "loader.py"))

        project = tmp_path / "project"
        _skill(project / ".co" / "skills", "commit", "PROJECT")

        registry = loader.load_skills(project)

        assert registry["commit"].description == "PROJECT"

    def test_a_user_skill_beats_the_bundled_one(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        _skill(home / ".co" / "skills", "commit", "USER")
        monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: home))

        builtin_dir = tmp_path / "fake_pkg" / "builtin"
        _skill(builtin_dir, "commit", "BUILTIN")
        monkeypatch.setattr(loader, "__file__", str(tmp_path / "fake_pkg" / "loader.py"))

        project = tmp_path / "project"
        (project / ".co").mkdir(parents=True)

        registry = loader.load_skills(project)

        assert registry["commit"].description == "USER"

    def test_skills_with_different_names_all_survive(self, tmp_path, monkeypatch):
        """Precedence must not become "keep only one of everything"."""
        home = tmp_path / "home"
        _skill(home / ".co" / "skills", "mine", "USER")
        monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: home))

        project = tmp_path / "project"
        _skill(project / ".co" / "skills", "ours", "PROJECT")

        registry = loader.load_skills(project)

        assert {"mine", "ours"} <= set(registry)

    def test_discover_skills_reports_the_winner_first(self, tmp_path, monkeypatch):
        """load_skills() is not the only consumer — anything reading the list
        directly should see the winning entry, not a later shadow of it."""
        home = tmp_path / "home"
        _skill(home / ".co" / "skills", "commit", "USER")
        monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: home))

        project = tmp_path / "project"
        _skill(project / ".co" / "skills", "commit", "PROJECT")

        found = [s for s in loader.discover_skills(project) if s.name == "commit"]

        assert len(found) == 1, "a shadowed duplicate is still in the list"
        assert found[0].description == "PROJECT"
