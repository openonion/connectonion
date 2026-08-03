"""Everywhere the version is written down, and whether they still agree.

A release updates four places by hand, and nothing checked them. During 1.5.1
the docs site still said 1.4.0 — the whole 1.5.0 cycle advertised a version two
behind, and nobody noticed because nothing looked.

It had drifted again by 1.5.11:

    pyproject.toml            1.5.11
    connectonion/__init__.py  1.5.11
    VERSIONING.md             1.5.10
    docs-site/lib/version.ts  1.5.5     ← what docs.connectonion.com showed

The docs site is where people decide whether to install. Six releases behind is
a small lie with a real cost, and it is invisible by construction.

#299 suggests deriving `__version__` from installed distribution metadata to
remove one source. That is worse here, and measurably: in this checkout the
metadata says 1.5.10 while the source says 1.5.11, because the installed dist
lags the working tree. Deriving would make `connectonion.__version__` report
the wrong number in exactly the setup developers use. Four literals that are
checked beat three that can lie.
"""

import re
from pathlib import Path

import pytest

import connectonion

REPO = Path(__file__).resolve().parents[2]


def _docs_site_path() -> Path:
    """Where the sibling docs repo is, from a checkout *or* a worktree.

    `REPO.parent` is wrong in a worktree — it points at wherever the worktree
    was created, which is a scratch directory. That made this check skip
    silently in the setup the work actually happens in, which is the same
    failure as the drift it exists to catch: nothing looked.

    The git common dir always points into the main checkout.
    """
    candidates = [REPO.parent]
    common = REPO / '.git'
    if common.is_file():                       # a worktree: .git is a pointer file
        target = common.read_text(encoding='utf-8').split(':', 1)[-1].strip()
        # <repo>/.git/worktrees/<name> → up four to the directory holding both repos
        candidates.append(Path(target).resolve().parents[3])
    for base in candidates:
        found = base / 'docs-site' / 'lib' / 'version.ts'
        if found.exists():
            return found
    return candidates[0] / 'docs-site' / 'lib' / 'version.ts'


DOCS_SITE = _docs_site_path()


def _pyproject_version() -> str:
    text = (REPO / 'pyproject.toml').read_text(encoding='utf-8')
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml has no version"
    return match.group(1)


def _versioning_md_version() -> str:
    text = (REPO / 'VERSIONING.md').read_text(encoding='utf-8')
    match = re.search(r'^##\s*Current Version:\s*([0-9][^\s]*)', text, re.MULTILINE)
    assert match, "VERSIONING.md has no '## Current Version:' line"
    return match.group(1)


def _docs_site_version() -> str:
    match = re.search(r"VERSION\s*=\s*'([^']+)'", DOCS_SITE.read_text(encoding='utf-8'))
    assert match, f"{DOCS_SITE} has no VERSION"
    return match.group(1)


def test_pyproject_and_the_package_agree():
    assert _pyproject_version() == connectonion.__version__, (
        f"pyproject.toml says {_pyproject_version()}, "
        f"connectonion/__init__.py says {connectonion.__version__}"
    )


def test_versioning_md_names_the_version_being_shipped():
    assert _versioning_md_version() == connectonion.__version__, (
        f"VERSIONING.md's 'Current Version' is {_versioning_md_version()}, "
        f"but this is {connectonion.__version__}"
    )


@pytest.mark.skipif(not DOCS_SITE.exists(),
                    reason=f"docs-site is a separate repo; not checked out at {DOCS_SITE}")
def test_the_docs_site_advertises_the_version_that_exists():
    """The one that lied for a whole release cycle.

    Skipped when the sibling repo is absent, which includes CI — so this
    catches drift locally and in the release runbook, not on every push. That
    is the honest limit of a cross-repo check that lives in one repo.
    """
    assert _docs_site_version() == connectonion.__version__, (
        f"the docs-site checkout says {_docs_site_version()}, this release is "
        f"{connectonion.__version__}.\n"
        f"  file: {DOCS_SITE}\n"
        f"  If that checkout is simply behind, pull it. If it is current, the "
        f"site is advertising a version that does not exist — update and deploy."
    )
