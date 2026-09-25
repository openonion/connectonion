"""A dependency whose next major breaks us is capped below it.

connectonion 1.8.8b7 declared `httpx>=0.24.0`. Testers followed the documented
`pip install --upgrade --pre 'connectonion==1.8.8b7'`, `--pre` let pip pick
httpx 1.0.dev6, and httpx 1.0 has no HTTPError, AsyncClient or Timeout: every
remote agent call crashed. Dropping `--pre` from our install lines fixes the
preview; the cap is what keeps *stable* working on the day httpx 1.0 is final.

This is a short list on purpose. Capping everything by habit makes installs
fail to resolve next to other packages for no reason; a dependency joins this
list when its next major is known to break an API we call.
"""

import re
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

REPO = Path(__file__).resolve().parents[2]

# package -> the first version (and its pre-releases) we must never resolve.
BREAKING_MAJOR = {
    "httpx": "1.0",  # removes HTTPError / AsyncClient / Timeout (1.0.dev6 on PyPI)
    "pydantic": "3.0",  # ends the v2 BaseModel API our models use
}


def _core_requirements() -> dict[str, Requirement]:
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"^dependencies = \[(.*?)^\]", pyproject, re.MULTILINE | re.DOTALL).group(1)
    lines = [line.split("#")[0] for line in block.splitlines()]
    requirements = [Requirement(r) for r in re.findall(r'"([^"]+)"', "\n".join(lines))]
    return {r.name.lower(): r for r in requirements}


def _locked_versions() -> dict[str, str]:
    lockfile = (REPO / "uv.lock").read_text(encoding="utf-8")
    return dict(re.findall(r'\[\[package\]\]\s*name = "([^"]+)"\s*version = "([^"]+)"', lockfile))


def test_a_breaking_major_and_its_previews_are_refused():
    requirements = _core_requirements()
    for package, major in BREAKING_MAJOR.items():
        spec = requirements[package].specifier
        # prereleases=True is what `pip install --pre` asks; 1.0.dev6 is exactly
        # the version that slipped through.
        for candidate in (major, f"{major}.dev6", f"{major}b1", f"{major}.1"):
            assert not spec.contains(candidate, prereleases=True), (
                f"{package}{spec} would install {candidate}; cap it below {major}"
            )


def test_the_locked_version_still_satisfies_the_cap():
    requirements, locked = _core_requirements(), _locked_versions()
    for package in BREAKING_MAJOR:
        assert requirements[package].specifier.contains(Version(locked[package])), (
            f"uv.lock has {package} {locked[package]}, outside {requirements[package].specifier}; run `uv lock`"
        )


# `pip install 'connectonion==1.8.8b7'` already accepts that one preview: a
# specifier that names a pre-release opts into it (PEP 440), checked in a
# scratch venv against PyPI. `--pre` adds nothing for us and opens every
# dependency to its pre-releases, so no install line we print or publish uses it.
# Historical release notes stay as they were written; from 1.8.8 on, none.
_PRE_FLAG = re.compile(r"pip install[^\"'`\n]*\s--pre\b")


def test_no_install_line_we_publish_asks_for_pre_releases():
    published = [REPO / "README.md", REPO / "docs" / "releases.md", REPO / "VERSIONING.md"]
    published += sorted((REPO / "docs" / "releases").glob("1.8.8*.md"))
    published += [p for p in (REPO / "connectonion").rglob("*") if p.suffix in {".py", ".md"}]
    offenders = [
        f"{path.relative_to(REPO)}: {match.group(0)}"
        for path in published
        for match in _PRE_FLAG.finditer(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, "install lines with --pre:\n" + "\n".join(offenders)
