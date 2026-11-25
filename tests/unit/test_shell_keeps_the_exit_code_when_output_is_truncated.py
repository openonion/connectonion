"""Unit tests for the Shell tool's output limit.

`Shell._format_output` cut the finished string at 10,000 characters, and the
`Exit code:` line is appended last. A command that printed a lot therefore
reached the agent with no exit status at all, which reads as a truncated
success. These tests pin the streams to the cap and the tool's own lines
outside it.
"""

import importlib
from subprocess import CompletedProcess

import pytest

# ``connectonion.useful_tools.shell`` is also the name of the module holding the
# Shell class, so go through importlib to get the module itself.
shell_module = importlib.import_module("connectonion.useful_tools.shell")


@pytest.fixture
def fake_subprocess(monkeypatch):
    def install(stdout="", stderr="", returncode=0):
        def run(*args, **kwargs):
            return CompletedProcess(args[0], returncode, stdout, stderr)

        monkeypatch.setattr(shell_module.subprocess, "run", run)

    return install


def test_huge_stdout_keeps_the_exit_code(fake_subprocess):
    fake_subprocess(stdout="x" * 12000, returncode=3)

    result = shell_module.Shell().run("failing-command")

    assert "Exit code: 3" in result
    assert "stdout truncated" in result
    assert len(result) <= shell_module.MAX_OUTPUT_CHARS


def test_huge_stderr_keeps_the_error_and_the_exit_code(fake_subprocess):
    fake_subprocess(stderr="e" * 12000, returncode=1)

    result = shell_module.Shell().run("failing-command")

    assert result.startswith("STDERR:")
    assert "stderr truncated" in result
    assert "Exit code: 1" in result
    assert len(result) <= shell_module.MAX_OUTPUT_CHARS


def test_stderr_survives_a_huge_stdout(fake_subprocess):
    fake_subprocess(stdout="x" * 12000, stderr="real error", returncode=1)

    result = shell_module.Shell().run("noisy-failure")

    assert "real error" in result
    assert "Exit code: 1" in result
    assert len(result) <= shell_module.MAX_OUTPUT_CHARS


def test_short_output_is_returned_unchanged(fake_subprocess):
    fake_subprocess(stdout="hi\n")

    assert shell_module.Shell().run("echo hi") == "hi"


def test_empty_output_has_a_placeholder(fake_subprocess):
    fake_subprocess()

    assert shell_module.Shell().run("true") == "(no output)"


def test_run_in_dir_formats_the_same_way(fake_subprocess):
    fake_subprocess(stdout="x" * 12000, returncode=2)

    result = shell_module.Shell().run_in_dir("failing-command", ".")

    assert "Exit code: 2" in result
    assert len(result) <= shell_module.MAX_OUTPUT_CHARS


def test_a_return_code_with_no_output_is_still_reported(fake_subprocess):
    fake_subprocess(returncode=7)

    assert shell_module.Shell().run("exit 7") == "Exit code: 7"
