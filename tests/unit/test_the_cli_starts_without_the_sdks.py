"""What `co --version` has to load in order to print a string.

Measured on this machine, `python -m connectonion.cli.main --version` spends
1.84 seconds importing before it prints six characters:

    connectonion.cli            1.84s
      connectonion              1.84s
        connectonion.core.llm   1.19s
          openai                0.89s
        connectonion.useful_tools 0.48s

Every command handler in cli/main.py is already imported inside its function —
that was deliberate, and the module docstring claims "fast startup (lazy
imports)". One line undoes it: `from .. import __version__` at module scope
pulls the whole package, and the package pulls the OpenAI and Anthropic SDKs,
the TUI, and every useful_tool.

The cost is not paid by `--version` alone. It is paid by `co status`, by every
tab-completion, and by every invocation from another tool — Claude Code and
codex drive `co` in a loop — which is what makes two seconds worth removing
rather than tolerating.

The version string lives in its own module now, importable without the package.
"""

import subprocess
import sys

import pytest


def _modules_after(statement: str) -> set:
    """Import in a fresh interpreter and report what came with it."""
    code = (
        "import sys, json\n"
        f"{statement}\n"
        "print(json.dumps(sorted(m for m in sys.modules if '.' not in m)))"
    )
    out = subprocess.run([sys.executable, "-c", code],
                         capture_output=True, text=True, check=True)
    import json
    return set(json.loads(out.stdout))


HEAVY = ("openai", "anthropic")


class TestTheVersionIsCheapToRead:

    def test_it_reads_without_the_package(self):
        from connectonion._version import __version__

        assert __version__

    def test_the_package_still_exposes_it(self):
        import connectonion
        from connectonion._version import __version__

        assert connectonion.__version__ == __version__

    def test_it_agrees_with_pyproject(self):
        import re
        from pathlib import Path

        from connectonion._version import __version__

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        declared = re.search(r'^version = "([^"]+)"', pyproject.read_text(),
                             re.MULTILINE).group(1)

        assert __version__ == declared

    @pytest.mark.parametrize("sdk", HEAVY)
    def test_reading_it_pulls_in_no_sdk(self, sdk):
        loaded = _modules_after("from connectonion._version import __version__")

        assert sdk not in loaded


class TestTheCLIEntryPointIsToo:
    """The rule above is only worth having if the entry point uses it."""

    @pytest.mark.parametrize("sdk", HEAVY)
    def test_importing_the_cli_pulls_in_no_sdk(self, sdk):
        loaded = _modules_after("import connectonion.cli.main")

        assert sdk not in loaded, f"co pays for {sdk} before parsing an argument"

    def test_version_still_prints(self):
        out = subprocess.run(
            [sys.executable, "-m", "connectonion.cli.main", "--version"],
            capture_output=True, text=True)

        from connectonion._version import __version__

        assert __version__ in out.stdout


class TestThereIsOneVersionString:
    """`connectonion/cli/__init__.py` carried its own `__version__ = "0.0.1b5"`,
    left over from the first beta, with a docstring saying the version command
    read it. Nothing read it, and `co --version` had printed the package version
    for a long time — so the one place a reader would look for the CLI's version
    gave an answer four minor releases stale."""

    def test_the_cli_package_does_not_carry_a_second_one(self):
        import connectonion.cli

        assert not hasattr(connectonion.cli, "__version__")
