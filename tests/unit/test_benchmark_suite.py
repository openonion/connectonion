"""Unit tests for benchmark suite validation.

LLM-Note: Tests for connectonion.benchmark.suite

What it tests:
- A suite with >=5 distinct cases of both kinds is valid; the example printed by the CLI is itself valid
- Every rule breach is reported with its case, field and fix: too few, duplicate ids, identical inputs,
  a counterexample with nothing forbidden, no counterexample, unknown fields, a missing must
- A suite that pins an agent or a skill is refused; a name that is a path is refused
- list_suites summarises valid and invalid files

Components under test:
- Module: connectonion/benchmark/suite.py
"""

import yaml

from connectonion.benchmark import suite as s


def case(i, kind="normal", **extra):
    body = {"id": f"c{i}", "kind": kind, "input": f"request number {i}",
            "expect": {"must": [f"outcome {i} happens"]}}
    if kind == "counterexample":
        body["expect"]["must_not"] = [f"forbidden {i} happens"]
    body.update(extra)
    return body


def write(tmp_path, name, data):
    directory = tmp_path / ".co" / "benchmarks"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.yaml").write_text(yaml.safe_dump(data, sort_keys=False))


def good(n=5):
    return {"name": "x", "cases": [case(i) for i in range(1, n)] + [case(n, "counterexample")]}


def problems(tmp_path, data, name="x"):
    write(tmp_path, name, data)
    loaded, found = s.load(name, tmp_path)
    return loaded, [p.line() for p in found]


def test_five_distinct_cases_of_both_kinds_are_valid(tmp_path):
    loaded, found = problems(tmp_path, good())

    assert found == []
    assert loaded.counts() == {"normal": 4, "counterexample": 1}


def test_the_example_the_cli_prints_is_a_valid_shape_once_it_has_five_cases(tmp_path):
    example = yaml.safe_load(s.EXAMPLE)
    example["cases"] += [case(i) for i in range(3, 6)]

    assert problems(tmp_path, example)[1] == []


def test_the_printed_example_is_valid_as_printed_and_each_case_carries_its_data(tmp_path):
    # 1.8.8b9 printed "Please process these three invoices" with no invoices;
    # run as printed, the Agent searched the workspace for them at 20 cents a case.
    (tmp_path / ".co" / "benchmarks").mkdir(parents=True)
    (tmp_path / ".co" / "benchmarks" / "reimbursement.yaml").write_text(s.EXAMPLE)

    loaded, found = s.load("reimbursement", tmp_path)

    assert found == [] and loaded is not None
    for c in loaded.cases:
        assert "INV-" in c.input and "buyer" in c.input, c.id
        # Every outcome is one the reply shows: nothing needs a tool that
        # changes the world, so an unconfigured Agent can pass it honestly.
        assert all(text.startswith("The reply") for text in c.must + c.must_not), c.id


def test_fewer_than_five_is_refused_with_how_many_to_add(tmp_path):
    _, found = problems(tmp_path, good(4))

    assert any("only 4 valid case(s)" in line and "at least 5" in line for line in found)


def test_a_duplicate_id_and_an_identical_input_are_both_named(tmp_path):
    data = good(6)
    data["cases"][1]["id"] = "c1"
    data["cases"][2]["input"] = "Request   number 1"  # same decision, different spacing and case

    _, found = problems(tmp_path, data)

    assert any(line.startswith("c1 · id: duplicate id") for line in found)
    assert any("same input as c1" in line for line in found)


def test_a_counterexample_must_forbid_something(tmp_path):
    data = good()
    del data["cases"][-1]["expect"]["must_not"]

    _, found = problems(tmp_path, data)

    assert any("c5 · expect.must_not: is a counterexample with nothing forbidden" in line for line in found)


def test_a_suite_with_no_counterexample_is_refused(tmp_path):
    _, found = problems(tmp_path, {"cases": [case(i) for i in range(1, 7)]})

    assert any("no counterexample" in line for line in found)


def test_a_benchmark_does_not_choose_the_agent_or_the_skill(tmp_path):
    data = good()
    data["agent"] = "agent.py"
    data["skill"] = "refund"

    _, found = problems(tmp_path, data)

    assert any("agent: a benchmark does not choose the agent" in line and "--agent" in line for line in found)
    assert any("skill: a benchmark does not choose the skill" in line for line in found)


def test_unknown_fields_and_a_missing_must_are_named_with_their_case(tmp_path):
    data = good()
    data["cases"][0]["expected"] = "typo"
    data["cases"][1]["expect"] = {"must_not": ["x"]}

    _, found = problems(tmp_path, data)

    assert any(line.startswith("c1 · expected: unknown field") for line in found)
    assert any(line.startswith("c2 · expect.must: has no must outcome") for line in found)


def test_a_name_that_is_a_path_is_not_resolved(tmp_path):
    loaded, found = s.load("../secrets", tmp_path)

    assert loaded is None and "not a benchmark name" in found[0].reason


def test_a_missing_file_says_where_it_looked_and_what_to_run(tmp_path):
    loaded, found = s.load("nope", tmp_path)

    assert loaded is None
    assert "nope.yaml does not exist" in found[0].reason and "co benchmark check nope" in found[0].fix


def test_list_reports_valid_and_invalid_suites(tmp_path):
    write(tmp_path, "good", good())
    write(tmp_path, "bad", {"cases": []})

    rows = {row["name"]: row for row in s.list_suites(tmp_path)}

    assert rows["good"]["valid"] is True and rows["good"]["cases"] == 5
    assert rows["bad"]["valid"] is False and rows["bad"]["problems"] == 1
