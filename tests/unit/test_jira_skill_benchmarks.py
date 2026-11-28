"""Versioned Jira Skill benchmark standards stay structurally valid.

Runtime benchmark files live under .co/benchmarks/ and are intentionally ignored;
these fixtures are the reviewable source copied into that location for evaluation.
"""

from pathlib import Path

from connectonion.benchmark import suite


ROOT = Path(__file__).parents[2]


def _load(name, tmp_path):
    target = tmp_path / '.co' / 'benchmarks'
    target.mkdir(parents=True)
    (target / f'{name}.yaml').write_text((ROOT / 'benchmarks' / f'{name}.yaml').read_text(encoding='utf-8'), encoding='utf-8')
    return suite.load(name, tmp_path)


def test_jira_cli_skill_benchmark_is_valid(tmp_path):
    loaded, problems = _load("jira-cli-skill", tmp_path)

    assert problems == []
    assert loaded is not None
    assert loaded.counts() == {"normal": 4, "counterexample": 2}


def test_rem_source_jira_skill_benchmark_is_valid(tmp_path):
    loaded, problems = _load("rem-source-jira-skill", tmp_path)

    assert problems == []
    assert loaded is not None
    assert loaded.counts() == {"normal": 4, "counterexample": 2}
