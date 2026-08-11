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

# Where VERSIONING.md starts recording every release rather than milestones.
# Before this it lists 0.0.1, 0.1.0, 1.0.0, 1.2.0 … — eleven entries covering
# eighty-odd tags — and the rest of that history is in CHANGELOG.md. Demanding
# an entry for each of those would mean writing a past nobody here checked.
#
# A floor, so 1.6 and everything after is covered without touching this line.
DENSE_HISTORY_FROM = (1, 5, 0)


def _documented_versions() -> set:
    return set(re.findall(r'^- (\d+\.\d+\.\d+(?:[a-zA-Z]+\d+)?)', VERSIONING.read_text(encoding='utf-8'),
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

        tags = subprocess.run(['git', 'tag', '-l', 'v*'], cwd=REPO,
                              capture_output=True, text=True).stdout.split()
        if not tags:
            # actions/checkout@v5 does not fetch tags unless asked, so on CI
            # this has nothing to compare against — and passing on an empty set
            # is how a check ends up reporting nothing in exactly the
            # environment it was written to guard. Say so instead; -rs in
            # addopts makes the skip visible.
            #
            # It runs where a release is actually cut, which is a working
            # checkout. `fetch-tags: true` in the workflow would make it run
            # everywhere and is the better answer, once someone with the
            # `workflow` token scope can push that file (#584).
            pytest.skip("no tags in this checkout — nothing to compare "
                        "VERSIONING.md against (CI does not fetch them)")

        def parts(v):
            return [int(x) for x in v.split('.')]

        documented = _documented_versions()

        released = {t.lstrip('v') for t in tags
                    if re.fullmatch(r'v\d+\.\d+\.\d+', t)}
        in_scope = {v for v in released if parts(v) >= list(DENSE_HISTORY_FROM)}

        missing = sorted(in_scope - documented, key=parts)
        assert missing == [], (
            f"released with no entry in VERSIONING.md: {missing}"
        )


class TestOneHistoryNotTwo:

    def test_the_changelog_points_at_the_one_that_is_kept(self):
        """Two histories is how one of them stops being written. CHANGELOG.md
        last gained a release in July and lists them out of order."""
        text = (REPO / 'CHANGELOG.md').read_text(encoding='utf-8')

        assert 'VERSIONING.md' in text, (
            "CHANGELOG.md does not say where the current history lives"
        )


class TestACheckThatCannotRunSaysSo:
    """The tag comparison is the one that found the six missing entries, and
    it is the one that cannot run on CI: `actions/checkout@v5` does not fetch
    tags unless asked, so `git tag -l` comes back empty there.

    Passing on an empty set is how a check ends up reporting nothing in exactly
    the environment it was written to guard — the same shape as the Windows
    clipboard tests that skipped everywhere (#584) and the docs-site check that
    skipped inside a worktree (#583). Third time this week, so it gets a test
    of its own rather than a comment.
    """

    def test_no_tags_skips_rather_than_passes(self, monkeypatch):
        import subprocess as sp_mod

        class Empty:
            stdout = ""

        monkeypatch.setattr(sp_mod, 'run', lambda *a, **k: Empty())

        with pytest.raises(pytest.skip.Exception) as skipped:
            TestNoReleaseIsSkipped().test_every_released_tag_is_documented()

        assert 'tags' in str(skipped.value)
