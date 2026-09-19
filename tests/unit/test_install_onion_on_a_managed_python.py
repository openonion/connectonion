"""pip refusing by policy is not the same failure as pip breaking.

Measured on the Intel acceptance Mac, 2026-09-12, with `co` installed into
Homebrew's python@3.13:

    Could not install Onionwright: pip could not install Onionwright (exit 1).

pip's own text above it said `externally-managed-environment` — a policy the OS
applies to its own interpreter, which every Homebrew and system Python applies
too. The line a reader ends on, and the only line an agent parses, named an exit
code instead. So the next move looks like "the download is broken" when it is
"this interpreter does not accept writes without an explicit override".

`co` itself lives in that interpreter, and Onionwright has to be importable by
the same one, so a virtualenv is a real answer only if `co` moves there too.
Both routes are named; neither is chosen for the caller, because the flag
overrides a guard somebody put there on purpose.
"""

import subprocess
import sys

import pytest

from connectonion.cli.commands import browser_commands
from connectonion.cli.commands.onionwright_install import _install_failure_advice

PIP_REFUSAL = """error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, try brew install ...
"""


def _completed(stderr="", stdout="", returncode=1):
    return subprocess.CompletedProcess(
        args=["pip"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_a_policy_refusal_is_named_as_one():
    advice = _install_failure_advice(_completed(stderr=PIP_REFUSAL), False)

    assert "externally managed" in advice
    assert "exit 1" not in advice, "the exit code is the least useful thing here"


def test_it_names_the_interpreter_the_reader_has_to_decide_about():
    advice = _install_failure_advice(_completed(stderr=PIP_REFUSAL), False)

    assert sys.executable in advice


def test_it_names_both_routes_and_picks_neither():
    advice = _install_failure_advice(_completed(stderr=PIP_REFUSAL), False)

    assert "co browser install-onion --break-system-packages" in advice
    assert "venv" in advice


def test_pips_own_words_are_kept():
    """Never summarise away the upstream text; it is the evidence."""
    advice = _install_failure_advice(_completed(stderr=PIP_REFUSAL), False)

    assert "externally-managed-environment" in advice


def test_an_ordinary_failure_still_reads_as_one():
    advice = _install_failure_advice(_completed(stderr="No space left on device"), False)

    assert "exit 1" in advice
    assert "--break-system-packages" not in advice, "do not offer a flag that cannot help"
    assert "No space left on device" in advice


def test_the_flag_is_not_re_offered_after_it_was_already_used():
    """If the override was on and pip still refused, repeating it is a loop."""
    advice = _install_failure_advice(_completed(stderr=PIP_REFUSAL), True)

    assert "--break-system-packages" not in advice


@pytest.mark.parametrize(
    "args,expected_override",
    [(["install-onion"], False), (["install-onion", "--break-system-packages"], True)],
)
def test_the_cli_passes_the_choice_through(monkeypatch, args, expected_override):
    seen = {}

    class _Result:
        version, already_installed = "0.0.14", False

    monkeypatch.setattr(
        "connectonion.cli.commands.onionwright_install.install_onionwright",
        lambda **kw: seen.update(kw) or _Result(),
    )

    assert browser_commands.handle_browser(list(args)) == 0
    assert seen == {"break_system_packages": expected_override}


def test_an_unknown_flag_is_still_a_usage_error(capsys):
    assert browser_commands.handle_browser(["install-onion", "--yolo"]) == 2

    usage = capsys.readouterr().err
    assert "--break-system-packages" in usage, "usage must list what IS accepted"
