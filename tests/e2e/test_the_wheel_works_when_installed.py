"""What we ship, installed, from outside the repo.

The suite cannot answer this question about itself. Much of it audits the
repository — VERSIONING.md, the Makefile, `Path(__file__).parents[2] /
"connectonion"` — so running it against an installed copy produces 51 failures
that are all artifacts of the repo not being there. Measured, on a wheel built
from `bb67f19`:

    51 failed, 4113 passed          against the installed wheel
     0 failed, 4440 passed          against the source tree

Every one of the 51 was the harness, not the package. That is not a fault in
those tests — auditing the repo is their job — but it does mean **no automated
check ever looks at the artifact that goes to PyPI**. The things that break
there are the ones that do not exist in a source checkout's blind spot: a data
file that is not packaged, a loader that resolves a path from the working
directory, an entry point that is not registered.

That has happened here before. pyproject.toml carries the note:

    It was never shipped before: `packages = ["connectonion"]` only picks up what
    lives under connectonion/, and docs/ is at the root — so every wheel went out
    without it while `co init` still reported ".co/docs/ (full documentation)"
    over an empty folder.

so this checks that one directly, along with the other non-`.py` files the
runtime loads: the trust policies, the co_ai prompts, the project template.

Marked `slow` — CI selects `-m "not slow and not real_api and not network"`, so
this runs when a release is being prepared, and VERSIONING.md's checklist says
to run it.

The build is deliberately cheap. The venv is created with
`--system-site-packages` and the wheel installed `--no-deps`, so the dependency
tree is not downloaded again: what is being tested is our own files, not pip.

The one thing this must not get wrong is *which* connectonion it imports. A
subprocess started in the repo has `''` on `sys.path` and the source tree wins,
silently — the first draft of this file did exactly that and reported the venv
was working when it had never been consulted. Every check below runs with `cwd`
set to a scratch directory for that reason.
"""

import os
import shutil
import site
import subprocess
import sys
import venv
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

REPO = Path(__file__).resolve().parents[2]


