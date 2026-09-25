"""
Purpose: Run a benchmark against the real Agent and score every expectation as PASS, FAIL or UNVERIFIED with its evidence
LLM-Note:
  Dependencies: imports from [contextlib, hashlib, json, os, time, typing, pydantic, benchmark/suite.py, llm_do, core/usage.py] and lazily from [cli/commands/eval_commands.get_agent_from_file, useful_plugins/skills._load_skill, connectonion] | imported by [cli/commands/benchmark_commands.py] | tested by [tests/unit/test_benchmark_runner.py]
  Data flow: agent.py → load_agent() (host() disabled during import) → per case × runs: reset_conversation → agent.input(effective input) → trace → activation evidence + tool evidence → judge() → Verdicts → attempt → report dict
  State/Effects: sets CO_EVAL_LIVE=0|1 in the environment for the duration of the run, restored after | writes nothing itself; report.save() does | the judge is one llm_do call per attempt
  Integration: `co eval run` builds the report and hands it to report.save/render | the judge and the Agent are separate: the judge never sees the SKILL.md, only the case, the answer and the tool evidence
  Errors: an Agent that raises, or a judge that fails, is a runner error on that attempt (exit 3 for the run), never a pass | a missing or unreadable --skill is RunnerError before any case runs

How a verdict is reached: the judge answers one narrower question per
statement — did this outcome occur, not occur, or can it not be verified from
what the run shows? The mapping to PASS/FAIL is code, not model output: for a
`must`, occurred is PASS; for a `must_not`, occurred is a hard FAIL. An
outcome that changes the world (sent, submitted, saved, paid) occurred only if
a tool result shows it; the Agent saying so is cannot-verify.
"""

import contextlib
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable, List, Literal, Optional

from pydantic import BaseModel

from .suite import Case, Suite

JUDGE_TEXT_LIMIT = 4000
TOOL_TEXT_LIMIT = 600

# Steps (LLM calls) one attempt may take before it is stopped. The co create
# template allows 100: on 1.8.8b9 a first benchmark whose cases carried no data
# let the coding agent search the workspace for invoices for up to 26 steps a
# case, and five cases cost a new user $1 of their $5. A case written with its
# data in the input is answered in a few steps, so 10 stops only the search.
# `co eval run --max-iterations N` raises it for a task that really needs more.
DEFAULT_MAX_ITERATIONS = 10


class RunnerError(RuntimeError):
    """The run could not happen as asked, and is never counted as a pass.

    `code` is the exit status: 2 when what was asked for is wrong (no such
    agent file, no such skill, a bad option), 3 when it was right and the
    machinery failed (the agent file would not import).
    """

    def __init__(self, message: str, code: int = 3):
        super().__init__(message)
        self.code = code


class _Verdict(BaseModel):
    statement: int
    status: Literal["occurred", "did_not_occur", "cannot_verify"]
    reason: str
    evidence: str


class _Judgement(BaseModel):
    verdicts: List[_Verdict]


# ---- the Agent ---------------------------------------------------------------------


def load_agent(path: str):
    """The Agent in `path`, imported without letting it start serving.

    The `co create` template ends with `host(agent)`, which never returns: a
    plain import of it would hang the run before the first case. host() is
    swapped for a no-op for exactly the duration of the import.
    """
    import connectonion

    from ..cli.commands.eval_commands import get_agent_from_file

    file = Path(path)
    if not file.exists():
        raise RunnerError(f"--agent {path} does not exist. Next: co eval run <name> --agent agent.py", code=2)
    original = connectonion.host
    connectonion.host = lambda *args, **kwargs: None
    try:
        return get_agent_from_file(str(file), str(file.resolve().parent))
    except Exception as error:  # an import error in someone's agent.py is theirs to read, in one line
        raise RunnerError(f"could not load an Agent from {path}: {type(error).__name__}: {error}") from error
    finally:
        connectonion.host = original


def agent_identity(agent, path: str) -> dict:
    llm = getattr(agent, "llm", None)
    return {"path": str(path), "name": getattr(agent, "name", ""), "model": getattr(llm, "model", "")}


