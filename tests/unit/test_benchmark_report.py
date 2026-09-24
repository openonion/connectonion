"""Unit tests for saved benchmark reports.

LLM-Note: Tests for connectonion.benchmark.report

What it tests:
- runs saved in quick succession come back in the order they were saved, so "the run before" is the run before
- a run is a new directory each time, its report is read-only and its traces sit beside it
- compare() names score change, newly passing/failing cases and a forbidden outcome that returned

Components under test:
- Module: connectonion/benchmark/report.py
"""

import stat

from connectonion.benchmark import report


def fake_report(passed: bool, forbidden: bool = False):
    verdict = "PASS" if passed else "FAIL"
    indicators = [{"kind": "must", "text": "done", "verdict": verdict, "reason": "", "evidence": ""},
                  {"kind": "must_not", "text": "harm", "verdict": "FAIL" if forbidden else "PASS",
                   "reason": "", "evidence": ""}]
    attempt = {"n": 1, "output": "o", "activation": None, "indicators": indicators,
               "passed": passed and not forbidden, "error": None, "trace": [{"type": "user_input"}]}
    case = {"id": "c1", "kind": "counterexample", "input": "i", "effective_input": "i", "attempts": [attempt],
            "passed_attempts": int(attempt["passed"]), "stability": f"{int(attempt['passed'])}/1"}
    body = {"benchmark": "b", "benchmark_sha256": "same", "agent": {"path": "agent.py", "model": "m"},
            "skill": None, "invoke": "auto", "runs": 1, "live": False, "cases": [case]}
    passed_count = sum(1 for i in indicators if i["verdict"] == "PASS")
    body["summary"] = {"cases": 1, "cases_passing": int(attempt["passed"]), "attempts": 1,
                       "passed_attempts": int(attempt["passed"]), "indicators": 2, "passed_indicators": passed_count,
                       "failed": 2 - passed_count, "unverified": 0, "forbidden_failures": int(forbidden),
                       "not_activated": 0, "runner_errors": 0, "exit_code": 0 if attempt["passed"] else 1}
    return body


def test_runs_saved_back_to_back_keep_their_order(tmp_path):
    saved = [report.save(fake_report(True), tmp_path).parent.name for _ in range(20)]

    assert report.run_ids("b", tmp_path) == saved


def test_a_saved_run_is_read_only_with_its_traces_beside_it(tmp_path):
    path = report.save(fake_report(True), tmp_path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o444
    loaded = report.load("b", root=tmp_path)
    trace_file = loaded["cases"][0]["attempts"][0]["trace_file"]
    assert trace_file.startswith(str(path.parent / "traces")) and "trace" not in loaded["cases"][0]["attempts"][0]


def test_compare_names_what_flipped_and_what_came_back(tmp_path):
    report.save(fake_report(True), tmp_path)
    second = report.save(fake_report(False, forbidden=True), tmp_path)

    current = report.load("b", second.parent.name, tmp_path)
    change = report.compare(current, report.previous("b", current["run_id"], tmp_path))

    assert change["score"] == 0.0 and change["previous_score"] == 1.0 and change["delta"] == -1.0
    assert change["newly_failing"] == ["c1"] and change["forbidden_regressions"] == ["c1: harm"]
    assert "newly failing: c1" in report.render(current, change)


def test_the_first_run_has_nothing_to_compare_with(tmp_path):
    first = report.save(fake_report(True), tmp_path)

    assert report.previous("b", first.parent.name, tmp_path) is None


def test_a_run_where_the_skill_never_ran_does_not_score_as_perfect(tmp_path):
    # Found on the first real run: every case failed on activation, every
    # expectation passed, and the comparison called that run 100%.
    unactivated = fake_report(True)
    unactivated["cases"][0]["attempts"][0]["activation"] = {"status": "FAIL", "evidence": "never called"}
    unactivated["summary"].update({"checks": 3, "passed_checks": 2, "not_activated": 1})
    report.save(unactivated, tmp_path)
    second = report.save(fake_report(True), tmp_path)

    current = report.load("b", second.parent.name, tmp_path)
    change = report.compare(current, report.previous("b", current["run_id"], tmp_path))

    assert change["previous_score"] == round(2 / 3, 4)


def test_a_comparison_across_a_different_setup_says_so(tmp_path):
    first = fake_report(True)
    first["invoke"] = "auto"
    report.save(first, tmp_path)
    second_body = fake_report(True)
    second_body["invoke"] = "explicit"
    second_body["agent"] = {"path": "agent.py", "model": "other-model"}
    second = report.save(second_body, tmp_path)

    current = report.load("b", second.parent.name, tmp_path)
    change = report.compare(current, report.previous("b", current["run_id"], tmp_path))

    assert change["setup_changed"] == ["invoke auto → explicit", "model m → other-model"]
    assert "not the same setup" in report.render(current, change)
