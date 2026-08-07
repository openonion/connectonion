"""The daemon-restart command we hand out kills the shell that runs it.

Shipped in three places, identically:

    pkill -f connectonion.cli.browser_agent.daemon

`pkill -f` matches against the whole command line of every process. A shell
invoked as `bash -c "pkill -f connectonion.cli.browser_agent.daemon"` has that
string in its own command line, so it matches itself and dies. Measured on a
real Linux box:

    $ bash -c "pkill -f connectonion.cli.browser_agent.daemon; echo SURVIVED"
    (no output — the shell was killed before echo)

    $ bash -c "pkill -f connectonion.cli.browser_agent[.]daemon; echo SURVIVED"
    SURVIVED

Both forms do kill the daemon. The difference is everything after it in the same
shell, which never runs.

That matters because of WHO these instructions are for. One of the three copies
is useful_skills/co-browser/SKILL.md — a file written to be executed by an
agent, which runs its commands exactly this way. The remedy for a stuck daemon
takes out the session trying to apply it, and reports nothing.

The bracketed character class is the standard fix: `[.]` matches a literal dot,
and the pattern text no longer contains the string it searches for.

It also mismeasures. `pgrep -f browser_agent.daemon | wc -l` counts the shell
running it, so a check for "is the daemon gone" reads 1 when the answer is 0 —
which is how the first reading of this was wrong.
"""

import pathlib
import re
import subprocess
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]

# Everything we ship that tells someone to pkill/pgrep by pattern.
SHIPPED = [
    ROOT / "connectonion/cli/browser_agent/client.py",
    ROOT / "connectonion/useful_skills/co-browser/SKILL.md",
    ROOT / "docs/co-browser.md",
]

PATTERN_COMMAND = re.compile(r"\b(pkill|pgrep)\s+(-\w+\s+)*(?P<pattern>[\w.\[\]/-]+)")


@pytest.fixture(params=SHIPPED, ids=lambda p: p.name)
def shipped_file(request):
    if not request.param.is_file():
        pytest.skip(f"{request.param} not shipped")
    return request.param


class TestNoShippedPatternMatchesItself:

    def test_every_pattern_is_self_excluding(self, shipped_file):
        """A pattern is safe when it cannot appear in the argv of the shell that
        runs it — which, for these, means at least one bracketed literal."""
        text = shipped_file.read_text(encoding="utf-8")

        for match in PATTERN_COMMAND.finditer(text):
            pattern = match.group("pattern")
            if "browser_agent" not in pattern:
                continue
            assert "[" in pattern, (
                f"{shipped_file.name} tells the reader to run "
                f"`{match.group(0)}`, whose pattern matches the shell running it"
            )

    def test_the_advice_is_still_there(self, shipped_file):
        """Guard against satisfying the above by deleting the instruction."""
        text = shipped_file.read_text(encoding="utf-8")

        assert "pkill" in text


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="measured on Linux; macOS pkill did not match the wrapper")
class TestTheClaimAboutPkillIsTrue:
    """The premise, measured here rather than trusted — the whole finding rests
    on it, and a reader who doubts it should be able to see it fail.

    Linux only, deliberately. The same probe run on macOS 23.1 left the shell
    alive (`SURVIVED rc=1` — BSD pkill reported no match at all), so asserting it
    everywhere would fail on a developer laptop for a reason that has nothing to
    do with the bug. Linux is where it was found, where servers run, and where
    the daemon this advice is about lives on a deployed agent.

    The shipped-text rule above is not scoped: the bracketed form is correct on
    every platform, and a SKILL.md is read on all of them.
    """

    @staticmethod
    def _run(pattern):
        """Run `pkill -f <pattern>` in its own shell; report whether it survived.

        The pattern deliberately matches nothing real, so nothing but the shell
        itself is at risk."""
        marker = "connectonion-selfmatch-probe-xyzzy"
        return subprocess.run(
            ["bash", "-c", f"pkill -f {pattern.format(m=marker)} ; echo SURVIVED"],
            capture_output=True, text=True, timeout=30,
        ).stdout

    def test_a_bare_pattern_kills_its_own_shell(self):
        assert "SURVIVED" not in self._run("{m}.suffix")

    def test_a_bracketed_pattern_does_not(self):
        assert "SURVIVED" in self._run("{m}[.]suffix")
