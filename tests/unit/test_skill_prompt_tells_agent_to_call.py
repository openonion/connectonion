"""The skill list has to tell the agent what to do with it.

A project skill whose description named its trigger phrases was never invoked:
asked in exactly those words, the agent ran glob, then glob again, then `find`
— hunting for a file it could never see, because skills live under dot
directories. The list said "you can call the skill() tool", which is a
description of a capability, not an instruction to use it.
"""

import sys

import pytest

skills_plugin = sys.modules.get("connectonion.useful_plugins.skills")
if skills_plugin is None:
    import connectonion.useful_plugins.skills  # noqa: F401
    skills_plugin = sys.modules["connectonion.useful_plugins.skills"]


class FakeAgent:
    def __init__(self):
        self.co_dir = None
        self.current_session = {"messages": [{"role": "system", "content": "BASE."}]}

    @property
    def prompt(self):
        return self.current_session["messages"][0]["content"]


@pytest.fixture
def injected(monkeypatch):
    from connectonion.useful_plugins.skills import SkillInfo

    monkeypatch.setattr(skills_plugin, "_discover_all_skills", lambda **kw: [
        SkillInfo(name="contract-ledger",
                  description="use when the user says 整理合同 / 更新台账",
                  location="project"),
        SkillInfo(name="commit", description="Create git commits", location="builtin"),
    ])
    agent = FakeAgent()
    skills_plugin._inject_skills_to_system_prompt(agent)
    return agent.prompt


class TestItInstructsRatherThanDescribes:
    def test_loading_a_matching_skill_is_stated_as_the_first_action(self, injected):
        """"You can call skill()" is a capability. The agent needs to be told
        that a matching description means call it, before doing anything else."""
        assert "first action" in injected.lower()

    def test_it_says_not_to_search_the_filesystem_for_skills(self, injected):
        """The observed failure was glob, glob, find — a hunt that cannot
        succeed, because skills live under dot directories."""
        lowered = injected.lower()
        assert "glob" in lowered or "search" in lowered
        assert "skill" in lowered

    def test_the_skill_tool_is_named_so_the_agent_can_call_it(self, injected):
        assert "skill(" in injected


class TestItKeepsSayingWhatIsAvailable:
    def test_every_discovered_skill_is_listed(self, injected):
        assert "contract-ledger" in injected
        assert "commit" in injected

    def test_descriptions_are_kept(self, injected):
        """The description is what the agent matches the user's words against —
        dropping it to save tokens would remove the trigger."""
        assert "整理合同" in injected

    def test_the_scope_of_each_skill_is_visible(self, injected):
        """With dozens of skills, "this one is the project's" is what breaks a
        tie between similar names."""
        assert "project" in injected

    def test_project_skills_come_before_builtin_ones(self, injected):
        """Order is a signal too: the project's own skill is the one meant to
        win when both could apply."""
        assert injected.index("contract-ledger") < injected.index("commit")


class TestNothingToSayStaysQuiet:
    def test_no_skills_means_no_section(self, monkeypatch):
        monkeypatch.setattr(skills_plugin, "_discover_all_skills", lambda **kw: [])
        agent = FakeAgent()

        skills_plugin._inject_skills_to_system_prompt(agent)

        assert agent.prompt == "BASE."
