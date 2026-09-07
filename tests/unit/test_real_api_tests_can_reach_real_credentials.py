"""A test that must reach a real provider has to see the real credential store.

`_never_touch_the_real_home` repoints HOME at a temp directory for every test.
It earns that: a mocked-HTTP run of `co auth microsoft` once wrote fake tokens
into the operator's real `~/.co/keys.env` and surfaced days later as "Microsoft
session expired" — the last thing anyone traces back to a test run.

But provider CLIs keep their credentials under `$HOME` too. `codex` stores an
OAuth session in `~/.codex/auth.json`; with HOME repointed it finds nothing and
the turn dies at the provider:

    tests/e2e/real_api/test_real_codex.py::test_real_codex_session_resume
    turn failed: unexpected status 401 Unauthorized:
    Missing bearer or basic authentication in header

Confirmed by changing one variable and nothing else: the identical `codex()`
call succeeded with the operator's HOME (from two different working
directories) and produced that exact 401 with HOME pointed at a temp dir.

So the rule is not "isolate HOME" but "isolate HOME for tests that must not
touch it". A `real_api` test is the stated exception: reaching the operator's
real account is its entire purpose, it is opt-in behind a marker, and it is
deselected from the default run.

Both halves are asserted from inside real tests rather than by inspecting the
fixture, so they exercise the contract the suite actually runs under.
"""

import os
import pwd
from pathlib import Path

import pytest

# The operator's real home, read from the password database so it is unaffected
# by whatever HOME this test itself was given.
OPERATOR_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)


def test_an_ordinary_test_is_isolated_from_the_real_home():
    """The protection every other test depends on, asserted from inside one."""
    assert Path.home() != OPERATOR_HOME, (
        "an ordinary test can see the operator's real home — the guard that "
        "stopped a test from overwriting live OAuth tokens is not running"
    )
    assert os.environ["HOME"] != str(OPERATOR_HOME)


@pytest.mark.real_api
def test_a_real_api_test_keeps_the_operator_home():
    """A provider test must find ~/.codex, ~/.claude, ~/.co as they really are."""
    assert Path.home() == OPERATOR_HOME, (
        "a real_api test was given a temp HOME, so a provider CLI storing its "
        "credentials under $HOME cannot authenticate — this is the 401 that "
        "blocked the real Codex resume gate"
    )
    assert os.environ["HOME"] == str(OPERATOR_HOME)
