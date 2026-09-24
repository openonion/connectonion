"""Unit tests for the benchmark runner: real Agent, real skills plugin, fake model and judge.

LLM-Note: Tests for connectonion.benchmark.runner

What it tests:
- The judge's three answers map to PASS/FAIL/UNVERIFIED in code: a must_not that occurred is a hard FAIL,
  cannot_verify is UNVERIFIED, a statement the judge skipped is UNVERIFIED, never PASS
- auto invocation: a real Agent that calls skill(name=...) is activated; one that answers without it is not
- explicit invocation: the real skills plugin replaces `/name input`; the report records the effective input
- a missing skill is exit 2 before any case runs; an Agent that raises is a runner error (exit 3), never a pass
- load_agent imports a file ending in host(agent) without serving
- CO_EVAL_LIVE is 0 during a run unless --live, and restored after

Components under test:
- Module: connectonion/benchmark/runner.py (with connectonion.core.agent.Agent and useful_plugins.skills)
"""

import os
import textwrap

import pytest

from connectonion.benchmark import runner
from connectonion.benchmark.suite import Case, Suite
from connectonion.core.agent import Agent
from connectonion.core.llm import LLMResponse, ToolCall
from connectonion.core.usage import TokenUsage
from connectonion.useful_plugins import skill, skills
from tests.utils.mock_helpers import MockLLM

SKILL_BODY = "Refund policy: refund only with a receipt. Never refund cash without one."


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / ".co" / "skills" / "refund"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(f"---\nname: refund\ndescription: Handle refunds\n---\n{SKILL_BODY}\n")
    (tmp_path / ".co" / "benchmarks").mkdir()
    (tmp_path / ".co" / "benchmarks" / "refund.yaml").write_text("placeholder\n")
    return tmp_path


def suite(project, *cases):
    return Suite(name="refund", path=project / ".co" / "benchmarks" / "refund.yaml", cases=list(cases))


CASE = Case(id="with-receipt", kind="normal", input="Customer has a receipt, refund them",
            must=["The refund is approved"], must_not=["Cash is refunded without a receipt"])


def agent(calls_skill: bool, answer="Refund approved."):
    """A real Agent whose model either calls the skill tool first or answers straight away."""
    def complete(messages, tools):
        called = any(m.get("role") == "tool" for m in messages)
        if calls_skill and not called:
            return LLMResponse(content=None, raw_response=None, usage=TokenUsage(),
                               tool_calls=[ToolCall(name="skill", arguments={"name": "refund"}, id="t1")])
        return LLMResponse(content=answer, tool_calls=[], raw_response=None, usage=TokenUsage())
    return Agent("refund-bot", tools=[skill], plugins=[skills], llm=MockLLM(on_complete=complete), log=False)


def judge_says(*statuses):
    """A judge that answers the numbered statements with these statuses, in order."""
    def call(prompt, output, model):
        return output(verdicts=[{"statement": i, "status": status, "reason": status, "evidence": "e"}
                                for i, status in enumerate(statuses, start=1)])
    return call


def run(project, bot, *, skill_name="refund", invoke="auto", judge=None, **kwargs):
    chosen = runner.resolve_skill(skill_name) if skill_name else None
    return runner.run(suite(project, CASE), bot, agent_path="agent.py", skill=chosen, invoke=invoke,
                      judge_model="judge-model", judge_call=judge or judge_says("occurred", "did_not_occur"),
                      **kwargs)


# ---- scoring -----------------------------------------------------------------------------

def test_a_forbidden_outcome_that_occurred_is_a_hard_fail_whatever_else_passed(project):
    report = run(project, agent(True), judge=judge_says("occurred", "occurred"))

    verdicts = [i["verdict"] for i in report["cases"][0]["attempts"][0]["indicators"]]
    assert verdicts == ["PASS", "FAIL"]
    assert report["summary"]["forbidden_failures"] == 1 and report["summary"]["exit_code"] == 1


def test_what_the_judge_cannot_verify_or_skipped_is_unverified_never_pass(project):
    report = run(project, agent(True), judge=judge_says("cannot_verify"))  # nothing said about statement 2

    indicators = report["cases"][0]["attempts"][0]["indicators"]
    assert [i["verdict"] for i in indicators] == ["UNVERIFIED", "UNVERIFIED"]
    assert "no verdict" in indicators[1]["reason"]
    assert report["summary"]["exit_code"] == 1