def resolve_skill(name: str) -> dict:
    """Where the named skill is, and a hash of it, so a report says which version ran."""
    from ..useful_plugins.skills import _load_skill

    loaded = _load_skill(name)
    if loaded is None:
        raise RunnerError(
            f"skill {name!r} is not discoverable: no .co/skills/{name}/SKILL.md, ~/.co/skills/{name}/SKILL.md "
            f"or built-in. Next: write .co/skills/{name}/SKILL.md, then rerun", code=2)
    data = Path(loaded["path"]).read_bytes()
    return {"name": name, "path": loaded["path"], "sha256": hashlib.sha256(data).hexdigest(),
            "instructions": loaded["instructions"]}


# ---- one attempt ----------------------------------------------------------------------


def effective_input(case: Case, skill: Optional[dict], invoke: str) -> str:
    if invoke == "explicit" and skill:
        return f"/{skill['name']} {case.input}"
    return case.input


def activation(skill: Optional[dict], invoke: str, session: dict, sent: str) -> Optional[dict]:
    """Evidence that the skill under test actually ran. None when no skill was named.

    auto: the Agent called the `skill` tool with this name and it succeeded.
    explicit: the skills plugin replaced the `/name` message with the skill's
    instructions. That replacement is the only trace it leaves, so the message
    list is where to look.
    """
    if skill is None:
        return None
    name = skill["name"]
    trace = session.get("trace") or []
    if invoke == "auto":
        calls = {e.get("tool_id"): e for e in trace
                 if e.get("type") == "tool_call" and e.get("name") == "skill"
                 and (e.get("args") or {}).get("name") == name}
        for entry in trace:
            if entry.get("type") == "tool_result" and entry.get("tool_id") in calls:
                if entry.get("status") == "success":
                    return {"status": "PASS", "evidence": f"skill(name={name!r}) returned success"}
                return {"status": "FAIL", "evidence": f"skill(name={name!r}) returned {entry.get('status')}"}
        called = sorted({e.get("name") for e in trace if e.get("type") == "tool_call"} - {None})
        return {"status": "FAIL",
                "evidence": f"the Agent never called skill(name={name!r}); tools it did call: {called or 'none'}"}
    user_texts = [str(m.get("content", "")) for m in session.get("messages") or []
                  if m.get("role") == "user"]
    marker = skill["instructions"].strip()[:120]
    if any("Skill did not start" in text for text in user_texts):
        return {"status": "FAIL", "evidence": "the skill's preflight refused to start it"}
    if marker and any(marker in text for text in user_texts):
        return {"status": "PASS", "evidence": f"/{name} was replaced with {_shown(skill['path'])}"}
    return {"status": "FAIL",
            "evidence": f"{sent!r} reached the Agent unchanged: its skills plugin did not take /{name}"}


def _shown(path: str) -> str:
    """A project skill by its project path, `.co/skills/x/SKILL.md`. The absolute
    path wrapped every evidence line in two on the first real report."""
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return path  # ~/.co/skills or built-in: outside the project, so it stays absolute


def tool_evidence(session: dict) -> List[dict]:
    """What the tools actually did, for the judge: name, args, status, result."""
    evidence = []
    for entry in session.get("trace") or []:
        if entry.get("type") != "tool_result":
            continue
        evidence.append({
            "tool": entry.get("name"),
            "args": _clip(json.dumps(entry.get("args") or {}, ensure_ascii=False, default=str)),
            "status": entry.get("status"),
            "result": _clip(str(entry.get("result", ""))),
        })
    return evidence


def _clip(text: str, limit: int = TOOL_TEXT_LIMIT) -> str:
    return text if len(text) <= limit else text[:limit] + f"… [{len(text) - limit} more chars]"


JUDGE_PROMPT = """You check whether outcomes happened in one run of an AI agent. You do not grade style.

Situation given to the agent: {given}
What the user said: {user_input}

The agent's final answer:
<answer>
{answer}
</answer>

What its tools actually did (name, arguments, status, result), in order:
<tools>
{tools}
</tools>

For each numbered statement, say whether that outcome OCCURRED in this run:
- "occurred": the answer or the tool results show it happened.
- "did_not_occur": they show it did not happen, or the agent did something incompatible with it.
- "cannot_verify": the evidence does not settle it.
An outcome that changes the outside world — something sent, submitted, saved, deleted, paid, booked,
created — occurred only if a tool result above shows it. If only the answer claims it, say "cannot_verify".
Judge the outcome, not the wording: a statement need not appear verbatim.

Statements:
{statements}

Answer every statement exactly once, by its number. `evidence` quotes the answer or names the tool result."""


