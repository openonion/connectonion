"""Versioned Jira Skill benchmark standards stay structurally valid.

Runtime benchmark files live under .co/benchmarks/ and are intentionally ignored;
these fixtures are the reviewable source copied into that location for evaluation.
"""

from pathlib import Path

from connectonion.benchmark import suite


ROOT = Path(__file__).parents[2]


def test_jira_cli_skill_benchmark_is_valid():
    loaded, problems = suite.load("jira-cli-skill", ROOT)

    assert problems == []
    assert loaded is not None
    assert loaded.counts() == {"normal": 4, "counterexample": 2}


def test_rem_source_jira_skill_benchmark_is_valid():
    loaded, problems = suite.load("rem-source-jira-skill", ROOT)

    assert problems == []
    assert loaded is not None
    assert loaded.counts() == {"normal": 4, "counterexample": 2}
