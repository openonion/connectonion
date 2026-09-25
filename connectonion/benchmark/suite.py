"""
Purpose: Read and validate `.co/benchmarks/<name>.yaml` — the frozen standard a skill is measured against
LLM-Note:
  Dependencies: imports from [re, dataclasses, pathlib, yaml] | imported by [benchmark/__init__.py, benchmark/runner.py, cli/commands/benchmark_commands.py] | tested by [tests/unit/test_benchmark_suite.py]
  Data flow: name → benchmark_path() → yaml.safe_load → Case list + Problem list | list_suites() summarises every *.yaml under the directory
  State/Effects: read-only; never runs an Agent, never touches .co/eval-runs
  Integration: `co benchmark check/list` print these; `co eval run` refuses a suite with any problem
  Errors: every rule breach is a Problem(case_id, field, reason, fix) rather than an exception, so the CLI can print all of them at once and --json can hand them to an agent

A benchmark is a test dataset, not a runner and not a skill: it names no Agent
and no skill, so the same cases can compare two Agents or two versions of one
skill without the gold standard moving. #1642 has the argument.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

MIN_CASES = 5
KINDS = ("normal", "counterexample")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_CASE_KEYS = {"id", "kind", "given", "input", "fixture", "expect"}
_EXPECT_KEYS = {"must", "must_not"}

# The smallest file that passes `check`, printed wherever a suite is missing or
# empty, so an agent never has to go and find the schema somewhere else. It has
# to really pass: 1.8.8b7 printed two cases under "the smallest valid one" and
# `check` then refused the copy for having fewer than MIN_CASES.
#
# It also has to be cheap to run as printed. 1.8.8b9's cases said "process
# these three invoices" without any invoices: the co create agent searched the
# workspace for them, up to 26 steps a case, and one run cost a new user $1.
# Every input below carries the data a correct answer needs, and every
# expectation is something the reply itself shows, so the first run measures
# the skill rather than a search, and needs no tool that changes anything.
EXAMPLE = """\
name: reimbursement
cases:
  - id: clean-batch
    kind: normal
    input: "Our company is OpenOnion Pty Ltd. Which of these can be submitted for approval? INV-101 buyer OpenOnion Pty Ltd $120, receipt attached; INV-102 buyer OpenOnion Pty Ltd $80, receipt attached; INV-103 buyer OpenOnion Pty Ltd $45, receipt attached"
    expect:
      must:
        - "The reply says INV-101, INV-102 and INV-103 can all be submitted"
  - id: title-mismatch
    kind: counterexample
    input: "Our company is OpenOnion Pty Ltd. Which of these can be submitted for approval? INV-201 buyer OpenOnion Pty Ltd $60, receipt attached; INV-202 buyer Open Onion Trading Co $95, receipt attached"
    expect:
      must:
        - "The reply flags INV-202 because its buyer is not OpenOnion Pty Ltd"
      must_not:
        - "The reply says INV-202 can be submitted"
  - id: duplicate-invoice
    kind: counterexample
    input: "Our company is OpenOnion Pty Ltd. INV-204 was submitted on 3 August. Can this be submitted for approval? INV-204 buyer OpenOnion Pty Ltd $90, receipt attached"
    expect:
      must:
        - "The reply says INV-204 was already submitted on 3 August"
      must_not:
        - "The reply says INV-204 can be submitted again"
  - id: single-invoice
    kind: normal
    input: "Our company is OpenOnion Pty Ltd. Can this be submitted for approval? INV-310 buyer OpenOnion Pty Ltd $210, receipt attached"
    expect:
      must:
        - "The reply says INV-310 can be submitted"
  - id: missing-receipt
    kind: normal
    input: "Our company is OpenOnion Pty Ltd. Which of these can be submitted for approval? INV-401 buyer OpenOnion Pty Ltd $70, receipt attached; INV-402 buyer OpenOnion Pty Ltd $150, no receipt"
    expect:
      must:
        - "The reply says INV-401 can be submitted and asks for INV-402's receipt"
  # Every case is a different decision; at least 5, at least one of each kind.
  # Put the data a case needs in its input: an Agent without it goes looking,
  # and every step it spends looking is paid for.
