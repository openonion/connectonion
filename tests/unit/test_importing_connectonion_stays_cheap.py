"""`import connectonion` loads what you asked for, not everything.

#588 removed the OpenAI and Anthropic SDKs from the startup path and `co --version`
went from 9.5s to 3.4s. The other 3.4s is still there, and it is the same bug:

    connectonion.cli.main       3.36s
      connectonion              3.30s        <- importing the CLI runs this
        connectonion.core         1.39s
        connectonion.useful_tools 1.16s
          connectonion.useful_tools.gmail  0.53s   -> google.oauth2, google.auth
        connectonion.tui          0.59s
        connectonion.network      0.54s

`connectonion/__init__.py` imports every subsystem eagerly to re-export its
names. Importing `connectonion.cli.main` runs the package `__init__` first —
Python has no way around that — so `co --version` pays for Gmail's Google
credentials, the TUI, and the whole network stack in order to print six
characters.

The test that was guarding this could not see it:

    HEAVY = ("openai", "anthropic")

It named two SDKs instead of the property, so `google.oauth2` walked past a
green suite. The list here is the subsystems the package pulls, not a list of
vendors to keep adding to.

The cost is paid by every `co` invocation, and Claude Code and codex drive `co`
in a loop — which is what makes three seconds worth removing rather than
tolerating.

Lazy re-export (PEP 562) keeps `from connectonion import Agent` working and
defers the import to the first use of a name. What must not change is the
public surface, so most of this file is about that: every name in `__all__`
still resolves, and to the same object it resolved to before.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]


def _in_a_fresh_interpreter(code: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(REPO))
    return subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, cwd=REPO, env=env)


def _top_level_modules_added_by(statement: str) -> set:
    """What the statement pulls in — measured against the interpreter it started
    with, not against an empty one.

    The difference matters. `google` is already in `sys.modules` before a bare
    interpreter runs a single line of user code: a `.pth` file in site-packages
    registers the namespace package at startup, and it disappears under `-S`.
    A test that asserted `"google" not in sys.modules` was therefore asserting
    something about this machine's site-packages, and could not have passed
    whatever the framework did.

    Subtracting the baseline asks the question that is actually about us: did
    importing connectonion pull in anything under `google.*`? An empty namespace
    entry costs nothing; `google.auth` and `google.oauth2` cost half a second.
    """
    code = ("import sys, json\n"
            "_before = set(sys.modules)\n"
            f"{statement}\n"
            "_added = set(sys.modules) - _before\n"
            "print(json.dumps(sorted({m.split('.')[0] for m in _added})))")
    out = _in_a_fresh_interpreter(code)
    assert out.returncode == 0, out.stderr
    import json
    return set(json.loads(out.stdout))


# Third-party packages the framework only needs once you use the thing that
# needs them. Named by what drags them in, so a new vendor does not need a new
# entry here to be caught.
NOT_NEEDED_TO_START = {
    "openai": "the OpenAI SDK",
    "anthropic": "the Anthropic SDK",
    "google": "Gmail's Google credentials",
}


class TestStartingTheCLI:

    @pytest.mark.parametrize("module,why", sorted(NOT_NEEDED_TO_START.items()))
    def test_the_cli_entry_point_does_not_load_it(self, module, why):
        loaded = _top_level_modules_added_by("import connectonion.cli.main")

        assert module not in loaded, f"co pays for {why} before parsing an argument"

    @pytest.mark.parametrize("module,why", sorted(NOT_NEEDED_TO_START.items()))
    def test_importing_the_package_does_not_load_it(self, module, why):
        loaded = _top_level_modules_added_by("import connectonion")

        assert module not in loaded, f"importing connectonion pays for {why}"

    def test_version_still_prints(self):
        out = _in_a_fresh_interpreter(
            "import runpy, sys;"
            " sys.argv = ['co', '--version'];"
            " runpy.run_module('connectonion.cli.main', run_name='__main__')")

        from connectonion._version import __version__

        assert __version__ in out.stdout, out.stdout + out.stderr


class TestThePublicSurfaceIsUnchanged:
    """The reason to be careful: this changes how every name in the package is
    reached. A name that stops resolving is a worse bug than a slow start."""

    def test_every_exported_name_resolves(self):
        import connectonion

        missing = [n for n in connectonion.__all__ if not hasattr(connectonion, n)]

        assert not missing, f"__all__ promises names that cannot be reached: {missing}"

    def test_every_exported_name_is_importable_by_from_import(self):
        names = ", ".join(__import__("connectonion").__all__)
        out = _in_a_fresh_interpreter(f"from connectonion import {names}")

        assert out.returncode == 0, out.stderr

    def test_a_star_import_still_works(self):
        out = _in_a_fresh_interpreter(
            "exec('from connectonion import *'); assert Agent and host and llm_do")

        assert out.returncode == 0, out.stderr

    def test_the_submodules_are_still_attributes(self):
        """`from .core import Agent` used to set `connectonion.core` as a side
        effect, and code reads it. Lazy loading has to keep that true."""
        import connectonion

        for sub in ("core", "network", "useful_tools", "debug", "address", "logger"):
            assert hasattr(connectonion, sub), f"connectonion.{sub} disappeared"

    def test_an_unknown_name_still_raises_attribute_error(self):
        import connectonion

        with pytest.raises(AttributeError):
            connectonion.no_such_thing

    def test_dir_lists_the_public_names(self):
        import connectonion

        assert set(connectonion.__all__) <= set(dir(connectonion))

    def test_a_name_is_the_same_object_every_time(self):
        """Resolved once and cached — two reads must not build two classes, or
        `isinstance` against the second one fails."""
        import connectonion

        assert connectonion.Agent is connectonion.Agent


class TestANameThatIsAlsoAModule:
    """`llm_do` and `transcribe` name both a module and the function inside it.

    Importing `connectonion.llm_do` makes the import system bind the *module*
    onto the package, shadowing the function. The eager version won that race
    by accident — `__init__` always ran first and rebound the function last —
    and lazy loading loses it: `connectonion.llm_do(...)` raises

        TypeError: 'module' object is not callable

    as soon as anything has imported the submodule. Which ordinary use does:
    `from connectonion.llm_do import llm_do` is in docs/README.md and in
    web_fetch.py and gmail.py.
    """

    @pytest.mark.parametrize("name", ["llm_do", "transcribe"])
    def test_it_is_the_function_even_after_the_module_is_imported(self, name):
        out = _in_a_fresh_interpreter(
            f"import connectonion.{name}\n"
            "import connectonion\n"
            f"assert callable(connectonion.{name}), type(connectonion.{name})\n"
            f"from connectonion import {name}\n"
            f"assert callable({name}), type({name})\n")

        assert out.returncode == 0, out.stderr

    @pytest.mark.parametrize("name", ["llm_do", "transcribe"])
    def test_it_is_the_function_when_nothing_imported_the_module(self, name):
        out = _in_a_fresh_interpreter(
            f"import connectonion; assert callable(connectonion.{name})")

        assert out.returncode == 0, out.stderr

    def test_the_module_is_still_reachable_by_its_own_path(self):
        """`from connectonion.llm_do import llm_do` is documented — README:1676."""
        out = _in_a_fresh_interpreter(
            "from connectonion.llm_do import llm_do; assert callable(llm_do)")

        assert out.returncode == 0, out.stderr


class TestWhatMustStayEager:

    def test_the_env_files_are_still_loaded_at_import(self, tmp_path):
        """A documented side effect: importing the package loads .env and
        ~/.co/keys.env. Deferring that would change when credentials appear."""
        env = tmp_path / ".env"
        env.write_text("CO_TEST_EAGER_ENV=loaded\n")

        out = subprocess.run(
            [sys.executable, "-c",
             "import connectonion, os; print(os.getenv('CO_TEST_EAGER_ENV'))"],
            capture_output=True, text=True, cwd=tmp_path,
            env=dict(os.environ, PYTHONPATH=str(REPO)))

        assert "loaded" in out.stdout, out.stdout + out.stderr

    def test_the_version_is_still_an_attribute(self):
        import connectonion
        from connectonion._version import __version__

        assert connectonion.__version__ == __version__


class TestEverySubmoduleThatUsedToBeReachableStillIs:
    """Eager `from .X import Y` also bound `connectonion.X`, for every subpackage
    the import touched — including ones nobody re-exported from.

    Checked against the commit before lazy loading landed:

        connectonion.tui             module          -> must stay a module
        connectonion.useful_plugins  module          -> must stay a module
        connectonion.cli             AttributeError  -> nothing to preserve

    They are undocumented internals, which is exactly why this is worth pinning:
    nobody would notice removing them until someone's code stopped importing.
    Listing them costs nothing at startup — a name is only imported when read.
    """

    @pytest.mark.parametrize("name", ["tui", "useful_plugins"])
    def test_it_is_still_an_attribute(self, name):
        import connectonion

        assert hasattr(connectonion, name), f"connectonion.{name} used to resolve"

    @pytest.mark.parametrize("name", ["tui", "useful_plugins"])
    def test_reading_it_gives_the_module(self, name):
        import connectonion
        from types import ModuleType

        assert isinstance(getattr(connectonion, name), ModuleType)

    @pytest.mark.parametrize("name", ["tui", "useful_plugins"])
    def test_it_is_not_loaded_until_it_is_read(self, name):
        """The point of the change: listing a name must not import it."""
        loaded = _top_level_modules_added_by("import connectonion")

        assert "connectonion" in loaded
        out = _in_a_fresh_interpreter(
            "import sys, connectonion;"
            f" assert 'connectonion.{name}' not in sys.modules, 'imported too early'")

        assert out.returncode == 0, out.stderr