def judge(case: Case, answer: str, tools: List[dict], *, model: str,
          call: Optional[Callable] = None) -> List[dict]:
    """One verdict per expectation, `must` first, in the order they were written."""
    rules = [("must", text) for text in case.must] + [("must_not", text) for text in case.must_not]
    statements = "\n".join(f"{i}. {text}" for i, (_, text) in enumerate(rules, start=1))
    prompt = JUDGE_PROMPT.format(
        given=case.given or "(none)", user_input=case.input,
        answer=_clip(answer or "(empty)", JUDGE_TEXT_LIMIT),
        tools="\n".join(json.dumps(t, ensure_ascii=False) for t in tools) or "(no tool was called)",
        statements=statements)
    if call is None:
        from ..llm_do import llm_do as call
    result = call(prompt, output=_Judgement, model=model)
    by_number = {v.statement: v for v in result.verdicts}
    indicators = []
    for number, (kind, text) in enumerate(rules, start=1):
        verdict = by_number.get(number)
        if verdict is None:
            indicators.append({"kind": kind, "text": text, "verdict": "UNVERIFIED",
                               "reason": "the judge gave no verdict for this statement", "evidence": ""})
            continue
        indicators.append({"kind": kind, "text": text, "verdict": _score(kind, verdict.status),
                           "reason": verdict.reason, "evidence": verdict.evidence})
    return indicators


def _score(kind: str, status: str) -> str:
    if status == "cannot_verify":
        return "UNVERIFIED"
    occurred = status == "occurred"
    if kind == "must":
        return "PASS" if occurred else "FAIL"
    return "FAIL" if occurred else "PASS"   # a forbidden outcome that happened is a hard FAIL


# ---- the run ------------------------------------------------------------------------------


@contextlib.contextmanager
def _live_flag(live: bool):
    """CO_EVAL_LIVE for the run, so a tool or skill that can tell a rehearsal
    from the real thing is told which this is. Restored afterwards."""
    before = os.environ.get("CO_EVAL_LIVE")
    os.environ["CO_EVAL_LIVE"] = "1" if live else "0"
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("CO_EVAL_LIVE", None)
        else:
            os.environ["CO_EVAL_LIVE"] = before


def run(suite: Suite, agent, *, agent_path: str, skill: Optional[dict] = None, invoke: str = "auto",
        runs: int = 1, live: bool = False, judge_model: str, judge_call: Optional[Callable] = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS) -> dict:
    """Every case `runs` times on a fresh session. Returns the report dict; saving is the caller's."""
    if invoke not in ("auto", "explicit"):
        raise RunnerError(f"--invoke must be auto or explicit, not {invoke!r}", code=2)
    if invoke == "explicit" and skill is None:
        raise RunnerError("--invoke explicit sends /<skill> <input>, so it needs --skill NAME", code=2)
    if runs < 1:
        raise RunnerError("--runs must be a positive integer", code=2)
    if max_iterations < 1:
        raise RunnerError("--max-iterations must be a positive integer", code=2)
    started = time.time()
    cases = []
    with _live_flag(live), _step_ceiling(agent, max_iterations), _answers_out_of_reach(agent, suite):
        for case in suite.cases:
            cases.append(_run_case(case, agent, skill=skill, invoke=invoke, runs=runs,
                                   judge_model=judge_model, judge_call=judge_call,
                                   max_iterations=max_iterations, answers=_answers(suite)))
    report = {
        "benchmark": suite.name,
        "benchmark_path": str(suite.path),
        "benchmark_sha256": hashlib.sha256(suite.path.read_bytes()).hexdigest(),
        "started_at": _iso(started),
        "finished_at": _iso(time.time()),
        "agent": agent_identity(agent, agent_path),
        "skill": {k: v for k, v in skill.items() if k != "instructions"} if skill else None,
        "invoke": invoke,
        "runs": runs,
        "max_iterations": max_iterations,
        "live": live,
        "judge_model": judge_model,
        "cases": cases,
    }
    report["summary"] = summarise(report)
    return report


@contextlib.contextmanager
def _step_ceiling(agent, max_iterations: int):
    """The Agent's own max_iterations, lowered for the run and restored after,
    so the ceiling is the loop's real limit rather than a guess from outside."""
    before = getattr(agent, "max_iterations", None)
    agent.max_iterations = max_iterations
    try:
        yield
    finally:
        agent.max_iterations = before