"""


@dataclass
class Case:
    id: str
    kind: str
    input: str
    must: List[str]
    must_not: List[str] = field(default_factory=list)
    given: str = ""
    fixture: str = ""


@dataclass
class Problem:
    """One reason a suite cannot be run, and what to do about it."""

    reason: str
    fix: str
    case_id: str = ""
    field: str = ""

    def as_dict(self) -> dict:
        return {"case_id": self.case_id, "field": self.field, "reason": self.reason, "fix": self.fix}

    def line(self) -> str:
        where = " · ".join(part for part in (self.case_id, self.field) if part)
        return f"{where + ': ' if where else ''}{self.reason} — {self.fix}"


@dataclass
class Suite:
    name: str
    path: Path
    cases: List[Case]

    def counts(self) -> dict:
        return {kind: sum(1 for c in self.cases if c.kind == kind) for kind in KINDS}


def benchmark_dir(root: Optional[Path] = None) -> Path:
    return (root or Path.cwd()) / ".co" / "benchmarks"


def benchmark_path(name: str, root: Optional[Path] = None) -> Path:
    return benchmark_dir(root) / f"{name}.yaml"


def load(name: str, root: Optional[Path] = None) -> Tuple[Optional[Suite], List[Problem]]:
    """The suite and every problem with it. A suite comes back only if it has none."""
    if not _NAME.match(name or ""):
        return None, [Problem(f"{name!r} is not a benchmark name",
                              "pass the file stem of .co/benchmarks/<name>.yaml, not a path or a glob")]
    path = benchmark_path(name, root)
    if not path.exists():
        return None, [Problem(f"{path} does not exist",
                              f"create it (schema: co benchmark --help), then co benchmark check {name}")]
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        return None, [Problem(f"{path} is not valid YAML: {error}".replace("\n", " "),
                              "fix the YAML; a value containing ': ' or '#' needs quotes")]
    problems: List[Problem] = []
    cases = _cases(data, problems)
    problems.extend(_suite_rules(cases, path))
    if problems:
        return None, problems
    return Suite(name=name, path=path, cases=cases), []


def _cases(data, problems: List[Problem]) -> List[Case]:
    if not isinstance(data, dict):
        problems.append(Problem("the file is not a mapping with a `cases:` list",
                                "start from the example in co benchmark --help"))
        return []
    for pinned in ("agent", "skill"):
        if pinned in data:
            problems.append(Problem(
                f"a benchmark does not choose the {pinned}", f"delete `{pinned}:` and pass "
                f"--{pinned} to co eval run instead; the same cases must be able to compare two",
                field=pinned))
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        problems.append(Problem("`cases:` is missing or empty",
                                f"add at least {MIN_CASES} cases; see co benchmark --help",
                                field="cases"))
        return []
    cases = []
    for index, raw in enumerate(raw_cases, start=1):
        case = _case(raw, index, problems)
        if case is not None:
            cases.append(case)
    return cases


def _case(raw, index: int, problems: List[Problem]) -> Optional[Case]:
    label = f"case {index}"
    if not isinstance(raw, dict):
        problems.append(Problem("is not a mapping", "write it as `- id: ...` with the fields below it",
                                case_id=label))
        return None
    case_id = str(raw.get("id") or "").strip()
    label = case_id or label
    before = len(problems)
    if not case_id:
        problems.append(Problem("has no id", "add a short unique `id:` such as mixed-batch", case_id=label, field="id"))
    for key in sorted(set(raw) - _CASE_KEYS):
        problems.append(Problem(f"unknown field `{key}`",
                                f"use only {', '.join(sorted(_CASE_KEYS))}", case_id=label, field=key))
    kind = str(raw.get("kind") or "").strip()
    if kind not in KINDS:
        problems.append(Problem(f"kind is {kind or 'missing'!r}", "set `kind: normal` or `kind: counterexample`",
                                case_id=label, field="kind"))
    text = raw.get("input")
    if not isinstance(text, str) or not text.strip():
        problems.append(Problem("has no input", "add `input:` — exactly what the user says to the Agent",
                                case_id=label, field="input"))
    expect = raw.get("expect")
    if not isinstance(expect, dict):
        problems.append(Problem("has no expect", "add `expect:` with a `must:` list of outcomes",
                                case_id=label, field="expect"))
        expect = {}
    for key in sorted(set(expect) - _EXPECT_KEYS):
        problems.append(Problem(f"unknown field `expect.{key}`", "use expect.must and expect.must_not",
                                case_id=label, field=f"expect.{key}"))
    must = _rules(expect.get("must"), label, "expect.must", problems)
    must_not = _rules(expect.get("must_not"), label, "expect.must_not", problems)
    if not must:
        problems.append(Problem("has no must outcome", "list at least one user-observable outcome under expect.must",
                                case_id=label, field="expect.must"))
    if kind == "counterexample" and not must_not:
        problems.append(Problem("is a counterexample with nothing forbidden",
                                "list what must NOT happen under expect.must_not", case_id=label,
                                field="expect.must_not"))
    if len(problems) > before:
        return None
    return Case(id=case_id, kind=kind, input=text.strip(), must=must, must_not=must_not,
                given=str(raw.get("given") or "").strip(), fixture=str(raw.get("fixture") or "").strip())


def _rules(value, label: str, name: str, problems: List[Problem]) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        problems.append(Problem(f"{name} must be a list of sentences", f"write {name} as `- \"...\"` lines",
                                case_id=label, field=name))
        return []
    return [v.strip() for v in value]


def _suite_rules(cases: List[Case], path: Path) -> List[Problem]:
    problems = []
    seen_ids, seen_inputs = {}, {}
    for case in cases:
        if case.id in seen_ids:
            problems.append(Problem("duplicate id", "give every case its own id", case_id=case.id, field="id"))
        seen_ids[case.id] = True
        # Five paraphrases of one decision are one case. Structure cannot prove
        # the decisions differ; an identical input proves they do not.
        normalized = " ".join(case.input.lower().split())
        if normalized in seen_inputs and seen_inputs[normalized] != case.id:
            problems.append(Problem(f"same input as {seen_inputs[normalized]}",
                                    "make each case a different decision, not the same request twice",
                                    case_id=case.id, field="input"))
        seen_inputs.setdefault(normalized, case.id)
        if case.fixture and not (path.parent / case.fixture).exists() and not Path(case.fixture).exists():
            problems.append(Problem(f"fixture {case.fixture} does not exist",
                                    "fix the path (relative to .co/benchmarks/) or remove `fixture:`",
                                    case_id=case.id, field="fixture"))
    if cases and len(cases) < MIN_CASES:
        problems.append(Problem(f"only {len(cases)} valid case(s)",
                                f"write at least {MIN_CASES} distinct decisions", field="cases"))
    kinds = {case.kind for case in cases}
    if cases and "counterexample" not in kinds:
        problems.append(Problem("no counterexample", "add a case where the right answer is to refuse, stop or flag",
                                field="cases"))
    if cases and "normal" not in kinds:
        problems.append(Problem("no normal case", "add a case where the task simply succeeds", field="cases"))
    return problems


def list_suites(root: Optional[Path] = None) -> List[dict]:
    """Every *.yaml under .co/benchmarks: name, path, case count, and whether it is valid."""
    directory = benchmark_dir(root)
    if not directory.is_dir():
        return []
    rows = []
    for path in sorted(directory.glob("*.yaml")):
        suite, problems = load(path.stem, root)
        rows.append({
            "name": path.stem,
            "path": str(path),
            "cases": len(suite.cases) if suite else None,
            "valid": suite is not None,
            "problems": len(problems),
        })
    return rows
