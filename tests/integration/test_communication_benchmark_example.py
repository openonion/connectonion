"""Keep the communication example's authored benchmark suites runnable."""

from pathlib import Path

import pytest

from connectonion.benchmark.suite import load


PROJECT = Path(__file__).resolve().parents[2] / "examples" / "communication-benchmark"


@pytest.mark.parametrize("name", ["email", "message-reply"])
def test_communication_benchmark_suite_is_valid(name):
    suite, problems = load(name, root=PROJECT)

    assert problems == []
    assert suite is not None
    assert len(suite.cases) >= 5
    assert all(suite.counts().values())