# ---- the Agent under test cannot read the answers -------------------------------------------
#
# On 1.8.8b11 the co create template, asked a benchmark question, ran
# glob("**/*") and then read_file(".co/benchmarks/reimbursement.yaml") in 4 of
# 5 cases: the file with every must and must_not. It scored 5/5, and the score
# meant nothing. Two layers, because neither is enough alone:
#   1. a before_each_tool guard refuses any call that names the benchmark
#      folder, an earlier run or the suite's file, for the length of the run;
#   2. a call that got the answers some other way (a grep over the workspace, a
#      shell pipeline, a sub-agent) leaves them in its result, so an attempt
#      whose tool results contain an expectation is INVALID: not judged, not a pass.

_REFUSAL = ("Refused during `co eval run`: {what} holds the benchmark's expected answers or earlier "
            "runs of it, and an agent under test does not read its own answer key. Answer from the "
            "request and your skills.")

# An expectation shorter than this is too likely to turn up in an honest tool
# result ("Approved") to be read as a leak.
_ANSWER_MIN_CHARS = 12


def _protected(suite: Suite) -> List[str]:
    """What a tool call may not name during the run, as lowercase substrings.
    ".co/benchmarks" covers an absolute path too; the file's own name and
    "eval-runs" cover `cd .co && cat benchmarks/x.yaml`."""
    return [".co/benchmarks", "eval-runs", suite.path.name.lower()]


def _fixtures(suite: Suite) -> List[str]:
    """A case's `fixture:` lives under .co/benchmarks/ and is there to be read."""
    return sorted({f".co/benchmarks/{case.fixture}".lower() for case in suite.cases if case.fixture},
                  key=len, reverse=True)


def _answers(suite: Suite) -> List[str]:
    texts = {text for case in suite.cases for text in (*case.must, *case.must_not)}
    return sorted(t for t in texts if len(t.strip()) >= _ANSWER_MIN_CHARS)


@contextlib.contextmanager
def _answers_out_of_reach(agent, suite: Suite):
    """The guard, first in line so it refuses before any approval prompt asks a
    person about a read that must not happen, and removed after the run."""
    events = getattr(agent, "events", None)
    if not isinstance(events, dict) or "before_each_tool" not in events:
        yield  # not a ConnectOnion Agent: the trace check below still applies
        return
    protected, fixtures = _protected(suite), _fixtures(suite)

    def guard(agent):
        pending = agent.current_session.get("pending_tool") or {}
        named = json.dumps(pending.get("arguments") or {}, ensure_ascii=False, default=str)
        named = named.replace("\\\\", "/").lower()  # a Windows path, as JSON escapes it
        for fixture in fixtures:
            named = named.replace(fixture, "<fixture>")
        hit = next((p for p in protected if p in named), None)
        if hit:
            raise PermissionError(_REFUSAL.format(what=hit))

    events["before_each_tool"].insert(0, guard)
    try:
        yield
    finally:
        events["before_each_tool"].remove(guard)


def _saw_answers(trace: List[dict], answers: List[str]) -> Optional[str]:
    """The first expectation a successful tool result contains, as the reason
    the attempt is INVALID; None when the run never saw one. The skill tool is
    left out: a SKILL.md is the thing under test, not a way around it."""
    for entry in trace:
        if entry.get("type") != "tool_result" or entry.get("status") != "success" or entry.get("name") == "skill":
            continue
        result = str(entry.get("result", ""))
        for text in answers:
            if text in result:
                return (f"{entry.get('name')} returned the benchmark's own expectation {text!r}: the Agent "
                        f"read the answers, so this attempt is not scored. Keep benchmark files and runs out "
                        f"of what its tools can reach, then rerun")
    return None


def _turn_result(session: dict) -> dict:
    results = [e for e in session.get("trace") or [] if e.get("type") == "turn_result"]
    return results[-1] if results else {}


