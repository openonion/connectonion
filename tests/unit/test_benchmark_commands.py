"""End-to-end tests of the benchmark CLI: check → eval run → eval report, with only the judge faked.

LLM-Note: Tests for connectonion.cli.commands.benchmark_commands and connectonion.benchmark.report through the real Typer app

What it tests:
- `co benchmark` alone is discovery: help, never a run; `co benchmark list` on an empty project prints the schema
- `co benchmark check` exit 0 names the next command; exit 2 lists every problem with its fix
- `co eval run` imports a real agent.py, saves an immutable report, exits 0/1 by the verdicts, names the report command
- a second run is compared with the first: newly failing cases and forbidden outcomes that came back
- `co eval report --latest` reopens the saved run; an unknown benchmark is exit 2
- the older `co eval NAME` still reaches the older evals, and `co skills --help` points at benchmarks

Components under test:
- connectonion/cli/main.py (benchmark_app, eval_app, _EvalGroup), cli/commands/benchmark_commands.py, benchmark/report.py
"""

import json
import stat
import textwrap

import pytest
import yaml
from typer.testing import CliRunner

from connectonion.cli.main import app

AGENT_PY = textwrap.dedent("""
    from connectonion import Agent, host
    from connectonion.core.llm import LLM, LLMResponse
    from connectonion.core.usage import TokenUsage

    class Clerk(LLM):
        def __init__(self):
            self.model = "clerk-model"
        def complete(self, messages, tools=None, **kw):
            return LLMResponse(content="Handled: " + messages[-1]["content"], tool_calls=[],
                               raw_response=None, usage=TokenUsage())
        def structured_complete(self, messages, output_schema, **kw):
            raise NotImplementedError

    agent = Agent("clerk", llm=Clerk(), log=False)
    host(agent)
""")


def cases():
    out = [{"id": f"normal-{i}", "kind": "normal", "input": f"task {i}",
            "expect": {"must": [f"task {i} is handled"]}} for i in range(1, 5)]
    out.append({"id": "refuse", "kind": "counterexample", "input": "delete production",
                "expect": {"must": ["the request is refused"], "must_not": ["production is deleted"]}})
    return out


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".co" / "benchmarks").mkdir(parents=True)
    (tmp_path / ".co" / "benchmarks" / "ops.yaml").write_text(yaml.safe_dump({"name": "ops", "cases": cases()}))
    (tmp_path / "agent.py").write_text(AGENT_PY)
    return tmp_path


@pytest.fixture
def judge(monkeypatch):
    """The judge is the only fake: it says every must occurred and every must_not did not,
    unless a case id is listed in `judge.forbidden_happened`."""
    import importlib

    # `connectonion.llm_do` the attribute is the function; the module is what the judge imports from.
    llm_do_module = importlib.import_module("connectonion.llm_do")

    state = {"forbidden_happened": set()}

    def fake(prompt, output, model):
        forbidden = any(case_id in prompt for case_id in ()) or any(
            text in prompt for text in state["forbidden_happened"])
        numbered = [line for line in prompt.splitlines() if line[:2].rstrip(".").isdigit()]
        verdicts = []
        for line in numbered:
            number = int(line.split(".", 1)[0])
            is_forbidden = "production is deleted" in line
            status = ("occurred" if forbidden else "did_not_occur") if is_forbidden else "occurred"
            verdicts.append({"statement": number, "status": status, "reason": "r", "evidence": "e"})
        return output(verdicts=verdicts)

    monkeypatch.setattr(llm_do_module, "llm_do", fake)
    return state


def co(*args):
    return CliRunner().invoke(app, list(args))


def test_bare_benchmark_is_discovery_and_runs_nothing(project):
    result = co("benchmark")

    assert result.exit_code == 0
    assert "Author the standard BEFORE editing a skill" in result.output
    assert not (project / ".co" / "eval-runs").exists()


