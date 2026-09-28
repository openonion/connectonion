"""A Google library's Python 3.10 notice must not print on every co command.

google.api_core warns, at import, that it will stop supporting Python 3.10 on
2026-10-04. On 1.8.9b19 every command that loaded a Google tool (co onenote
among them, through the tools package) printed that FutureWarning and its
source line above its own output. It is a note to the library's maintainers,
not something a co user can act on mid-command.
"""

import warnings

import connectonion.cli.main as cli_main


def _warn(message: str, module: str) -> list:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        cli_main._quiet_dependency_notices()
        warnings.warn_explicit(message, FutureWarning, "x.py", 1, module=module)
    return [str(w.message) for w in caught]


def test_the_cli_silences_the_google_python_version_notice():
    assert not _warn("You are using a Python version (3.10.21) which Google will stop supporting",
                     "google.api_core._python_version_support")


def test_other_future_warnings_still_show():
    assert _warn("something of ours changes", "connectonion.something")
