"""Project readers must not mistake a nested directory for the project's `.co/`.

#660 and #661 made the rule: the directory that owns `.co/` is the project, and
everything walks up to find it. The walk-up stops at the *nearest* `.co/`. That
means readers must consistently resolve from the project root. This regression
suite covers the four readers previously found resolving against the bare cwd:
project skills, project subagents, the co_ai skill loader, and the permission
whitelist the approval plugin reads from `host.yaml`.
"""

from pathlib import Path

import pytest


BLOCKED = "0x" + "b" * 64


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A configured project with a subdirectory to run from."""
    co = tmp_path / "project" / ".co"
    (co / "skills" / "mine").mkdir(parents=True)
    (co / "agents" / "helper").mkdir(parents=True)
    (co / "host.yaml").write_text(
        "name: real\n"
        "port: 8806\n"
        "trust: strict\n"
        "permissions:\n"
        "  my_project_tool:\n"
        "    allowed: true\n"
    )
    (co / "blocklist.txt").write_text(BLOCKED + "\n")
    (co / "skills" / "mine" / "SKILL.md").write_text(
        "---\nname: mine\ndescription: d\n---\n\nDo it.\n"
    )
    (co / "agents" / "helper" / "AGENT.md").write_text(
        "---\nname: helper\ndescription: d\n---\n\nHelp.\n"
    )
    (tmp_path / "project" / "sub" / "deeper").mkdir(parents=True)

    from connectonion.network.trust import tools
    monkeypatch.setattr(tools, "_mentioned", set(), raising=False)
    return tmp_path / "project"


class TestTheReadersWalkUpToo:
    """Four lookups that still resolved against the bare cwd."""

    def test_a_project_skill_is_found(self, project, monkeypatch):
        from connectonion.useful_plugins.skills import _load_skill

        monkeypatch.chdir(project / "sub")

        assert _load_skill("mine") is not None

    def test_the_co_ai_loader_sees_it(self, project, monkeypatch):
        from connectonion.cli.co_ai.skills.loader import discover_skills

        monkeypatch.chdir(project / "sub")

        assert any(s.name == "mine" for s in discover_skills())

    def test_a_project_subagent_is_found(self, project, monkeypatch):
        from connectonion.useful_plugins.subagents import _discover_all_agents

        monkeypatch.chdir(project / "sub")

        assert any(a["name"] == "helper" for a in _discover_all_agents())

    def test_the_permission_whitelist_comes_from_the_project(self, project, monkeypatch):
        """#661 taught `host()` to walk up for host.yaml; the approval plugin
        reads permissions out of the same file and did not."""
        from connectonion.useful_plugins.tool_approval.approval import (
            load_permission_patterns,
        )

        monkeypatch.chdir(project / "sub")

        assert "my_project_tool" in load_permission_patterns(None)

    def test_two_levels_down_as_well(self, project, monkeypatch):
        from connectonion.useful_plugins.skills import _load_skill

        monkeypatch.chdir(project / "sub" / "deeper")

        assert _load_skill("mine") is not None


class TestFromTheProjectRoot:
    """Unchanged — all of this already worked."""

    def test_the_skill_is_still_found(self, project, monkeypatch):
        from connectonion.useful_plugins.skills import _load_skill

        monkeypatch.chdir(project)

        assert _load_skill("mine") is not None

    def test_the_permission_is_still_read(self, project, monkeypatch):
        from connectonion.useful_plugins.tool_approval.approval import (
            load_permission_patterns,
        )

        monkeypatch.chdir(project)

        assert "my_project_tool" in load_permission_patterns(None)


class TestWhatMustNotChange:

    def test_user_level_skills_are_still_reached(self, project, monkeypatch, tmp_path):
        """Walking up must not cost the ~/.co fallback."""
        from connectonion.useful_plugins.skills import _get_skill_paths

        monkeypatch.chdir(project / "sub")
        paths = [str(p) for p in _get_skill_paths("anything")]

        assert any(str(Path.home() / ".co") in p for p in paths)

    def test_an_explicit_base_path_still_wins(self, project, tmp_path, monkeypatch):
        from connectonion.cli.co_ai.skills.loader import discover_skills

        elsewhere = tmp_path / "elsewhere"
        (elsewhere / ".co" / "skills" / "other").mkdir(parents=True)
        (elsewhere / ".co" / "skills" / "other" / "SKILL.md").write_text(
            "---\nname: other\ndescription: d\n---\n\nGo.\n"
        )
        monkeypatch.chdir(project)

        assert any(s.name == "other" for s in discover_skills(base_path=elsewhere))

    def test_outside_any_project_the_cwd_is_used(self, tmp_path, monkeypatch):
        from connectonion.useful_plugins.skills import _load_skill

        (tmp_path / ".co" / "skills" / "loose").mkdir(parents=True)
        (tmp_path / ".co" / "skills" / "loose" / "SKILL.md").write_text(
            "---\nname: loose\ndescription: d\n---\n\nGo.\n"
        )
        monkeypatch.chdir(tmp_path)

        assert _load_skill("loose") is not None


class TestTheSecondCreator:
    """`co skills copy --to-project` plants one too.

        skills_dir = (Path.cwd() / ".co" / "skills") if to_project else SKILLS_DIR
        skills_dir.mkdir(parents=True, exist_ok=True)

    The point of `--to-project` is that a deploy will find the skill. Run from a
    subdirectory it puts the skill somewhere no deploy looks *and* leaves a decoy
    `.co/` behind that shadows the project's own from then on.
    """

    def test_no_decoy_appears(self, project, monkeypatch, tmp_path):
        from connectonion.cli.commands.skills_commands import _copy_entry
        from connectonion.cli.commands import skills_commands

        src = tmp_path / "src" / "new"
        src.mkdir(parents=True)
        (src / "SKILL.md").write_text("---\nname: new\ndescription: d\n---\n\nGo.\n")
        monkeypatch.chdir(project / "sub")

        _copy_entry({"name": "new", "path": str(src / "SKILL.md"), "source": "t"},
                    force=True, skills_dir=skills_commands.project_skills_dir())

        assert not (project / "sub" / ".co").exists()

    def test_it_lands_where_a_deploy_looks(self, project, monkeypatch, tmp_path):
        from connectonion.cli.commands.skills_commands import _copy_entry
        from connectonion.cli.commands import skills_commands

        src = tmp_path / "src" / "new"
        src.mkdir(parents=True)
        (src / "SKILL.md").write_text("---\nname: new\ndescription: d\n---\n\nGo.\n")
        monkeypatch.chdir(project / "sub")

        _copy_entry({"name": "new", "path": str(src / "SKILL.md"), "source": "t"},
                    force=True, skills_dir=skills_commands.project_skills_dir())

        assert (project / ".co" / "skills" / "new" / "SKILL.md").exists()


class TestTrustIsConsistentWithItself:
    """`list_file` walks up (#660); two functions in the same file did not.

    Both fail safe on their own — no admins found, no self address — but the
    split means one half of trust answers for the project and the other half
    answers for wherever the process was standing. The visible cost: an agent
    onboarding by payment advertises `methods: ["payment"]` and no
    `payment_address`, so the client is told to pay and not told where.
    """

    def test_the_admins_are_the_projects_admins(self, project, monkeypatch):
        from connectonion.network.trust.tools import load_admins

        (project / ".co" / "admins.txt").write_text("0x" + "a" * 64 + "\n")
        monkeypatch.chdir(project / "sub")

        assert "0x" + "a" * 64 in load_admins()

    def test_the_self_address_is_the_projects(self, project, monkeypatch):
        from connectonion import address
        from connectonion.network.trust.tools import get_self_address

        saved = address.generate()
        address.save(saved, project / ".co")
        monkeypatch.chdir(project / "sub")

        assert get_self_address() == saved["address"]

    def test_an_explicit_co_dir_still_wins(self, project, tmp_path, monkeypatch):
        from connectonion.network.trust.tools import load_admins

        other = tmp_path / "other" / ".co"
        other.mkdir(parents=True)
        (other / "admins.txt").write_text("0x" + "c" * 64 + "\n")
        monkeypatch.chdir(project)

        assert "0x" + "c" * 64 in load_admins(other)
