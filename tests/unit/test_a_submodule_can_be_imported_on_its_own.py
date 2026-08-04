"""`from connectonion.logger import Logger` raises ImportError.

A regression from #631, which stopped `connectonion/__init__.py` importing the
framework eagerly so that `co --version` did not have to pay for it. The eager
imports had been hiding a cycle:

    connectonion.logger
      -> from .core.usage import totals_from_trace     (line 22)
      -> connectonion.core.__init__
      -> from .agent import Agent
      -> from ..logger import Logger                   -- logger is on line 22

Before #631 something always pulled `connectonion.core` in first, so the cycle
was never entered from this side. Now nothing does. Measured at 6863e45~1 (the
commit before #631) against today's main:

    import connectonion.logger                        worked  -> ImportError
    from connectonion.logger import Logger            worked  -> ImportError
    import connectonion; connectonion.logger          worked  -> ImportError

The third is the lazy package's own attribute access, so the failure is reached
through `connectonion.logger` as well as through a direct import.

It only shows in a process that has not already imported `connectonion.core`,
which is why nothing caught it: `from connectonion import Agent` imports core on
the way, and every test and every entry point does that first. A user who writes
`from connectonion.logger import Logger` in a fresh script does not.

Each case therefore runs in its own interpreter. Asserting this inside the test
process proves nothing — by then core is long since imported.
"""

import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]


def _in_a_fresh_interpreter(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO, capture_output=True, text=True, timeout=120,
    )


# Every submodule the package promises as an attribute. logger is the one that
# broke; the rest are here so the next import added to one of them is caught.
# Real top-level modules of the package.
SUBMODULES = [
    "address", "console", "core", "debug", "derive", "logger",
    "network", "prompts", "tui", "useful_events_handlers", "useful_plugins",
    "useful_tools",
]

# Everything that resolved as `connectonion.<name>` before the package went
# lazy, measured at 6863e45~1. `announce` and `relay` live under
# `connectonion.network` and were only ever attributes, never importable paths.
ATTRIBUTES = SUBMODULES + ["announce", "relay"]


class TestImportedFirstInACleanProcess:

    @pytest.mark.parametrize("module", SUBMODULES)
    def test_the_submodule_imports(self, module):
        result = _in_a_fresh_interpreter(f"import connectonion.{module}")

        assert result.returncode == 0, result.stderr.strip().splitlines()[-1:]

    def test_the_logger_class_can_be_imported_directly(self):
        """The shape a user actually writes."""
        result = _in_a_fresh_interpreter(
            "from connectonion.logger import Logger; print(Logger.__name__)"
        )

        assert result.returncode == 0, result.stderr.strip().splitlines()[-1:]
        assert "Logger" in result.stdout

    @pytest.mark.parametrize("module", ATTRIBUTES)
    def test_the_lazy_attribute_resolves(self, module):
        """`import connectonion` then `connectonion.<name>` — the path #631 added."""
        result = _in_a_fresh_interpreter(
            f"import connectonion; assert connectonion.{module}.__name__"
        )

        assert result.returncode == 0, result.stderr.strip().splitlines()[-1:]


class TestTheUsualOrderStillWorks:
    """What every entry point does today — must not regress while fixing the above."""

    def test_agent_first(self):
        result = _in_a_fresh_interpreter(
            "from connectonion import Agent; from connectonion.logger import Logger"
        )

        assert result.returncode == 0, result.stderr.strip().splitlines()[-1:]

    def test_core_first(self):
        result = _in_a_fresh_interpreter(
            "import connectonion.core; import connectonion.logger"
        )

        assert result.returncode == 0, result.stderr.strip().splitlines()[-1:]


class TestTheLoggerStillCountsTokens:
    """The import being moved is the one that does the counting."""

    def test_totals_from_trace_is_reachable_from_the_logger(self):
        """It moved into the function; it must still be the same one."""
        result = _in_a_fresh_interpreter(
            "import connectonion.logger as l\n"
            "from connectonion.core.usage import totals_from_trace as t\n"
            "import inspect; src = inspect.getsource(l)\n"
            "assert 'totals_from_trace' in src\n"
            "print(t([]))"
        )

        assert result.returncode == 0, result.stderr.strip().splitlines()[-1:]