def _build_wheel(into: Path) -> Path:
    """Build a wheel, preferring the non-isolated path so no network is needed."""
    for extra in (["--no-isolation"], []):
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "-o", str(into), *extra],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=900,
        )
        wheels = list(into.glob("*.whl"))
        if result.returncode == 0 and wheels:
            return wheels[0]
    pytest.skip(f"could not build a wheel here: {result.stderr.strip()[-300:]}")


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    """A venv holding only the built wheel, plus a scratch cwd to run it from."""
    if shutil.which(sys.executable) is None:
        pytest.skip("no interpreter to build with")

    root = tmp_path_factory.mktemp("wheel")
    wheel = _build_wheel(root / "dist")

    env_dir = root / "venv"
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(env_dir)
    bin_dir = env_dir / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")

    # `--system-site-packages` reaches the base interpreter, not packages in an
    # outer venv. The autouse HOME-isolation fixture also deliberately hides
    # the operator's user-site from child processes. Make the already-tested
    # outer dependency layers visible after this child venv's site-packages so
    # the wheel installed below always wins if another ConnectOnion is present.
    child_site_result = subprocess.run(
        [str(python), "-c", "import site; print(site.getsitepackages()[0])"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert child_site_result.returncode == 0, child_site_result.stderr[-400:]
    child_site = Path(child_site_result.stdout.strip())
    dependency_sites = {
        str(Path(entry).resolve())
        for entry in [*site.getsitepackages(), site.getusersitepackages()]
        if entry
        and Path(entry).is_dir()
        and Path(entry).resolve() != child_site.resolve()
    }
    (child_site / "_connectonion_outer_test_dependencies.pth").write_text(
        "".join(f"{entry}\n" for entry in sorted(dependency_sites)),
        encoding="utf-8",
    )

    install = subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--quiet",
            "--no-deps",
            "--force-reinstall",
            str(wheel),
        ],
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert install.returncode == 0, install.stderr[-500:]

    elsewhere = root / "elsewhere"
    elsewhere.mkdir()
    return python, bin_dir, elsewhere, env_dir


def _run(installed, code: str, cwd=None) -> subprocess.CompletedProcess:
    python, _, elsewhere, _env = installed
    return subprocess.run(
        [str(python), "-c", code],
        cwd=str(cwd or elsewhere),
        capture_output=True,
        text=True,
        timeout=300,
    )


class TestItIsTheWheelBeingTested:
    """If this is wrong, everything below is measuring the source tree."""

    def test_the_import_comes_from_the_venv(self, installed):
        """Not merely "some site-packages" -- *this* venv's.

        The venv is built with --system-site-packages so the dependency tree is
        not downloaded again, which means an outer installed connectonion is also
        importable. Asserting only that the path contains "site-packages" would
        pass while measuring that other copy.
        """
        *_, env_dir = installed
        result = _run(
            installed,
            "import connectonion, pathlib;"
            " print(pathlib.Path(connectonion.__file__).parent)",
        )

        assert result.returncode == 0, result.stderr[-400:]
        assert str(env_dir) in result.stdout, result.stdout

    def test_the_repo_is_not_on_the_path(self, installed):
        result = _run(
            installed,
            "import connectonion;"
            f" print(str(connectonion.__file__).startswith({str(REPO)!r}))",
        )

        assert (
            "False" in result.stdout
        ), "the source tree shadowed the installed package"


class TestTheDataFilesShipped:
    """Every non-.py file the runtime loads."""

    def test_the_trust_policies_load(self, installed):
        result = _run(
            installed,
            "from connectonion.network.trust.trust_agent import TrustAgent;"
            " print([TrustAgent(l)._config.get('default')"
            "        for l in ('open', 'careful', 'strict')])",
        )

        assert result.returncode == 0, result.stderr[-400:]
        assert "['allow', 'ask', 'deny']" in result.stdout

    def test_the_co_ai_prompts_assemble(self, installed):
        result = _run(
            installed,
            "import pathlib, connectonion;"
            " from connectonion.cli.co_ai.prompts.assembler import assemble_prompt;"
            " from connectonion.cli.co_ai.tools import ask_user;"
            " d = pathlib.Path(connectonion.__file__).parent / 'cli/co_ai/prompts';"
            " out = assemble_prompt(prompts_dir=str(d), tools=[ask_user]);"
            " print(len(str(out)))",
        )

        assert result.returncode == 0, result.stderr[-400:]
        assert int(result.stdout.strip()) > 1000, "the prompts assembled to nothing"

    def test_the_project_template_is_there(self, installed):
        result = _run(
            installed,
            "import pathlib, connectonion;"
            " d = pathlib.Path(connectonion.__file__).parent / 'cli/templates';"
            " print(sorted(p.name for p in d.iterdir()))",
        )

        assert result.returncode == 0, result.stderr[-400:]
        assert "co-ai" in result.stdout

    def test_the_docs_are_there(self, installed):
        """The force-include in pyproject.toml, which every wheel once missed."""
        result = _run(
            installed,
            "import pathlib, connectonion;"
            " d = pathlib.Path(connectonion.__file__).parent / 'docs';"
            " print(len(list(d.rglob('*.md'))) if d.exists() else 0)",
        )

        assert result.returncode == 0, result.stderr[-400:]
        assert int(result.stdout.strip()) > 50, "connectonion/docs/ did not ship"

    def test_the_browser_preview_pin_and_evidence_ship_together(self, installed):
        result = _run(
            installed,
            """
from pathlib import Path

import connectonion
from connectonion import browser_preview

package = Path(connectonion.__file__).parent
plan = (package / "docs/1.8-browser-preview-plan.md").read_text()
manifest = (package / "docs/releases/assets/v1.8.0a5/manifest.yml").read_text()
assert browser_preview.ONIONWRIGHT_VERSION == "0.0.13.dev5"
assert browser_preview.ONIONWRIGHT_DRIVER_VERSION == "1.61.0"
assert browser_preview.ONIONWRIGHT_ARTIFACT == (
    "onionwright/0.0.13.dev5/onionwright-0.0.13.dev5-py3-none-any.whl"
)
assert "0.0.13.dev5" in plan
assert "0.0.13.dev5" in manifest
""",
        )

        assert result.returncode == 0, result.stderr[-400:]


class TestTheCommandRuns:

    def test_co_version_matches_the_package(self, installed):
        python, bin_dir, elsewhere, _ = installed
        co = bin_dir / ("co.exe" if os.name == "nt" else "co")

        assert co.exists(), "the `co` entry point was not installed"

        result = subprocess.run(
            [str(co), "--version"],
            cwd=str(elsewhere),
            capture_output=True,
            text=True,
            timeout=300,
        )
        version = (REPO / "connectonion" / "_version.py").read_text(encoding="utf-8")
        expected = version.split('__version__ = "')[1].split('"')[0]

        assert (
            expected in result.stdout
        ), f"{result.stdout!r} does not report {expected}"

    def test_co_init_fills_the_docs_folder(self, installed, tmp_path):
        """`co init` says ".co/docs/" is there; this is the check that it is."""
        python, bin_dir, _, _ = installed
        co = bin_dir / ("co.exe" if os.name == "nt" else "co")
        project = tmp_path / "fresh"
        project.mkdir()

        result = subprocess.run(
            [str(co), "init", "--yes"],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=600,
        )

        assert result.returncode == 0, result.stderr[-400:]
        assert (project / ".co" / "host.yaml").exists()
        docs = list((project / ".co" / "docs").rglob("*.md"))
        assert len(docs) > 50, f"co init produced {len(docs)} docs"
