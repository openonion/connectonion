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

import os
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
    configured = os.environ.get("CONNECTONION_DOCS_SITE")
    if configured:
        return Path(configured).expanduser().resolve() / "lib" / "version.ts"

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
    text = DOCS_SITE.read_text(encoding='utf-8')
    name = "PREVIEW_VERSION" if re.search(r"[a-zA-Z]", connectonion.__version__) else "STABLE_VERSION"
    match = re.search(rf"{name}\s*=\s*'([^']+)'", text)
    if not match:
        match = re.search(r"VERSION\s*=\s*'([^']+)'", text)
    assert match, f"{DOCS_SITE} has no {name} or VERSION"
    return match.group(1)


def test_pyproject_and_the_package_agree():
    assert _pyproject_version() == connectonion.__version__, (
        f"pyproject.toml says {_pyproject_version()}, "
        f"connectonion.__version__ is {connectonion.__version__}"
        # Not "connectonion/__init__.py says": __init__ holds no literal, it
        # re-exports from ._version. Naming the wrong file here is how the
        # release runbook came to instruct an edit to it — see
        # TestTheFileTheCliReadsIsTheOneThatWasBumped below.
    )


def test_versioning_md_names_the_version_being_shipped():
    assert _versioning_md_version() == connectonion.__version__, (
        f"VERSIONING.md's 'Current Version' is {_versioning_md_version()}, "
        f"but this is {connectonion.__version__}"
    )


def test_uv_lock_names_the_version_being_shipped():
    """Editable root metadata is still package metadata and must be refreshed."""
    lockfile = (REPO / "uv.lock").read_text(encoding="utf-8")
    package = re.search(
        r'\[\[package\]\]\s*name = "connectonion"\s*version = "([^"]+)"',
        lockfile,
    )
    assert package, "uv.lock has no root connectonion package"
    assert package.group(1) == _pyproject_version(), (
        f"uv.lock says {package.group(1)}, pyproject.toml says "
        f"{_pyproject_version()}; run uv lock after every version bump"
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


class TestTheFileTheCliReadsIsTheOneThatWasBumped:
    """test_pyproject_and_the_package_agree asks `connectonion.__version__` — an
    attribute, not a file. `co --version` does not read that attribute: it reads
    connectonion/_version.py directly, which is the entire reason that module
    exists (importing the package to print six characters pulled in the provider
    SDKs and the TUI).

    So the two can disagree, and the release runbook instructs exactly the edit
    that makes them. `~/.claude/commands/release.md` step 3.3 says to bump:

        pyproject.toml              version = "X.Y.Z"
        connectonion/__init__.py    __version__ = "X.Y.Z"

    but __init__.py holds no literal — it does `from ._version import
    __version__`. Adding the instructed line after that import shadows it, and
    the result was measured on this checkout:

        pyproject.toml           1.6.0
        __init__.py              1.6.0   (added, as instructed)
        connectonion/_version.py 1.5.11  (never touched)

        test_pyproject_and_the_package_agree   PASSED
        co --version                           co 1.5.11

    The only test that failed was the docs-site one, which is a different claim
    about a sibling repo and is skipped in CI — so following the runbook ships a
    green suite and a CLI that reports the previous release.
    """

    def test_the_version_module_holds_the_pyproject_version(self):
        literal = re.search(r'__version__\s*=\s*"([^"]+)"',
                            (REPO / 'connectonion/_version.py').read_text(encoding='utf-8'))

        assert literal, "connectonion/_version.py has no __version__ literal"
        assert literal.group(1) == _pyproject_version(), (
            f"_version.py says {literal.group(1)}, pyproject.toml says "
            f"{_pyproject_version()}. _version.py is what `co --version` reads."
        )

    def test_init_does_not_define_a_second_version(self):
        """One literal. A second one shadows the import and nothing else notices."""
        text = (REPO / 'connectonion/__init__.py').read_text(encoding='utf-8')

        assert not re.search(r'^__version__\s*=\s*["\']', text, re.MULTILINE), (
            "connectonion/__init__.py assigns its own __version__. It should only "
            "re-export from ._version, which is the file `co --version` reads — "
            "otherwise the two drift and every check that asks the attribute "
            "agrees with the wrong one."
        )

    def test_the_cli_prints_the_version_being_shipped(self):
        """The end of the chain, asked the way a user asks it."""
        from typer.testing import CliRunner

        from connectonion.cli.main import app

        output = CliRunner().invoke(app, ["--version"], env={"COLUMNS": "200"}).output

        assert _pyproject_version() in output, (
            f"`co --version` printed {output.strip()!r}, but this release is "
            f"{_pyproject_version()}"
        )