def test_a_clean_run_passes_and_exits_zero(project):
    report = run(project, agent(True))

    assert report["summary"]["exit_code"] == 0
    assert report["cases"][0]["stability"] == "1/1"
    assert report["skill"]["sha256"] and "instructions" not in report["skill"]
    assert report["agent"]["model"] == "mock-llm"


# ---- was the skill used? --------------------------------------------------------------------

def test_auto_counts_the_skill_only_if_the_real_agent_called_it(project):
    used = run(project, agent(True))["cases"][0]["attempts"][0]["activation"]
    skipped = run(project, agent(False))

    assert used["status"] == "PASS"
    activation = skipped["cases"][0]["attempts"][0]["activation"]
    assert activation["status"] == "FAIL" and "never called skill(name='refund')" in activation["evidence"]
    assert skipped["summary"]["not_activated"] == 1 and skipped["summary"]["exit_code"] == 1


def test_explicit_goes_through_the_real_plugin_and_records_what_was_sent(project):
    report = run(project, agent(False), invoke="explicit")

    case = report["cases"][0]
    assert case["effective_input"] == "/refund Customer has a receipt, refund them"
    assert case["attempts"][0]["activation"] == {
        "status": "PASS", "evidence": "/refund was replaced with .co/skills/refund/SKILL.md"}, \
        "a project skill is named by its project path, not an absolute one"


def test_explicit_without_the_plugin_is_caught_not_assumed(project):
    bare = Agent("no-plugin", llm=MockLLM(on_complete=lambda m, t: LLMResponse(
        content="ok", tool_calls=[], raw_response=None, usage=TokenUsage())), log=False)

    report = run(project, bare, invoke="explicit")

    activation = report["cases"][0]["attempts"][0]["activation"]
    assert activation["status"] == "FAIL" and "reached the Agent unchanged" in activation["evidence"]


def test_without_a_skill_no_skill_is_claimed(project):
    report = run(project, agent(False), skill_name=None)

    assert report["skill"] is None and report["cases"][0]["attempts"][0]["activation"] is None
    assert report["summary"]["exit_code"] == 0


# ---- failure is never a pass ----------------------------------------------------------------------

def test_a_skill_that_is_not_there_is_a_usage_error_before_anything_runs(project):
    with pytest.raises(runner.RunnerError) as error:
        runner.resolve_skill("missing")

    assert error.value.code == 2 and ".co/skills/missing/SKILL.md" in str(error.value)


def test_an_agent_that_raises_is_a_runner_error_not_a_pass(project):
    class Broken:
        name, llm, current_session = "broken", None, None

        def reset_conversation(self):
            pass

        def input(self, text):
            raise ConnectionError("model unreachable")

    report = run(project, Broken(), skill_name=None)

    attempt = report["cases"][0]["attempts"][0]
    assert attempt["passed"] is False and "ConnectionError: model unreachable" in attempt["error"]
    assert report["summary"]["exit_code"] == 3


def test_explicit_needs_a_skill(project):
    with pytest.raises(runner.RunnerError, match="needs --skill"):
        run(project, agent(False), skill_name=None, invoke="explicit")


def test_a_template_agent_py_that_ends_in_host_is_imported_without_serving(project):
    (project / "agent.py").write_text(textwrap.dedent("""
        from connectonion import Agent, host
        from connectonion.core.llm import LLM, LLMResponse

        class Quiet(LLM):
            def __init__(self):
                self.model = "quiet"
            def complete(self, messages, tools=None, **kw):
                return LLMResponse(content="hi", tool_calls=[], raw_response=None)
            def structured_complete(self, messages, output_schema, **kw):
                raise NotImplementedError

        agent = Agent("template", llm=Quiet(), log=False)
        host(agent)  # never returns if it really serves
    """))

    loaded = runner.load_agent("agent.py")

    import connectonion
    assert loaded.name == "template"
    assert connectonion.host.__name__ == "host", "the real host() is back after the import"


def test_live_is_off_during_a_run_unless_asked_and_restored_after(project, monkeypatch):
    seen = []

    class Recorder:
        name, llm = "rec", None
        current_session = {}

        def reset_conversation(self):
            pass

        def input(self, text):
            seen.append(os.environ.get("CO_EVAL_LIVE"))
            return "done"

    monkeypatch.setenv("CO_EVAL_LIVE", "outer")
    run(project, Recorder(), skill_name=None)
    run(project, Recorder(), skill_name=None, live=True)

    assert seen == ["0", "1"]
    assert os.environ["CO_EVAL_LIVE"] == "outer"
