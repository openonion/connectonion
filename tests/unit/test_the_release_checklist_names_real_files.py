"""The release procedure names files that are not there.

VERSIONING.md's "Files to Update When Versioning" and "Version Update Checklist"
are what someone follows on the day a release is cut. Every entry is wrong:

    1. /connectonion/__init__.py - `__version__` variable
         it reads `from ._version import __version__` — there is no literal to edit
    2. /setup.py - version parameter
         does not exist
    3. /docs-site/app/page.tsx - Version badge
         does not exist
    6. /pyproject.toml - version field (if exists)
         it exists, and is one of the two places that must change
    -  connectonion/_version.py
         the actual home of the version string, named nowhere

and the build step cannot run:

    python setup.py sdist bdist_wheel

Following it produces a release where nothing that matters was edited, and then
a command that fails. The version *consistency* is guarded —
test_the_version_agrees_with_itself.py compares pyproject, the package,
VERSIONING.md and the docs site — so the release would be caught. The
instructions for getting there were not guarded by anything.

Same shape as #636: a documented thing that is not real. Checked here rather
than trusted, so the procedure cannot rot again while the code moves under it.
"""

import re
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
VERSIONING = REPO / "VERSIONING.md"


def _release_sections() -> str:
    """The two sections a releaser actually follows."""
    text = VERSIONING.read_text(encoding="utf-8")
    start = text.index("## Files to Update When Versioning")
    end = text.index("## What Triggers Each Version Type")
    return text[start:end]


def _paths_named() -> list:
    """Backticked things that name a file in this repo.

    The sibling docs site is skipped on purpose: it lives beside this checkout,
    not inside it, and test_the_version_agrees_with_itself.py is what locates
    and checks it. Asserting on it from here would fail in a clone that does not
    have it, which is a different thing from the procedure being wrong.
    """
    found = []
    for line in _release_sections().split("\n"):
        if "if exists" in line or "if present" in line:
            continue
        for token in re.findall(r"`([^`]+)`", line):
            token = token.strip().lstrip("/")
            if " " in token:                              # a command, not a path
                continue
            if token.startswith(("docs-site/", "lib/")):  # the sibling repo
                continue
            if "/" in token or token.endswith((".py", ".md", ".toml", ".json", ".tsx")):
                found.append(token)
    return found


def _is_in_the_repo(name: str) -> bool:
    """A path relative to the root, or a bare filename found anywhere in it."""
    if (REPO / name).exists():
        return True
    return "/" not in name and any(REPO.rglob(name))


class TestEveryFileItNamesExists:

    def test_at_least_one_path_is_named(self):
        """If the parser stops finding anything, this test stops meaning anything."""
        assert _paths_named(), "no paths found — the sections moved or were renamed"

    def test_they_all_exist(self):
        missing = sorted({p for p in _paths_named() if not _is_in_the_repo(p)})

        assert missing == [], (
            f"VERSIONING.md tells a releaser to edit files that are not here: {missing}"
        )


class TestItNamesTheFileTheVersionIsActuallyIn:
    """`connectonion/__init__.py` has no version literal — it imports one."""

    def test_the_version_lives_where_this_test_thinks(self):
        source = (REPO / "connectonion" / "_version.py").read_text(encoding="utf-8")

        assert re.search(r'^__version__ = "', source, re.M), "the version moved again"

    def test_the_init_has_no_literal_to_edit(self):
        source = (REPO / "connectonion" / "__init__.py").read_text(encoding="utf-8")

        assert not re.search(r'^__version__ = "', source, re.M)

    def test_the_checklist_names_the_real_file(self):
        assert "_version.py" in _release_sections(), (
            "the release checklist does not mention connectonion/_version.py, "
            "which is the only place the version string exists"
        )


class TestTheBuildCommandCanRun:

    def test_it_does_not_call_a_setup_py_that_is_not_there(self):
        sections = _release_sections()

        if "setup.py" in sections:
            assert (REPO / "setup.py").exists(), (
                "the release step runs setup.py, and there is no setup.py"
            )

    def test_the_build_backend_it_names_is_the_one_configured(self):
        """pyproject declares the backend; the checklist should drive that one."""
        pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")

        assert "build-backend" in pyproject, "pyproject has no build backend"
        assert "python -m build" in _release_sections(), (
            "the checklist does not use the PEP 517 build this project is set up for"
        )


class TestReleaseArtifactsCannotMixVersions:
    def test_old_artifacts_are_removed_before_building(self):
        sections = _release_sections()

        assert sections.index("rm -rf dist/") < sections.index("python -m build")

    def test_artifacts_are_checked_before_upload(self):
        sections = _release_sections()

        assert sections.index("python -m twine check") < sections.index("python -m twine upload")

    def test_upload_is_limited_to_the_current_version(self):
        sections = _release_sections()

        assert "twine upload dist/*" not in sections
        assert "dist/connectonion-X.Y.Z.tar.gz" in sections
        assert "dist/connectonion-X.Y.Z-py3-none-any.whl" in sections


class TestTheReleaseDecisionIsPublished:
    def test_the_checklist_requires_a_design_journal(self):
        sections = _release_sections()

        assert "Design Journal" in sections
        assert "canonical URL" in sections

    def test_the_journal_waits_for_public_artifacts(self):
        sections = _release_sections()

        assert sections.index("PyPI and the GitHub") < sections.index(
            "publish the docs-site"
        )
