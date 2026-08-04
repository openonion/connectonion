"""A stray `.co/` one directory down quietly replaces the project's own.

#660 and #661 made the rule: the directory that owns `.co/` is the project, and
everything walks up to find it. The walk-up stops at the *nearest* `.co/`. That
makes any code which creates a `.co/` wherever it happens to be standing far more
dangerous than it was before those two fixes — it does not merely leave a stray
directory, it plants a decoy that every later lookup finds first.

`plan_mode.get_plan_file_path` does exactly that:

    co_dir = Path.cwd() / ".co"
    co_dir.mkdir(exist_ok=True)

Measured on a project whose `.co/host.yaml` says `trust: strict` and whose
`.co/blocklist.txt` holds an address, running `co ai` from a subdirectory:

    BEFORE plan mode: trust=strict  blocked=True
    plan mode created: True
    AFTER  plan mode: trust=None    blocked=False

Both flips are fail-open, and both persist: the decoy stays on disk, so every
later run from that subdirectory reads it. A project configured whitelist-only
admits contacts and accepts an invite code, and an address the operator blocked
is no longer blocked — because someone once opened plan mode in a subdirectory.

Logger had the same shape and #661 fixed it. This is the remaining creator, and
the same round found four readers still resolving against the bare cwd:
project skills, project subagents, the co_ai skill loader, and the permission
whitelist the approval plugin reads out of the same `host.yaml` that #661 taught
`host()` to walk up for — so today one half of that file is found from a
subdirectory and the other half is not.
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


class TestPlanModePlantsNoDecoy:
    """The creator. This is the one that makes the others permanent."""

    def test_no_co_directory_appears_in_the_subdirectory(self, project, monkeypatch):
        from connectonion.cli.co_ai.tools.plan_mode import get_plan_file_path

        monkeypatch.chdir(project / "sub")
        get_plan_file_path("s1")

        assert not (project / "sub" / ".co").exists(), "plan mode planted a decoy .co/"

    def test_the_plan_goes_to_the_projects_own_co(self, project, monkeypatch):
        from connectonion.cli.co_ai.tools.plan_mode import get_plan_file_path

        monkeypatch.chdir(project / "sub")

        assert get_plan_file_path("s1").parent == project / ".co"

    def test_trust_survives_it(self, project, monkeypatch):
        """The consequence that matters: strict must not become the default."""
        from connectonion.cli.co_ai.tools.plan_mode import get_plan_file_path
        from connectonion.network.host.config import load_host_config

        monkeypatch.chdir(project / "sub")
        get_plan_file_path("s1")

        assert load_host_config(None).get("trust") == "strict"

    def test_a_blocked_address_stays_blocked(self, project, monkeypatch):
        from connectonion.cli.co_ai.tools.plan_mode import get_plan_file_path
        from connectonion.network.trust.tools import is_blocked

        monkeypatch.chdir(project / "sub")
        get_plan_file_path("s1")

        assert is_blocked(BLOCKED), "opening plan mode un-blocked a blocked address"

    def test_outside_any_project_it_still_works(self, tmp_path, monkeypatch):
        """No project above us — plan mode must still have somewhere to write."""
        from connectonion.cli.co_ai.tools.plan_mode import get_plan_file_path

        monkeypatch.chdir(tmp_path)
        path = get_plan_file_path("s1")

        assert path.parent == tmp_path / ".co"
        assert path.parent.is_dir(), "it must still create one where there is no project"

    def test_the_session_id_still_scopes_the_file(self, project, monkeypatch):
        from connectonion.cli.co_ai.tools.plan_mode import get_plan_file_path

        monkeypatch.chdir(project / "sub")

        assert get_plan_file_path("abc").name == "PLAN_abc.md"
        assert get_plan_file_path(None).name != "PLAN_abc.md"


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