def test_list_on_an_empty_project_prints_the_schema(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = co("benchmark", "list")

    assert result.exit_code == 0 and "kind: counterexample" in result.output


def test_check_passes_and_names_the_run_command(project):
    result = co("benchmark", "check", "ops")

    assert result.exit_code == 0
    assert "Valid: 5 cases (4 normal, 1 counterexample)" in result.output
    assert "co eval run ops --agent agent.py" in result.output


def test_check_fails_with_every_problem_and_json_for_agents(project):
    (project / ".co" / "benchmarks" / "thin.yaml").write_text(yaml.safe_dump({"cases": cases()[:2]}))

    text = co("benchmark", "check", "thin")
    data = json.loads(co("benchmark", "check", "thin", "--json").stdout)

    assert text.exit_code == 2 and "only 2 valid case(s)" in text.output and "no counterexample" in text.output
    assert data["valid"] is False and {p["field"] for p in data["problems"]} == {"cases"}


def test_run_then_report_then_a_regression_is_named(project, judge):
    first = co("eval", "run", "ops", "--agent", "agent.py")
    assert first.exit_code == 0, first.output
    assert "expectations 6/6" in first.output and "co eval report ops --latest" in first.output
    reports = sorted((project / ".co" / "eval-runs" / "ops").glob("*/report.json"))
    assert len(reports) == 1 and stat.S_IMODE(reports[0].stat().st_mode) == 0o444
    saved = json.loads(reports[0].read_text())
    assert saved["agent"]["model"] == "clerk-model" and saved["skill"] is None
    assert yaml.safe_load((project / ".co" / "benchmarks" / "ops.yaml").read_text())["cases"] == cases(), \
        "the authored benchmark is never written to"

    judge["forbidden_happened"].add("production is deleted")
    second = co("eval", "run", "ops", "--agent", "agent.py")

    assert second.exit_code == 1
    assert "newly failing: refuse" in second.output
    # It passed in the run before, so this is new, not "again" (1.8.8b7 said "again").
    assert "newly forbidden: refuse: production is deleted" in second.output
    assert "forbidden again" not in second.output
    assert len(list((project / ".co" / "eval-runs" / "ops").glob("*/report.json"))) == 2

    reopened = co("eval", "report", "ops", "--latest")
    assert reopened.exit_code == 0 and "FAIL  refuse" in reopened.output
    assert "edit only the skill for refuse" in reopened.output


def test_report_for_a_benchmark_never_run_is_exit_2(project):
    result = co("eval", "report", "ops")

    assert result.exit_code == 2 and "co eval run ops --agent agent.py" in result.output


def test_a_first_multi_run_says_what_it_will_spend_and_suggests_one_run(project, judge):
    # 1.8.8b9: a new user followed the hint to --runs 3 and would have spent $3
    # of $5 before learning the cases could not pass.
    result = co("eval", "run", "ops", "--agent", "agent.py", "--runs", "3", "--max-iterations", "4")

    assert "5 cases × 3 run(s) = 15 Agent runs, each stopped after 4 steps" in result.output
    assert "--runs 1 first" in result.output
    assert json.loads(next((project / ".co" / "eval-runs" / "ops").glob("*/report.json")).read_text())[
        "max_iterations"] == 4

    again = co("eval", "run", "ops", "--agent", "agent.py", "--runs", "3")
    assert "each stopped after 10 steps" in again.output
    assert "--runs 1 first" not in again.output, "once a run is saved, more runs are a choice, not a trap"


def test_check_suggests_one_run_first(project):
    result = co("benchmark", "check", "ops")

    assert "--runs 1" in result.output and "--runs 3" not in result.output


def test_run_with_a_missing_agent_file_is_exit_2_not_3(project):
    result = co("eval", "run", "ops", "--agent", "nope.py")

    assert result.exit_code == 2 and "nope.py does not exist" in result.output


def test_run_refuses_an_invalid_benchmark_before_loading_any_agent(project):
    (project / ".co" / "benchmarks" / "thin.yaml").write_text(yaml.safe_dump({"cases": cases()[:1]}))

    result = co("eval", "run", "thin", "--agent", "agent.py")

    assert result.exit_code == 2 and "co benchmark check thin" in result.output


def test_the_older_co_eval_name_still_reaches_the_older_evals(project):
    result = co("eval", "some-old-eval")

    assert result.exit_code == 1 and "No evals found" in result.output


def test_skills_help_points_at_benchmarks_without_claiming_to_author(project):
    import re

    result = co("skills", "--help")
    # CI sets FORCE_COLOR, so the help carries ANSI codes mid-sentence; Rich also
    # wraps and boxes it. Compare the words.
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    text = " ".join(plain.replace("│", " ").split())

    assert "does not author or benchmark them" in text
    assert "co benchmark --help" in text


def test_the_example_printed_on_an_empty_project_passes_check(tmp_path, monkeypatch):
    """1.8.8b7 printed a 2-case "smallest valid one" that check then refused for having fewer than 5."""
    monkeypatch.chdir(tmp_path)
    listed = co("benchmark", "list")
    printed = listed.stdout.split("smallest valid one:", 1)[1].strip()

    (tmp_path / ".co" / "benchmarks").mkdir(parents=True)
    (tmp_path / ".co" / "benchmarks" / "example.yaml").write_text(printed)
    checked = co("benchmark", "check", "example")

    assert checked.exit_code == 0, checked.output
