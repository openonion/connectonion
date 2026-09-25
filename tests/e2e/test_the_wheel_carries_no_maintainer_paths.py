"""The built wheel, opened: no internal docs, no maintainer home directories.

1.8.8b7 went to PyPI carrying docs/testing/ (91 files) with ~245 absolute paths
from the machine that recorded them, and `co init` copied them into every
project's .co/docs/. tests/unit/test_the_wheel_ships_only_public_docs.py checks
the configuration that decides this on every commit; this checks the artifact
the configuration produces, because hatch's rules are easy to misread — the old
force-include ignored `exclude` entirely and nobody noticed for months.

Marked `slow` like the installed-wheel test beside it: it builds a wheel.
"""

import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

REPO = Path(__file__).resolve().parents[2]
PLACEHOLDER_HOMES = {"you", "me", "name", "user", "User"}
INTERNAL = ("connectonion/docs/testing/", "connectonion/docs/acceptance/",
            "connectonion/docs/releases/assets/", "connectonion/docs/archive/")


@pytest.fixture(scope="module")
def wheel(tmp_path_factory):
    out = tmp_path_factory.mktemp("wheel")
    for extra in (["--no-isolation"], []):
        result = subprocess.run([sys.executable, "-m", "build", "--wheel", "-o", str(out), *extra],
                                cwd=REPO, capture_output=True, text=True, timeout=900)
        built = list(out.glob("*.whl"))
        if result.returncode == 0 and built:
            with zipfile.ZipFile(built[0]) as archive:
                yield {name: archive.read(name) for name in archive.namelist()}
            return
    pytest.fail(f"could not build a wheel here: {result.stderr.strip()[-300:]}")


def test_public_docs_ship(wheel):
    assert "connectonion/docs/quickstart.md" in wheel
    assert any(name.startswith("connectonion/docs/design-decisions/") for name in wheel)


def test_internal_docs_do_not_ship(wheel):
    leaked = sorted(name for name in wheel if name.startswith(INTERNAL))
    assert not leaked, f"{len(leaked)} internal files in the wheel, e.g. {leaked[:5]}"


def test_no_file_names_a_real_home_directory(wheel):
    leaks = sorted(
        f"{name}: /Users/{login.decode()}"
        for name, data in wheel.items()
        for login in set(re.findall(rb"/Users/([A-Za-z0-9_.-]+)", data))
        if login.decode() not in PLACEHOLDER_HOMES
    )
    assert not leaks, "\n".join(leaks)
