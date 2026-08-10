"""Tier visibility: which skills travel, and which links are broken."""
from io import StringIO
import pytest
from pathlib import Path
from rich.console import Console

# useful_plugins/__init__ rebinds the name `skills` to the plugin LIST, so
# `import ...skills as sk` hands back a list. Reach the module through sys.modules.
import sys
import connectonion.useful_plugins.skills  # noqa: F401  (registers the module)

sk = sys.modules["connectonion.useful_plugins.skills"]


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A project with a project-tier skill and a user-tier one."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    (project / ".co" / "skills" / "ships").mkdir(parents=True)
    (project / ".co" / "skills" / "ships" / "SKILL.md").write_text(
        "---\nname: ships\ndescription: travels\n---\ndo it\n")
    (home / ".co" / "skills" / "stays").mkdir(parents=True)
    (home / ".co" / "skills" / "stays" / "SKILL.md").write_text(
        "---\nname: stays\ndescription: personal\n---\ndo it\n")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return project, home


class TestWhatTravels:
    def test_a_user_tier_skill_is_named_as_staying_behind(self, tree):
        project, _ = tree
        staying = sk.skills_that_will_not_travel(project_dir=project)
        assert [s.name for s in staying] == ["stays"]

    def test_a_project_tier_skill_is_not_reported(self, tree):
        project, _ = tree
        assert "ships" not in {s.name for s in sk.skills_that_will_not_travel(project_dir=project)}

    def test_builtin_travels_because_it_ships_inside_the_package(self):
        """It is installed with connectonion, so a deployed agent has it — even
        though it is deliberately not published to clients."""
        assert "builtin" in sk.TRAVELS_ON_DEPLOY
        assert "builtin" not in sk.PUBLISHED_SKILL_LOCATIONS


class TestBrokenLinks:
    def test_a_dangling_symlink_is_reported_not_skipped(self, tree):
        project, _ = tree
        link = project / ".co" / "skills" / "ghost"
        link.symlink_to(project / "nowhere")

        problems = sk.find_skill_problems(project_dir=project)

        assert ("project", "ghost", "broken symlink") in problems

    def test_a_dangling_symlink_reports_its_real_path_and_target(self, tree):
        project, _ = tree
        link = project / ".co" / "skills" / "ghost"
        target = project / "missing" / "skill"
        link.symlink_to(target)

        problem = next(
            p for p in sk.find_skill_problem_details(project_dir=project)
            if p.name == "ghost"
        )

        assert problem.path == link
        assert problem.target == target

    def test_deploy_marks_only_a_broken_skill_that_travels_as_failure(self, tree):
        from connectonion.cli.commands.deploy_commands import _print_deploy_skill_problems

        project, home = tree
        project_link = project / ".co" / "skills" / "project-ghost"
        project_link.symlink_to(project / "missing-project-skill")
        user_link = home / ".co" / "skills" / "user-ghost"
        user_link.symlink_to(home / "missing-user-skill")
        stream = StringIO()

        _print_deploy_skill_problems(
            project,
            Console(file=stream, color_system=None, width=300),
            payload_roots=(project,),
        )

        output = stream.getvalue()
        assert f"✗ {project_link} — broken symlink → {project / 'missing-project-skill'}" in output
        assert "(project; affects this deploy)" in output
        assert f"! {user_link} — broken symlink → {home / 'missing-user-skill'}" in output
        assert "(user; not in deploy payload)" in output
        assert "user/user-ghost" not in output

    def test_an_explicitly_bundled_user_skill_affects_the_deploy(self, tree):
        from connectonion.cli.commands.deploy_commands import _print_deploy_skill_problems

        project, home = tree
        target = home / "source" / "ghost"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("---\ndescription: [broken\n---\n")
        link = home / ".co" / "skills" / "ghost"
        link.symlink_to(target)
        stream = StringIO()

        _print_deploy_skill_problems(
            project,
            Console(file=stream, color_system=None, width=300),
            payload_roots=(link.resolve(),),
        )

        assert f"✗ {link}" in stream.getvalue()
        assert "(user; affects this deploy)" in stream.getvalue()

    def test_a_bundled_skill_directory_is_not_reported_as_staying(self, tree, monkeypatch):
        from connectonion.cli.commands import deploy_commands

        project, home = tree
        stream = StringIO()
        monkeypatch.setattr(
            deploy_commands,
            "console",
            Console(file=stream, color_system=None, width=300),
        )

        deploy_commands._warn_about_skills_left_behind(
            project, [home / ".co" / "skills"]
        )

        assert "stays" not in stream.getvalue()

    def test_an_untracked_project_problem_is_not_called_payload(self, tree):
        from connectonion.cli.commands.deploy_commands import _print_deploy_skill_problems

        project, _ = tree
        link = project / ".co" / "skills" / "untracked"
        link.symlink_to(project / "missing")
        stream = StringIO()

        _print_deploy_skill_problems(
            project,
            Console(file=stream, color_system=None, width=300),
            payload_entries=set(),
        )

        assert f"! {link}" in stream.getvalue()
        assert "not in deploy payload" in stream.getvalue()

    def test_a_tracked_file_below_a_problem_directory_is_payload(self, tree):
        from connectonion.cli.commands.deploy_commands import _print_deploy_skill_problems

        project, _ = tree
        skill = project / ".co" / "skills" / "bad-yaml"
        skill.mkdir()
        manifest = skill / "SKILL.md"
        manifest.write_text("---\ndescription: [broken\n---\n")
        stream = StringIO()

        _print_deploy_skill_problems(
            project,
            Console(file=stream, color_system=None, width=300),
            payload_entries={manifest.absolute()},
        )

        assert f"✗ {skill}" in stream.getvalue()
        assert "affects this deploy" in stream.getvalue()

    def test_rich_markup_in_a_path_is_printed_literally(self, tree):
        from connectonion.cli.commands.deploy_commands import _print_deploy_skill_problems

        project, home = tree
        link = home / ".co" / "skills" / "[red]ghost"
        link.symlink_to(home / "[blue]missing")
        stream = StringIO()

        _print_deploy_skill_problems(
            project, Console(file=stream, color_system=None, width=300)
        )

        output = stream.getvalue()
        assert str(link) in output
        assert str(home / "[blue]missing") in output

    def test_a_symlink_to_its_own_ancestor_is_reported(self, tree):
        project, _ = tree
        skills_dir = project / ".co" / "skills"
        (skills_dir / "loop").symlink_to(skills_dir)

        problems = sk.find_skill_problems(project_dir=project)

        assert any(name == "loop" and "ancestor" in reason
                   for _, name, reason in problems)

    def test_a_plain_directory_without_a_skill_file_is_not_a_problem(self, tree):
        """People keep notes and scratch dirs in here. Only a link makes a claim
        that can be false."""
        project, _ = tree
        (project / ".co" / "skills" / "notes").mkdir()

        assert sk.find_skill_problems(project_dir=project) == []

    def test_a_healthy_tree_reports_nothing(self, tree):
        project, _ = tree
        assert sk.find_skill_problems(project_dir=project) == []
