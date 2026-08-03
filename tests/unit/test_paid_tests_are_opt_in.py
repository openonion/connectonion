"""The release gate does not depend on four funded provider accounts.

`make test-e2e` is `pytest -m e2e`, and tests/conftest.py auto-marks by folder:
everything under tests/e2e/ gets `e2e`, everything under tests/e2e/real_api/
also gets `real_api`. So the gate swept in 140 tests that call Anthropic,
OpenAI, Gemini and Codex for real, and on a machine that is not funded for all
four it read like this:

    52 failed, 492 passed, 59 skipped

every failure a 401 from a provider, none of them about our code. A check that
answers "is this laptop funded" instead of "is this release sound" trains
people to read red as normal — which is not a state a long-term-support
release should ship in.

The paid tests stay; they are just no longer what stands between a release and
the door.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _collect(*args: str) -> int:
    """How many tests the given selection collects."""
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', '--collect-only', '-q',
         '-p', 'no:cacheprovider', *args],
        cwd=REPO, capture_output=True, text=True, timeout=600,
    )
    match = re.search(r'(\d+)/(\d+) tests collected|(\d+) tests collected',
                      result.stdout)
    if match:
        return int(match.group(1) or match.group(3))
    match = re.search(r'collected (\d+) items? / (\d+) deselected / (\d+) selected',
                      result.stdout)
    if match:
        return int(match.group(3))
    match = re.search(r'collected (\d+) items?', result.stdout)
    return int(match.group(1)) if match else -1


def test_the_e2e_gate_collects_no_paid_tests():
    """What `make test-e2e` runs."""
    assert _collect('tests/e2e/real_api', '-m', 'e2e and not real_api') == 0


def test_the_e2e_gate_still_covers_our_own_system():
    """Excluding paid providers must not empty the gate."""
    assert _collect('tests/e2e', '-m', 'e2e and not real_api') > 100


def test_the_paid_tests_remain_reachable():
    """Opt-in, not deleted."""
    assert _collect('tests/e2e/real_api', '-m', 'real_api') > 100


def test_the_makefile_uses_the_narrowed_selection():
    """The gate is only as good as what the Makefile actually invokes."""
    makefile = (REPO / 'Makefile').read_text()
    target = makefile.split('test-e2e:')[1].split('\n\n')[0]
    assert 'not real_api' in target, (
        f"`make test-e2e` still selects paid tests: {target.strip()!r}"
    )
