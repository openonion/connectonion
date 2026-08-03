"""What each `make` target actually selects.

A `-m` on the command line **replaces** the `-m` in pytest.ini's addopts; it
does not combine with it. Every target here spells its own `-m`, so every one
of them silently drops the project default:

    addopts:  -m "not real_api and not network"

`make test` is `-m "not real_api"`, which puts the 21 `network` tests back —
browser-stealth runs that drive a real Chrome against a dozen third-party
fingerprinting sites (sannysoft, creepjs, recaptcha_v3, nowsecure_cf …). Slow,
dependent on sites nobody here controls, and not what a command called `test`
should be reaching for.

This is the same mechanism that had `make test-e2e` running 140 paid-provider
tests while pytest.ini looked like it excluded them (#578), and the same one
that makes the documented per-file command in test_server_lifecycle.py collect
seven tests and run none (#444). One override, three different surprises.

So each target now says the whole expression, and these tests hold them to it.
"""

import re
from pathlib import Path

import pytest

MAKEFILE = Path(__file__).resolve().parents[2] / 'Makefile'
DEFAULT_EXCLUSIONS = ('not real_api', 'not network')


def _target(name: str) -> str:
    body = MAKEFILE.read_text().split(f"\n{name}:")[1]
    return body.split("\n\n")[0]


class TestNoTargetQuietlyReenablesWhatTheProjectExcludes:

    @pytest.mark.parametrize("target", ['test', 'cov'])
    def test_it_keeps_both_default_exclusions(self, target):
        body = _target(target)

        missing = [e for e in DEFAULT_EXCLUSIONS if e not in body]
        assert missing == [], (
            f"`make {target}` drops {missing} — a -m on the command line "
            f"replaces the one in addopts, it does not add to it"
        )


class TestTheGateKeepsTheRelayTests:
    """`make test-e2e` keeps `network`, and that is deliberate.

    The marker covers two unlike things: the eight relay end-to-end tests,
    which talk to our own relay, and the browser-stealth runs against a dozen
    third-party fingerprinting sites. Excluding it drops both — measured:

        e2e and not real_api                  → relay tests: 8
        e2e and not real_api and not network  → relay tests: 0

    A gate that quietly stops checking CONNECT, sessions and approval is worse
    than one that occasionally waits on someone else's site.
    """

    def test_the_gate_does_not_exclude_network(self):
        assert 'not network' not in _target('test-e2e')

    def test_it_still_excludes_the_paid_providers(self):
        assert 'not real_api' in _target('test-e2e')


class TestTheOptInTargetsStayOptIn:

    def test_test_real_is_the_way_to_run_paid_providers(self):
        assert 'real_api' in _target('test-real')

    def test_the_narrow_targets_are_left_alone(self):
        """`make test-unit` naming one marker is the point of it; it is not
        pretending to be a whole-suite run."""
        for target in ['test-unit', 'test-integration', 'test-cli']:
            assert '-m' in _target(target)


class TestTheDefaultIsStillWhatPytestIniSays:

    def test_addopts_still_carries_both(self):
        """If this changes, the Makefile above is wrong rather than right."""
        addopts = (MAKEFILE.parent / 'pytest.ini').read_text()
        assert 'not real_api and not network' in addopts