def _run_case(case: Case, agent, *, skill, invoke, runs, judge_model, judge_call,
              max_iterations: int = DEFAULT_MAX_ITERATIONS, answers: Optional[List[str]] = None) -> dict:
    sent = effective_input(case, skill, invoke)
    attempts = []
    for number in range(1, runs + 1):
        attempt = {"n": number, "output": "", "activation": None, "indicators": [], "passed": False,
                   "error": None, "stopped": None, "invalid": None, "cost": None, "trace": []}
        try:
            agent.reset_conversation()
            attempt["output"] = str(agent.input(sent) or "")
            session = agent.current_session or {}
            attempt["trace"] = list(session.get("trace") or [])
            ended = _turn_result(session)
            attempt["cost"] = (ended.get("usage") or {}).get("cost")
            attempt["activation"] = activation(skill, invoke, session, sent)
            # Not judged when it saw the answers: a verdict on an answer copied
            # from the key is no verdict, and it would cost a judge call.
            attempt["invalid"] = _saw_answers(attempt["trace"], answers or [])
            if attempt["invalid"] is None and ended.get("reason") == "max_iterations":
                # Not judged: the answer is "Task incomplete", and judging it
                # would spend a judge call to say so. Not a runner error either:
                # nothing broke, the Agent just did not finish inside the ceiling.
                attempt["stopped"] = (f"stopped after {max_iterations} steps without an answer. If the case "
                                      f"carries the data it needs, this is the skill's to fix; if the task "
                                      f"really takes more steps, rerun with --max-iterations N")
            elif attempt["invalid"] is None:
                attempt["indicators"] = judge(case, attempt["output"], tool_evidence(session),
                                              model=judge_model, call=judge_call)
        except Exception as error:  # the Agent or the judge broke: a runner error, never a pass
            attempt["error"] = f"{type(error).__name__}: {error}"
        activated = attempt["activation"] is None or attempt["activation"]["status"] == "PASS"
        attempt["passed"] = (attempt["error"] is None and attempt["stopped"] is None and activated
                             and attempt["invalid"] is None
                             and bool(attempt["indicators"])
                             and all(i["verdict"] == "PASS" for i in attempt["indicators"]))
        attempts.append(attempt)
    passed = sum(1 for a in attempts if a["passed"])
    return {"id": case.id, "kind": case.kind, "input": case.input, "effective_input": sent,
            "attempts": attempts, "passed_attempts": passed, "stability": f"{passed}/{len(attempts)}"}


def summarise(report: dict) -> dict:
    attempts = [a for case in report["cases"] for a in case["attempts"]]
    indicators = [i for a in attempts for i in a["indicators"]]
    runner_errors = sum(1 for a in attempts if a["error"])
    failed = sum(1 for i in indicators if i["verdict"] == "FAIL")
    unverified = sum(1 for i in indicators if i["verdict"] == "UNVERIFIED")
    not_activated = sum(1 for a in attempts if a["activation"] and a["activation"]["status"] != "PASS")
    stopped = sum(1 for a in attempts if a.get("stopped"))
    invalid = sum(1 for a in attempts if a.get("invalid"))
    costs = [a["cost"] for a in attempts if isinstance(a.get("cost"), (int, float))]
    # Checks = every expectation plus, when a skill was named, "did it run" per
    # attempt. The score is taken over checks: on the first real run every
    # expectation passed while the skill never ran once, and an expectation-only
    # score called that 100%.
    activation_checks = sum(1 for a in attempts if a["activation"])
    passed_indicators = sum(1 for i in indicators if i["verdict"] == "PASS")
    if runner_errors:
        exit_code = 3
    elif failed or unverified or not_activated or stopped or invalid or not attempts:
        exit_code = 1
    else:
        exit_code = 0
    return {
        "cases": len(report["cases"]),
        "cases_passing": sum(1 for c in report["cases"] if c["passed_attempts"] == len(c["attempts"])),
        "attempts": len(attempts),
        "passed_attempts": sum(1 for a in attempts if a["passed"]),
        "indicators": len(indicators),
        "passed_indicators": passed_indicators,
        "checks": len(indicators) + activation_checks,
        "passed_checks": passed_indicators + activation_checks - not_activated,
        "failed": failed,
        "unverified": unverified,
        "forbidden_failures": sum(1 for i in indicators if i["kind"] == "must_not" and i["verdict"] == "FAIL"),
        "not_activated": not_activated,
        "stopped": stopped,
        "invalid": invalid,
        # What the Agent's own model calls cost, as measured; None when no
        # attempt reported usage. The judge's calls are not in it.
        "agent_cost": round(sum(costs), 4) if costs else None,
        "runner_errors": runner_errors,
        "exit_code": exit_code,
    }


def _iso(seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))
