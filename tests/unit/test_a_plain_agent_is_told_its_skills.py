"""A plain Agent with the skills plugin is told which skills exist (#1666).

`Agent("x", tools=[skill], plugins=[skills])` discovered `.co/skills/` into
`agent.skills` and never put the list in front of the model. Nothing called the
function that was written to do it. On a real model, five `co eval run --invoke
auto` cases called `skill(name=...)` zero times: a model cannot choose a skill it
was never told about.

These tests use a fake model that sees only what a real one sees — the messages
it is sent — and acts on them.

LLM-Note: Tests for connectonion/useful_plugins/skills.py (setup_skills prompt injection)
"""

import pytest

from connectonion.benchmark import runner
from connectonion.benchmark.suite import Case, Suite
from connectonion.core.agent import Agent
from connectonion.core.llm import LLMResponse, ToolCall
from connectonion.core.usage import TokenUsage
from connectonion.useful_plugins import skill, skills
from tests.utils.mock_helpers import MockLLM

DESCRIPTION = "Use when the user asks to be reimbursed for an invoice"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / ".co" / "skills" / "reimbursement"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: reimbursement\ndescription: {DESCRIPTION}\n---\nCheck the title matches.\n")
    (tmp_path / ".co" / "benchmarks").mkdir()
    (tmp_path / ".co" / "benchmarks" / "reimbursement.yaml").write_text("placeholder\n")
    return tmp_path


def system_text(messages):
    return "\n".join(m["content"] for m in messages if m.get("role") == "system")


def choosing_model(seen):
    """Calls skill(name='reimbursement') only if its prompt told it that skill exists."""
    def complete(messages, tools):
        prompt = system_text(messages)
        seen.append(prompt)
        told = "reimbursement" in prompt and DESCRIPTION in prompt
        called = any(m.get("role") == "tool" for m in messages)
        if told and not called:
            return LLMResponse(content=None, raw_response=None, usage=TokenUsage(), tool_calls=[
                ToolCall(name="skill", arguments={"name": "reimbursement"}, id="t1")])
        return LLMResponse(content="Submitted.", tool_calls=[], raw_response=None, usage=TokenUsage())
    return complete


def plain_agent(seen, **kwargs):
    return Agent("x", tools=[skill], plugins=[skills],
                 llm=MockLLM(on_complete=choosing_model(seen)), log=False, **kwargs)


def test_the_model_is_sent_each_skill_name_and_description(project):
    seen = []
    agent = plain_agent(seen)

    agent.input("Please reimburse INV-301")

    assert "reimbursement" in seen[0] and DESCRIPTION in seen[0]
    assert "skill(" in seen[0], "the model is told how to load one, not only that it exists"


def test_a_fresh_session_is_told_too(project):
    """The benchmark runs every case on a reset session; the list must survive it."""
    seen = []
    agent = plain_agent(seen)

    agent.input("first")
    agent.reset_conversation()
    agent.input("second")

    assert DESCRIPTION in seen[-1]


def test_a_prompt_that_already_lists_skills_is_not_given_a_second_list(project):
    """co ai builds its own `# Available Skills` section and also installs this
    plugin; two catalogues of the same skills would only cost tokens."""
    existing = "BASE\n\n# Available Skills\n\n<available_skills>\n</available_skills>"
    seen = []
    agent = plain_agent(seen, system_prompt=existing)

    agent.input("hi")

    assert seen[0].count("# Available Skills") == 1


def test_co_eval_run_invoke_auto_can_pass_on_a_skill(project):
    seen = []
    agent = plain_agent(seen)
    case = Case(id="one-invoice", kind="normal", input="Please reimburse INV-301",
                must=["The invoice is submitted"], must_not=["Payment is claimed"])
    suite = Suite(name="reimbursement", cases=[case],
                  path=project / ".co" / "benchmarks" / "reimbursement.yaml")

    def judge(prompt, output, model):
        return output(verdicts=[
            {"statement": 1, "status": "occurred", "reason": "r", "evidence": "e"},
            {"statement": 2, "status": "did_not_occur", "reason": "r", "evidence": "e"}])

    report = runner.run(suite, agent, agent_path="agent.py", skill=runner.resolve_skill("reimbursement"),
                        invoke="auto", judge_model="judge", judge_call=judge)

    assert report["cases"][0]["attempts"][0]["activation"]["status"] == "PASS"
    assert report["summary"]["exit_code"] == 0
