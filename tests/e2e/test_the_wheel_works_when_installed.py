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

The install is self-contained: a fresh venv installs the candidate wheel and
its declared dependencies. Inheriting system packages and using `--no-deps`
hid missing dependencies until HOME isolation made the user-site disappear.

The one thing this must not get wrong is *which* connectonion it imports. A
subprocess started in the repo has `''` on `sys.path` and the source tree wins,
silently — the first draft of this file did exactly that and reported the venv
was working when it had never been consulted. Every check below runs with `cwd`
set to a scratch directory for that reason.
"""

import os
import shutil
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
            cwd=REPO, capture_output=True, text=True, timeout=900,
        )
        wheels = list(into.glob("*.whl"))
        if result.returncode == 0 and wheels:
            return wheels[0]
    pytest.fail(f"could not build a wheel here: {result.stderr.strip()[-300:]}")


def _runtime_env():
    """Keep installed-package probes independent and initialization offline."""
    env = {key: value for key, value in os.environ.items()
           if key not in {"PYTHONPATH", "PYTHONHOME"}}
    env.update(CONNECTONION_BACKEND_URL="http://127.0.0.1:9",
               HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9",
               ALL_PROXY="http://127.0.0.1:9", NO_PROXY="")
    return env


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    """A venv holding only the built wheel, plus a scratch cwd to run it from."""
    if shutil.which(sys.executable) is None:
        pytest.skip("no interpreter to build with")

    root = tmp_path_factory.mktemp("wheel")
    wheel = _build_wheel(root / "dist")

    env_dir = root / "venv"
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(env_dir)
    bin_dir = env_dir / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")

    install = subprocess.run(
        [str(python), "-I", "-m", "pip", "install", "--quiet",
         "--force-reinstall", str(wheel)],
        cwd=root, capture_output=True, text=True, timeout=900,
    )
    assert install.returncode == 0, install.stderr[-500:]

    elsewhere = root / "elsewhere"
    elsewhere.mkdir()
    return python, bin_dir, elsewhere, env_dir


def _run(installed, code: str, cwd=None) -> subprocess.CompletedProcess:
    python, _, elsewhere, _env = installed
    return subprocess.run([str(python), "-c", code],
                          cwd=str(cwd or elsewhere),
                          env=_runtime_env(),
                          capture_output=True, text=True, timeout=300)


class TestItIsTheWheelBeingTested:
    def test_declared_dependencies_survive_without_user_or_system_site(self, installed):
        python, _, elsewhere, env_dir = installed
        config = (env_dir / "pyvenv.cfg").read_text()
        assert "include-system-site-packages = false" in config.lower()
        result = subprocess.run(
            [str(python), "-I", "-c",
             "import dotenv, requests, pathlib; "
             "print(pathlib.Path(dotenv.__file__).resolve()); "
             "print(pathlib.Path(requests.__file__).resolve())"],
            cwd=elsewhere, env=_runtime_env(), capture_output=True, text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert all(str(env_dir) in line for line in result.stdout.splitlines())
        check = subprocess.run([str(python), "-I", "-m", "pip", "check"],
                               cwd=elsewhere, env=_runtime_env(),
                               capture_output=True, text=True, timeout=30)
        assert check.returncode == 0, check.stdout + check.stderr

    """If this is wrong, everything below is measuring the source tree."""

    def test_the_import_comes_from_the_venv(self, installed):
        """Not merely "some site-packages" -- *this* venv's.

        Asserting only that the path contains "site-packages" would pass while
        measuring an outer installation injected by the caller's environment.
        The exact fresh venv must own the imported candidate.
        """
        *_, env_dir = installed
        result = _run(installed, "import connectonion, pathlib;"
                                 " print(pathlib.Path(connectonion.__file__).parent)")

        assert result.returncode == 0, result.stderr[-400:]
        assert str(env_dir) in result.stdout, result.stdout

    def test_the_repo_is_not_on_the_path(self, installed):
        result = _run(installed, "import connectonion;"
                                 f" print(str(connectonion.__file__).startswith({str(REPO)!r}))")

        assert "False" in result.stdout, "the source tree shadowed the installed package"


def test_installed_cli_and_sdk_share_the_project_env(installed, tmp_path):
    """The public entry point must not fall back to a subdirectory's secrets."""
    python, bin_dir, _, _ = installed
    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    (home / ".co" / "keys.env").write_text("CO_WHEEL_ENV=global\n", encoding="utf-8")
    project = home / "project"
    (project / ".co").mkdir(parents=True)
    (project / ".env").write_text("CO_WHEEL_ENV=project\n", encoding="utf-8")
    nested = project / "src"
    nested.mkdir()
    (nested / ".env").write_text("CO_WHEEL_ENV=nested\n", encoding="utf-8")
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT") if key in os.environ}
    env.update(HOME=str(home), USERPROFILE=str(home), CO_DEBUG_ENV="1")
    result = subprocess.run(
        [str(python), "-c", "import connectonion, os; print(os.environ['CO_WHEEL_ENV'])"],
        cwd=nested, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "project"
    co = bin_dir / ("co.exe" if os.name == "nt" else "co")
    result = subprocess.run(
        [str(co), "--version"], cwd=nested, env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert f"[env] {(project / '.env').resolve()}" in result.stderr
    assert f"[env] {(nested / '.env').resolve()}" not in result.stderr


class TestTheDataFilesShipped:
    """Every non-.py file the runtime loads."""

    def test_the_trust_policies_load(self, installed):
        result = _run(installed,
                      "from connectonion.network.trust.trust_agent import TrustAgent;"
                      " print([TrustAgent(l)._config.get('default')"
                      "        for l in ('open', 'careful', 'strict')])")

        assert result.returncode == 0, result.stderr[-400:]
        assert "['allow', 'ask', 'deny']" in result.stdout

    def test_the_co_ai_prompts_assemble(self, installed):
        result = _run(installed,
                      "import pathlib, connectonion;"
                      " from connectonion.cli.co_ai.prompts.assembler import assemble_prompt;"
                      " from connectonion.cli.co_ai.tools import ask_user;"
                      " d = pathlib.Path(connectonion.__file__).parent / 'cli/co_ai/prompts';"
                      " out = assemble_prompt(prompts_dir=str(d), tools=[ask_user]);"
                      " print(len(str(out)))")

        assert result.returncode == 0, result.stderr[-400:]
        assert int(result.stdout.strip()) > 1000, "the prompts assembled to nothing"

    def test_the_project_template_is_there(self, installed):
        result = _run(installed,
                      "import pathlib, connectonion;"
                      " d = pathlib.Path(connectonion.__file__).parent / 'cli/templates';"
                      " print(sorted(p.name for p in d.iterdir()))")

        assert result.returncode == 0, result.stderr[-400:]
        assert "co-ai" in result.stdout

    def test_the_docs_are_there(self, installed):
        """The force-include in pyproject.toml, which every wheel once missed."""
        result = _run(installed,
                      "import pathlib, connectonion;"
                      " d = pathlib.Path(connectonion.__file__).parent / 'docs';"
                      " print(len(list(d.rglob('*.md'))) if d.exists() else 0)")

        assert result.returncode == 0, result.stderr[-400:]
        assert int(result.stdout.strip()) > 50, "connectonion/docs/ did not ship"


class TestTheCommandRuns:

    def test_co_init_defaults_to_global_without_project_files(self, installed, tmp_path):
        _, bin_dir, _, _ = installed
        co = bin_dir / ("co.exe" if os.name == "nt" else "co")
        project = tmp_path / "not-a-project"
        project.mkdir()
        home = tmp_path / "init-home"
        home.mkdir()
        env = dict(_runtime_env(), HOME=str(home), USERPROFILE=str(home),
                   HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9",
                   ALL_PROXY="http://127.0.0.1:9", NO_PROXY="")

        result = subprocess.run([str(co), "init", "--yes"], cwd=project, env=env,
                                capture_output=True, text=True, timeout=300)

        assert result.returncode == 0, result.stderr[-400:]
        assert (home / ".co" / "keys.env").is_file()
        assert (home / ".co" / "keys" / "agent.key").is_file()
        assert list(project.iterdir()) == []

    def test_co_version_matches_the_package(self, installed):
        python, bin_dir, elsewhere, _ = installed
        co = bin_dir / ("co.exe" if os.name == "nt" else "co")

        assert co.exists(), "the `co` entry point was not installed"

        result = subprocess.run([str(co), "--version"], cwd=str(elsewhere),
                                env=_runtime_env(),
                                capture_output=True, text=True, timeout=300)
        version = (REPO / "connectonion" / "_version.py").read_text(encoding="utf-8")
        expected = version.split('__version__ = "')[1].split('"')[0]

        assert expected in result.stdout, f"{result.stdout!r} does not report {expected}"

    def test_co_init_fills_the_docs_folder(self, installed, tmp_path):
        """`co init` says ".co/docs/" is there; this is the check that it is."""
        python, bin_dir, _, _ = installed
        co = bin_dir / ("co.exe" if os.name == "nt" else "co")
        project = tmp_path / "fresh"
        project.mkdir()

        result = subprocess.run([str(co), "init", "./", "--yes"], cwd=str(project),
                                env=_runtime_env(),
                                capture_output=True, text=True, timeout=600)

        assert result.returncode == 0, result.stderr[-400:]
        assert (project / ".co" / "host.yaml").exists()
        docs = list((project / ".co" / "docs").rglob("*.md"))
        assert len(docs) > 50, f"co init produced {len(docs)} docs"
