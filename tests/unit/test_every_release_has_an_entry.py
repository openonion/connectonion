"""Whether the version being shipped says what is in it.

Two files record release history and both stopped:

    VERSIONING.md     1.5.0 … 1.5.5
    CHANGELOG.md      1.5.0, then 1.2.1, 1.0.5, 1.0.9, 1.0.3 …  (out of order)
    PyPI              1.5.11

Six releases — 1.5.6 through 1.5.11 — shipped with an entry in neither. Someone
upgrading from 1.5.5 to 1.6.0 has no way to learn what they are getting, which
is a strange thing to say about a version we intend to support long-term.

#299 fixed the version *number* drifting between four places by testing that
they agree. This is the same shape one level up: the number now agrees
everywhere, and says nothing about what it contains.

So the rule is the one that would have caught it: a release cannot happen while
the version being shipped has no entry describing it.
"""

import re
from pathlib import Path

import pytest

import connectonion

REPO = Path(__file__).resolve().parents[2]
VERSIONING = REPO / 'VERSIONING.md'


def _documented_versions() -> set:
    return set(re.findall(r'^- (\d+\.\d+\.\d+)', VERSIONING.read_text(encoding='utf-8'),
                          re.MULTILINE))


class TestTheVersionBeingShippedIsDescribed:

    def test_this_version_has_an_entry(self):
        assert connectonion.__version__ in _documented_versions(), (
            f"{connectonion.__version__} is what ships and VERSIONING.md does "
            f"not say what is in it"
        )


class TestNoReleaseIsSkipped:
    """A gap is how six of them went unnoticed."""

    def test_every_released_tag_is_documented(self):
        import subprocess

        tags = subprocess.run(['git', 'tag', '-l', 'v1.5.*'], cwd=REPO,
                              capture_output=True, text=True).stdout.split()
        released = {t.lstrip('v') for t in tags}
        documented = _documented_versions()

        missing = sorted(released - documented,
                         key=lambda v: [int(p) for p in v.split('.')])
        assert missing == [], f"released with no entry: {missing}"


class TestOneHistoryNotTwo:

    def test_the_changelog_points_at_the_one_that_is_kept(self):
        """Two histories is how one of them stops being written. CHANGELOG.md
        last gained a release in July and lists them out of order."""
        text = (REPO / 'CHANGELOG.md').read_text(encoding='utf-8')

        assert 'VERSIONING.md' in text, (
            "CHANGELOG.md does not say where the current history lives"
        )
