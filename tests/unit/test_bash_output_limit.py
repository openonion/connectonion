"""Unit tests for the bash tool's output limit."""

import importlib
from subprocess import CompletedProcess

import pytest

# ``connectonion.useful_tools.bash`` is also the name of the exported function,
# so go through importlib to get the module itself.
bash_module = importlib.import_module("connectonion.useful_tools.bash")


def _fake_run(stdout="", stderr="", returncode=0):
    def run(*args, **kwargs):
        return CompletedProcess(args[0], returncode, stdout, stderr)

    return run


@pytest.fixture
def fake_subprocess(monkeypatch):
    def install(stdout="", stderr="", returncode=0):
        monkeypatch.setattr(
            bash_module,
            "subprocess",
            type("FakeSubprocess", (), {"run": staticmethod(_fake_run(stdout, stderr, returncode))}),
        )

    return install


def test_huge_stdout_keeps_the_exit_code(fake_subprocess):
    fake_subprocess(stdout="x" * 12000, returncode=3)

    result = bash_module.bash("failing-command")

    assert "Exit code: 3" in result
    assert "stdout truncated" in result
    assert len(result) <= bash_module.MAX_OUTPUT_CHARS


def test_huge_stderr_keeps_the_error_and_the_exit_code(fake_subprocess):
    fake_subprocess(stderr="e" * 12000, returncode=1)

    result = bash_module.bash("failing-command")

    assert result.startswith("STDERR:")
    assert "stderr truncated" in result
    assert "Exit code: 1" in result
    assert len(result) <= bash_module.MAX_OUTPUT_CHARS


def test_short_output_is_returned_unchanged(fake_subprocess):
    fake_subprocess(stdout="hi\n")

    assert bash_module.bash("echo hi") == "hi"


def test_empty_output_has_a_placeholder(fake_subprocess):
    fake_subprocess()

    assert bash_module.bash("true") == "(no output)"


def test_stdout_and_stderr_together_stay_under_the_limit(fake_subprocess):
    fake_subprocess(stdout="x" * 9000, stderr="e" * 9000, returncode=2)

    result = bash_module.bash("failing-command")

    assert "Exit code: 2" in result
    assert len(result) <= bash_module.MAX_OUTPUT_CHARS


def test_a_stderr_that_fills_the_cap_still_leaves_the_stdout_notice(fake_subprocess):
    # Both streams overflow and stderr alone would consume the whole budget.
    # stdout must still be announced, not silently dropped.
    fake_subprocess(stdout="x" * 12000, stderr="e" * 12000, returncode=1)

    result = bash_module.bash("failing-command")

    assert "stdout truncated" in result
    assert "stderr truncated" in result
    assert "Exit code: 1" in result
    assert len(result) <= bash_module.MAX_OUTPUT_CHARS


def test_a_huge_stderr_does_not_swallow_stdout(fake_subprocess):
    fake_subprocess(stdout="important result\n" * 100, stderr="e" * 12000, returncode=1)

    result = bash_module.bash("failing-command")

    assert "important result" in result
    assert result.index("important result") < result.index("STDERR:")


def test_failure_without_output_still_reports_the_exit_code(fake_subprocess):
    fake_subprocess(returncode=1)

    result = bash_module.bash("false")

    assert result.strip() == "Exit code: 1"
    assert "(no output)" not in result
