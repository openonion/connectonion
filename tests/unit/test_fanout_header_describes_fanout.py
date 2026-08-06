"""fanout.py's own header describes behaviour it no longer has.

Three claims went stale while I was fixing the overwrite in this branch:

    State/Effects: … rm + relink on idempotent re-runs (_replace clears existing
                   dir/symlink/file before linking)

_replace refuses a real directory now — that was the data-loss fix. It clears a
symlink and a plain file; a directory stops the install.

    Data flow: … Kiro wants plain `.md` copies.

Not a copy any more: install_kiro writes the body with an ownership marker
prepended, because a copy leaves nothing for a re-sync to recognise as its own.

    Errors: lets OSError bubble …

No mention that an install can decline and return a lower count, which is the
one new outcome a caller has to handle.

This is the failure I opened #717, #724 and #726 about — a header trusted as a
source while the code moved underneath it — in a file I have edited four times
this branch. So it gets a test rather than a promise.

The assertions are about the specific claims, not the prose: a header has to be
allowed to read like a header.
"""

import inspect

import pytest

from connectonion.cli.commands import fanout


HEADER = inspect.getdoc(fanout) or ""


class TestTheStaleClaimsAreGone:

    def test_it_does_not_claim_to_clear_directories(self):
        assert "clears existing dir" not in HEADER, (
            "_replace refuses a real directory; the header still promises rmtree"
        )

    def test_it_does_not_call_kiro_a_plain_copy(self):
        assert "plain `.md` copies" not in HEADER

    def test_it_mentions_that_an_install_can_decline(self):
        lowered = HEADER.lower()

        assert "refus" in lowered or "declin" in lowered or "keeps" in lowered


class TestTheClaimsMatchTheCode:
    """Each one checked against behaviour, not against wording."""

    @pytest.fixture
    def home(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fanout, "HOME", tmp_path)
        return tmp_path

    def _bundle(self, tmp_path):
        skill = tmp_path / "bundle" / "skills" / "thing"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: thing\ndescription: d\n---\n\n# Body\n", encoding="utf-8"
        )
        return tmp_path / "bundle"

    def test_a_directory_really_is_kept(self, home, tmp_path):
        mine = home / ".codex" / "skills" / "a-thing"
        mine.mkdir(parents=True)

        assert fanout.install_skill_dirs(self._bundle(tmp_path), "a", "codex") == 0
        assert not mine.is_symlink()

    def test_kiro_output_really_carries_the_marker(self, home, tmp_path):
        (home / ".kiro" / "steering").mkdir(parents=True)

        fanout.install_kiro(self._bundle(tmp_path), "a")
        written = (home / ".kiro" / "steering" / "a-thing.md").read_text()

        assert fanout.OURS_MARKER in written

    def test_the_marker_constant_is_exported(self):
        """The header names it, so it has to be reachable."""
        assert isinstance(fanout.OURS_MARKER, str) and fanout.OURS_MARKER


class TestTheHeaderStillDescribesTheModule:
    """Guard against fixing this by deleting the section."""

    def test_every_public_function_is_named(self):
        public = [
            name for name, obj in vars(fanout).items()
            if inspect.isfunction(obj) and not name.startswith("_")
        ]

        missing = [name for name in public if name not in HEADER]
        assert missing == [], f"the header no longer mentions {missing}"

    def test_the_per_tool_layout_is_still_documented(self):
        for tool in ("claude", "codex", "cursor", "kiro"):
            assert tool in HEADER
