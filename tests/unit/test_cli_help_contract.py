"""Every `co` command's help meets the #1643 contract (#1657, #1721, #1735).

The rules live in connectonion/cli/audit.py, the engine behind `co audit`, so
the command a contributor runs and the check CI runs are the same code. One
test per command, so a failure names the command and its fix.

`co wiki` prints reviewed pages word for word and is held to them by
tests/e2e/cli/test_wiki_help_contract.py.
"""

import pytest

from connectonion.cli import audit
from connectonion.cli.main import app


@pytest.mark.parametrize("path", audit.commands(app))
def test_help_meets_the_contract(path):
    problems = audit.check_page(app, path)
    assert not problems, "\n".join(f"{f.check}: {f.fix}" for f in problems) + "\nRun: co audit"
